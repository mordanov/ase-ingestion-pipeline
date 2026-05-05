#!/usr/bin/env bash
# =============================================================================
# Health Ingestion Pipeline — EC2 deploy / teardown
#
# Deploys (or updates) the EC2 stack defined in infra/cloudformation/ec2.yaml.
#
# Usage:
#   ./infra/scripts/deploy-ec2.sh              # deploy / update
#   ACTION=teardown ./infra/scripts/deploy-ec2.sh   # delete stack
#
# Common overrides:
#   REGION=eu-west-1 KEY_NAME=my-key ./infra/scripts/deploy-ec2.sh
#   SSH_CIDR=203.0.113.5/32 ./infra/scripts/deploy-ec2.sh  # restrict SSH
#   INSTANCE_TYPE=t3.large ./infra/scripts/deploy-ec2.sh
#   DRY_RUN=1 ./infra/scripts/deploy-ec2.sh   # print what would run
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
TEMPLATE="${INFRA_DIR}/cloudformation/ec2.yaml"

# ─── Configuration ────────────────────────────────────────────────────────────

PROFILE="${PROFILE:-${AWS_PROFILE:-}}"
REGION="${REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"

# Build common AWS CLI args — always include --region, add --profile when set
AWS_ARGS=(--region "$REGION")
[[ -n "$PROFILE" ]] && AWS_ARGS+=(--profile "$PROFILE")
PROJECT_NAME="${PROJECT_NAME:-health-ingestion}"
ENVIRONMENT="${ENVIRONMENT:-poc}"
STACK_NAME="${STACK_NAME:-${PROJECT_NAME}-${ENVIRONMENT}-ec2}"

INSTANCE_TYPE="${INSTANCE_TYPE:-t3.medium}"
KEY_NAME="${KEY_NAME:-}"
SSH_CIDR="${SSH_CIDR:-0.0.0.0/0}"
VOLUME_SIZE="${VOLUME_SIZE:-30}"
HOSTED_ZONE_NAME="${HOSTED_ZONE_NAME:-aleksandr-mordanov.click.}"
RECORD_NAME="${RECORD_NAME:-ingestion-pipeline.aleksandr-mordanov.click}"
# VPC_ID must be set (defaults to the default VPC if not provided — resolved below)
VPC_ID="${VPC_ID:-}"

ACTION="${ACTION:-deploy}"
DRY_RUN="${DRY_RUN:-0}"

# ─── Colours ─────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
step()    { echo -e "\n${CYAN}══ $* ══${NC}"; }
dry()     { echo -e "${YELLOW}[DRY]${NC}   would run: $*"; }

run() {
  if [[ "$DRY_RUN" == "1" ]]; then dry "$*"; else "$@"; fi
}

# ─── Helpers ─────────────────────────────────────────────────────────────────

stack_exists() {
  aws "${AWS_ARGS[@]}" cloudformation describe-stacks \
    --stack-name "$1" \
    --query 'Stacks[0].StackStatus' --output text 2>/dev/null \
    | grep -qv "NONE\|does not exist" && return 0 || return 1
}

