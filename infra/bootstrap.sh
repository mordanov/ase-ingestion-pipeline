#!/usr/bin/env bash
# Health Intelligence Platform — AWS Bootstrap Script
# Deploys all CloudFormation stacks and registers IoT CA certificate.
# Usage: ./infra/bootstrap.sh [--env <name>] [--region <region>]

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
ENV="${ENV:-poc}"
REGION="${AWS_REGION:-eu-central-1}"
TEMPLATES_BUCKET="${TEMPLATES_BUCKET:-}"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -base64 24)}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CF_DIR="${SCRIPT_DIR}/cloudformation"
CERTS_DIR="${SCRIPT_DIR}/certs"

# ── Parse flags ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --env) ENV="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --bucket) TEMPLATES_BUCKET="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# ── Prerequisites check ───────────────────────────────────────────────────────
echo "==> Checking prerequisites..."
for cmd in aws docker jq openssl; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: $cmd is required but not installed."
    exit 1
  fi
done

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region "$REGION")
echo "  AWS Account: ${ACCOUNT_ID}"
echo "  Region: ${REGION}"
echo "  Environment: ${ENV}"

# ── S3 bucket for templates ───────────────────────────────────────────────────
if [[ -z "$TEMPLATES_BUCKET" ]]; then
  TEMPLATES_BUCKET="${ACCOUNT_ID}-${ENV}-health-cfn-templates"
fi

echo "==> Ensuring S3 bucket: ${TEMPLATES_BUCKET}"
if ! aws s3 ls "s3://${TEMPLATES_BUCKET}" --region "$REGION" &>/dev/null; then
  aws s3 mb "s3://${TEMPLATES_BUCKET}" --region "$REGION"
  aws s3api put-bucket-versioning \
    --bucket "$TEMPLATES_BUCKET" \
    --versioning-configuration Status=Enabled \
    --region "$REGION"
fi

echo "==> Uploading CloudFormation templates..."
aws s3 sync "${CF_DIR}/" "s3://${TEMPLATES_BUCKET}/cloudformation/" \
  --include "*.yaml" --region "$REGION"

# ── Helper: deploy stack ──────────────────────────────────────────────────────
deploy_stack() {
  local stack_name="$1"
  local template_url="$2"
  shift 2
  local params=("$@")

  echo "==> Deploying stack: ${stack_name}"
  if aws cloudformation describe-stacks \
    --stack-name "$stack_name" --region "$REGION" &>/dev/null; then
    CMD="update-stack"
  else
    CMD="create-stack"
  fi

  aws cloudformation "$CMD" \
    --stack-name "$stack_name" \
    --template-url "$template_url" \
    --parameters "${params[@]}" \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
    --region "$REGION" || true

  echo "  Waiting for ${stack_name}..."
  aws cloudformation wait stack-"${CMD%%-stack}"-complete \
    --stack-name "$stack_name" --region "$REGION"
  echo "  ✓ ${stack_name} deployed"
}

BASE_URL="https://${TEMPLATES_BUCKET}.s3.${REGION}.amazonaws.com/cloudformation"

# ── Step 1: Networking ────────────────────────────────────────────────────────
deploy_stack "${ENV}-networking" \
  "${BASE_URL}/networking.yaml" \
  "ParameterKey=Environment,ParameterValue=${ENV}"

# ── Step 2: Streaming ─────────────────────────────────────────────────────────
deploy_stack "${ENV}-streaming" \
  "${BASE_URL}/streaming.yaml" \
  "ParameterKey=Environment,ParameterValue=${ENV}"

STREAM_ARN=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-streaming" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='StreamArn'].OutputValue" \
  --output text)

STREAM_NAME=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-streaming" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='StreamName'].OutputValue" \
  --output text)

# ── Step 3: IAM ───────────────────────────────────────────────────────────────
deploy_stack "${ENV}-iam" \
  "${BASE_URL}/iam.yaml" \
  "ParameterKey=Environment,ParameterValue=${ENV}" \
  "ParameterKey=KinesisStreamArn,ParameterValue=${STREAM_ARN}"

JITR_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-iam" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='JitrLambdaRoleArn'].OutputValue" \
  --output text)

ECS_TASK_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-iam" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='EcsTaskRoleArn'].OutputValue" \
  --output text)

# ── Step 4: IoT + Streaming (parallel-capable, sequential for simplicity) ─────
deploy_stack "${ENV}-iot" \
  "${BASE_URL}/iot.yaml" \
  "ParameterKey=Environment,ParameterValue=${ENV}" \
  "ParameterKey=KinesisStreamArn,ParameterValue=${STREAM_ARN}" \
  "ParameterKey=KinesisStreamName,ParameterValue=${STREAM_NAME}" \
  "ParameterKey=JitrLambdaRoleArn,ParameterValue=${JITR_ROLE_ARN}" \
  "ParameterKey=IoTRuleRoleArn,ParameterValue=${ECS_TASK_ROLE_ARN}"

# ── Step 5: Register CA certificate for JITR ─────────────────────────────────
echo "==> Registering IoT CA certificate..."
mkdir -p "${CERTS_DIR}"
CA_KEY="${CERTS_DIR}/ca.key"
CA_CERT="${CERTS_DIR}/ca.crt"
VERIFICATION_KEY="${CERTS_DIR}/verification.key"
VERIFICATION_CSR="${CERTS_DIR}/verification.csr"
VERIFICATION_CERT="${CERTS_DIR}/verification.crt"

