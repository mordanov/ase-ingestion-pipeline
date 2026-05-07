#!/usr/bin/env bash
# =============================================================================
# Health Ingestion Pipeline — EC2 stack teardown
#
# Deletes the CloudFormation stack created by deploy-ec2.sh.
# Removes: EC2 instance, Elastic IP, security group, IAM role + profile.
#
# ⚠  WARNING: All data stored on the EBS volume is permanently lost.
#    Back up PostgreSQL and Delta Lake data before running this script.
#
# Usage:
#   ./infra/scripts/teardown-ec2.sh
#
# Common overrides (must match the values used at deploy time):
#   REGION=eu-west-1 ./infra/scripts/teardown-ec2.sh
#   STACK_NAME=my-custom-stack ./infra/scripts/teardown-ec2.sh
#   ENVIRONMENT=dev ./infra/scripts/teardown-ec2.sh
#   DRY_RUN=1 ./infra/scripts/teardown-ec2.sh   # preview without deleting
# =============================================================================

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────

PROFILE="${PROFILE:-${AWS_PROFILE:-}}"
REGION="${REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"

AWS_ARGS=(--region "$REGION")
[[ -n "$PROFILE" ]] && AWS_ARGS+=(--profile "$PROFILE")

PROJECT_NAME="${PROJECT_NAME:-health-ingestion}"
ENVIRONMENT="${ENVIRONMENT:-poc}"
STACK_NAME="${STACK_NAME:-${PROJECT_NAME}-${ENVIRONMENT}-ec2}"

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

# ─── Preflight ────────────────────────────────────────────────────────────────

step "Preflight"

command -v aws &>/dev/null || error "AWS CLI not found — install it first"

aws "${AWS_ARGS[@]}" sts get-caller-identity --query 'Account' --output text &>/dev/null \
  || error "AWS credentials invalid (profile: ${PROFILE:-default}, region: $REGION)"

ACCOUNT_ID=$(aws "${AWS_ARGS[@]}" sts get-caller-identity --query 'Account' --output text)
info "AWS account : $ACCOUNT_ID"
info "Region      : $REGION"
info "Stack       : $STACK_NAME"
[[ "$DRY_RUN" == "1" ]] && warn "DRY RUN — no resources will be modified"

# ─── Check stack exists ───────────────────────────────────────────────────────

step "Check stack"

STACK_STATUS=$(aws "${AWS_ARGS[@]}" cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "NOT_FOUND")

if [[ "$STACK_STATUS" == "NOT_FOUND" || "$STACK_STATUS" == "None" ]]; then
  warn "Stack '$STACK_NAME' not found — already deleted or never created"
  exit 0
fi

info "Current stack status: $STACK_STATUS"

# Resolve instance ID and public IP for display before deletion
INSTANCE_ID=$(aws "${AWS_ARGS[@]}" cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" \
  --output text 2>/dev/null || true)

PUBLIC_IP=$(aws "${AWS_ARGS[@]}" cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='PublicIP'].OutputValue" \
  --output text 2>/dev/null || true)

# ─── Warning & confirmation ───────────────────────────────────────────────────

echo ""
echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${RED} WARNING: PERMANENT DELETION${NC}"
echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  The following resources will be permanently deleted:"
echo -e "  ${YELLOW}  • EC2 instance       ${INSTANCE_ID:-unknown}${NC}"
echo -e "  ${YELLOW}  • Elastic IP         ${PUBLIC_IP:-unknown}${NC}"
echo -e "  ${YELLOW}  • Security group${NC}"
echo -e "  ${YELLOW}  • IAM role + profile${NC}"
echo ""
echo -e "  ${RED}All data on the EBS volume will be lost (PostgreSQL, Delta Lake).${NC}"
echo -e "  ${RED}Ensure you have backed up any data you need before proceeding.${NC}"
echo ""

if [[ "$DRY_RUN" == "1" ]]; then
  warn "DRY RUN — skipping confirmation prompt"
else
  read -r -p "  Type the stack name to confirm deletion [${STACK_NAME}]: " CONFIRM
  echo ""
  if [[ "$CONFIRM" != "$STACK_NAME" ]]; then
    echo "Aborted — stack name did not match."
    exit 1
  fi
fi

# ─── Delete stack ─────────────────────────────────────────────────────────────

step "Deleting stack: $STACK_NAME"

run aws "${AWS_ARGS[@]}" cloudformation delete-stack --stack-name "$STACK_NAME"

if [[ "$DRY_RUN" != "1" ]]; then
  info "Waiting for stack deletion to complete (this can take 2–3 minutes)..."
  aws "${AWS_ARGS[@]}" cloudformation wait stack-delete-complete \
    --stack-name "$STACK_NAME" \
    || error "Stack deletion failed — check CloudFormation console for details"

  echo ""
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${GREEN} Stack deleted: $STACK_NAME${NC}"
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""

  if [[ -n "$PUBLIC_IP" ]]; then
    echo -e "  ${CYAN}Note:${NC} Update or remove the Route 53 DNS record that pointed to ${PUBLIC_IP}"
    echo -e "  ${CYAN}Note:${NC} Remove ${YELLOW}EC2_HOST=${PUBLIC_IP}${NC} from GitHub Secrets if no longer needed"
    echo ""
  fi
fi