stack_output() {
  aws "${AWS_ARGS[@]}" cloudformation describe-stacks \
    --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey==\`$2\`].OutputValue" \
    --output text 2>/dev/null || true
}

# ─── Preflight ────────────────────────────────────────────────────────────────

step "Preflight"
for cmd in aws; do
  command -v "$cmd" &>/dev/null || error "Required tool not found: $cmd"
done

aws "${AWS_ARGS[@]}" sts get-caller-identity --query 'Account' --output text &>/dev/null \
  || error "AWS credentials invalid (profile: ${PROFILE:-default}, region: $REGION)"

ACCOUNT_ID=$(aws "${AWS_ARGS[@]}" sts get-caller-identity --query 'Account' --output text)
info "AWS account: $ACCOUNT_ID  region: $REGION  profile: ${PROFILE:-default}"
[[ "$DRY_RUN" == "1" ]] && warn "DRY RUN — no resources will be modified"

# Resolve VPC ID (auto-detect default VPC if not provided)
if [[ -z "$VPC_ID" ]]; then
  VPC_ID=$(aws "${AWS_ARGS[@]}" ec2 describe-vpcs \
    --filters "Name=is-default,Values=true" \
    --query "Vpcs[0].VpcId" \
    --output text 2>/dev/null || true)
  [[ -z "$VPC_ID" || "$VPC_ID" == "None" ]] \
    && error "No default VPC found. Set VPC_ID=vpc-xxxx explicitly."
  info "Using default VPC: $VPC_ID"
fi

# ─── Build parameter list ─────────────────────────────────────────────────────

PARAMS=(
  "ParameterKey=ProjectName,ParameterValue=${PROJECT_NAME}"
  "ParameterKey=Environment,ParameterValue=${ENVIRONMENT}"
  "ParameterKey=InstanceType,ParameterValue=${INSTANCE_TYPE}"
  "ParameterKey=SSHAllowedCidr,ParameterValue=${SSH_CIDR}"
  "ParameterKey=HostedZoneName,ParameterValue=${HOSTED_ZONE_NAME}"
  "ParameterKey=RecordName,ParameterValue=${RECORD_NAME}"
  "ParameterKey=VolumeSize,ParameterValue=${VOLUME_SIZE}"
  "ParameterKey=VpcId,ParameterValue=${VPC_ID}"
)
[[ -n "$KEY_NAME" ]] && PARAMS+=("ParameterKey=KeyName,ParameterValue=${KEY_NAME}")

# ─── Deploy ───────────────────────────────────────────────────────────────────

if [[ "$ACTION" == "deploy" ]]; then
  step "Deploy EC2 stack: $STACK_NAME"

  if stack_exists "$STACK_NAME"; then
    info "Stack exists — updating..."
    run aws "${AWS_ARGS[@]}" cloudformation update-stack \
      --stack-name "$STACK_NAME" \
      --template-body "file://${TEMPLATE}" \
      --parameters "${PARAMS[@]}" \
      --capabilities CAPABILITY_NAMED_IAM \
      || { warn "No changes to deploy (stack is already up-to-date)"; exit 0; }
    if [[ "$DRY_RUN" != "1" ]]; then
      info "Waiting for update to complete..."
      aws "${AWS_ARGS[@]}" cloudformation wait stack-update-complete \
        --stack-name "$STACK_NAME" \
        || error "Stack update failed — check CloudFormation console"
    fi
  else
    info "Creating new stack..."
    run aws "${AWS_ARGS[@]}" cloudformation create-stack \
      --stack-name "$STACK_NAME" \
      --template-body "file://${TEMPLATE}" \
      --parameters "${PARAMS[@]}" \
      --capabilities CAPABILITY_NAMED_IAM
    if [[ "$DRY_RUN" != "1" ]]; then
      info "Waiting for stack creation..."
      aws "${AWS_ARGS[@]}" cloudformation wait stack-create-complete \
        --stack-name "$STACK_NAME" \
        || error "Stack creation failed — check CloudFormation console"
    fi
  fi

  if [[ "$DRY_RUN" != "1" ]]; then
    PUBLIC_IP=$(stack_output "$STACK_NAME" "PublicIP")
    DNS_NAME=$(stack_output "$STACK_NAME" "DNSName")
    INSTANCE_ID=$(stack_output "$STACK_NAME" "InstanceId")

    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN} EC2 instance deployed${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "  Instance ID  : ${YELLOW}${INSTANCE_ID}${NC}"
    echo -e "  Public IP    : ${YELLOW}${PUBLIC_IP}${NC}"
    echo -e "  DNS          : ${YELLOW}${DNS_NAME}${NC}"
    echo ""
    echo -e "  Next steps:"
    echo -e "  ${CYAN}1. SSH in:${NC}"
    if [[ -n "$KEY_NAME" ]]; then
      echo -e "     ssh ec2-user@${DNS_NAME}"
    else
      echo -e "     aws ssm start-session --target ${INSTANCE_ID} --region ${REGION}${PROFILE:+ --profile ${PROFILE}}"
    fi
    echo -e "  ${CYAN}2. Clone repo and start services:${NC}"
    echo -e "     git clone <your-repo-url>"
    echo -e "     cd ingestion_pipeline"
    echo -e "     cp .env.example .env   # fill in secrets"
    echo -e "     docker compose up -d"
    echo ""
  fi

# ─── Teardown ─────────────────────────────────────────────────────────────────

elif [[ "$ACTION" == "teardown" ]]; then
  step "Teardown EC2 stack: $STACK_NAME"

  if ! stack_exists "$STACK_NAME"; then
    warn "Stack $STACK_NAME not found — already deleted or never created"
    exit 0
  fi

  echo ""
  echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${RED} WARNING: This will permanently delete the EC2 instance and EIP${NC}"
  echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""

  if [[ "$DRY_RUN" != "1" ]]; then
    read -r -p "Type the stack name to confirm deletion [${STACK_NAME}]: " CONFIRM
    [[ "$CONFIRM" != "$STACK_NAME" ]] && { echo "Aborted"; exit 1; }
  fi

  run aws "${AWS_ARGS[@]}" cloudformation delete-stack --stack-name "$STACK_NAME"
  if [[ "$DRY_RUN" != "1" ]]; then
    info "Waiting for stack deletion..."
    aws "${AWS_ARGS[@]}" cloudformation wait stack-delete-complete \
      --stack-name "$STACK_NAME" \
      || error "Stack deletion failed — check CloudFormation console"
    success "Stack deleted: $STACK_NAME"
  fi

else
  error "Unknown ACTION='${ACTION}'. Use 'deploy' or 'teardown'."
fi