if [[ ! -f "$CA_KEY" ]]; then
  openssl genrsa -out "$CA_KEY" 4096
  openssl req -new -x509 -days 3650 -key "$CA_KEY" \
    -out "$CA_CERT" \
    -subj "/C=US/ST=Cloud/O=HealthPlatform/CN=${ENV}-CA"
  echo "  CA certificate generated: ${CA_CERT}"
fi

REGISTRATION_CODE=$(aws iot get-registration-code --region "$REGION" --query registrationCode --output text)
openssl genrsa -out "$VERIFICATION_KEY" 2048
openssl req -new -key "$VERIFICATION_KEY" -out "$VERIFICATION_CSR" \
  -subj "/CN=${REGISTRATION_CODE}"
openssl x509 -req -in "$VERIFICATION_CSR" -CA "$CA_CERT" -CAkey "$CA_KEY" \
  -CAcreateserial -out "$VERIFICATION_CERT" -days 500

CA_CERT_ID=$(aws iot register-ca-certificate \
  --ca-certificate "file://${CA_CERT}" \
  --verification-cert "file://${VERIFICATION_CERT}" \
  --set-as-active \
  --allow-auto-registration \
  --region "$REGION" \
  --query certificateId --output text 2>/dev/null || echo "already-registered")

echo "  CA Certificate ID: ${CA_CERT_ID}"

# ── Step 6: Compute (ECS, ALB, RDS, Redis) ────────────────────────────────────
ECS_EXEC_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-iam" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='EcsExecutionRoleArn'].OutputValue" \
  --output text)

VPC_ID=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-networking" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='VpcId'].OutputValue" \
  --output text)

PUBLIC_SUBNET1=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-networking" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='PublicSubnet1'].OutputValue" \
  --output text)

PUBLIC_SUBNET2=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-networking" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='PublicSubnet2'].OutputValue" \
  --output text)

PRIVATE_SUBNET1=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-networking" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='PrivateSubnet1'].OutputValue" \
  --output text)

PRIVATE_SUBNET2=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-networking" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='PrivateSubnet2'].OutputValue" \
  --output text)

ALB_SG=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-networking" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='AlbSGId'].OutputValue" \
  --output text)

ECS_SG=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-networking" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='EcsSGId'].OutputValue" \
  --output text)

RDS_SG=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-networking" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='RdsSGId'].OutputValue" \
  --output text)

REDIS_SG=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-networking" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='RedisSGId'].OutputValue" \
  --output text)

deploy_stack "${ENV}-compute" \
  "${BASE_URL}/compute.yaml" \
  "ParameterKey=Environment,ParameterValue=${ENV}" \
  "ParameterKey=VpcId,ParameterValue=${VPC_ID}" \
  "ParameterKey=PublicSubnet1,ParameterValue=${PUBLIC_SUBNET1}" \
  "ParameterKey=PublicSubnet2,ParameterValue=${PUBLIC_SUBNET2}" \
  "ParameterKey=PrivateSubnet1,ParameterValue=${PRIVATE_SUBNET1}" \
  "ParameterKey=PrivateSubnet2,ParameterValue=${PRIVATE_SUBNET2}" \
  "ParameterKey=AlbSGId,ParameterValue=${ALB_SG}" \
  "ParameterKey=EcsSGId,ParameterValue=${ECS_SG}" \
  "ParameterKey=RdsSGId,ParameterValue=${RDS_SG}" \
  "ParameterKey=RedisSGId,ParameterValue=${REDIS_SG}" \
  "ParameterKey=EcsExecutionRoleArn,ParameterValue=${ECS_EXEC_ROLE_ARN}" \
  "ParameterKey=EcsTaskRoleArn,ParameterValue=${ECS_TASK_ROLE_ARN}" \
  "ParameterKey=KinesisStreamName,ParameterValue=${STREAM_NAME}" \
  "ParameterKey=DBPassword,ParameterValue=${DB_PASSWORD}"

# ── Step 7: Build and push Docker image ───────────────────────────────────────
ECR_URI=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-compute" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='EcrRepositoryUri'].OutputValue" \
  --output text)

echo "==> Building and pushing Docker image to ${ECR_URI}..."
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

docker build -t "${ECR_URI}:latest" "${SCRIPT_DIR}/.."
docker push "${ECR_URI}:latest"

# ── Step 8: Run database migrations ───────────────────────────────────────────
ALB_DNS=$(aws cloudformation describe-stacks \
  --stack-name "${ENV}-compute" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='AlbDnsName'].OutputValue" \
  --output text)

echo "==> Running seed script against ${ALB_DNS}..."
API_ENDPOINT="http://${ALB_DNS}" python "${SCRIPT_DIR}/../scripts/seed_devices.py" || true

# ── IoT endpoint ───────────────────────────────────────────────────────────────
IOT_ENDPOINT=$(aws iot describe-endpoint --endpoint-type iot:Data-ATS \
  --region "$REGION" --query endpointAddress --output text)

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║      Health Intelligence Platform — Deployment Summary   ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Environment : ${ENV}"
echo "║  API URL     : http://${ALB_DNS}"
echo "║  Ingest URL  : http://${ALB_DNS}:9000/ingest  (via ALB)"
echo "║  Grafana     : http://${ALB_DNS}/grafana"
echo "║  IoT Endpoint: ${IOT_ENDPOINT}"
echo "║  CA Cert     : ${CA_CERT}"
echo "╚══════════════════════════════════════════════════════════╝"
