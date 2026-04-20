#!/usr/bin/env bash
# =============================================================================
# setup-airgapped-codebuild.sh
#
# Prepares an air-gapped AWS environment so that CodeBuild can build Lambda
# container images WITHOUT any outbound internet access.
#
# What this script does:
#   1. Creates an ECR repository for base images in the customer account
#   2. Pulls ghcr.io/astral-sh/uv:0.9.6 and re-tags + pushes it to ECR
#   3. Pulls public.ecr.aws/lambda/python:3.12-arm64 and re-tags + pushes to ECR
#   4. Prints the --parameters strings to pass to idp-cli deploy
#
# Run this on a machine that HAS internet access AND AWS credentials for the
# customer account.
#
# Usage:
#   bash scripts/setup-airgapped-codebuild.sh \
#     --region <aws-region> \
#     --account <aws-account-id> \
#     [--repo-name <ecr-repo>]      # default: idp-base-images
#     [--pypi-url <artifactory-url>] # optional: your internal PyPI URL
#
# Requirements on this machine:
#   - docker (running)
#   - aws CLI v2 (configured with customer account credentials)
# =============================================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Source image references (what we pull from public registries) ─────────────
UV_SOURCE_IMAGE="ghcr.io/astral-sh/uv:0.9.6"
LAMBDA_SOURCE_IMAGE="public.ecr.aws/lambda/python:3.12-arm64"

# ── Defaults ─────────────────────────────────────────────────────────────────
REGION=""
ACCOUNT_ID=""
REPO_NAME="idp-base-images"
PYPI_URL=""

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --region)    REGION="$2";     shift 2 ;;
    --account)   ACCOUNT_ID="$2"; shift 2 ;;
    --repo-name) REPO_NAME="$2";  shift 2 ;;
    --pypi-url)  PYPI_URL="$2";   shift 2 ;;
    -h|--help)
      echo "Usage: $0 --region <region> --account <account-id> [--repo-name <name>] [--pypi-url <url>]"
      echo ""
      echo "Options:"
      echo "  --region    AWS region (e.g. us-east-1)"
      echo "  --account   AWS account ID (12-digit)"
      echo "  --repo-name ECR repo name for base images (default: idp-base-images)"
      echo "  --pypi-url  Internal PyPI/Artifactory URL for Lambda pip installs (optional)"
      exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

# ── Validate required args ────────────────────────────────────────────────────
[[ -z "$REGION" ]]     && die "--region is required. Example: --region us-east-1"
[[ -z "$ACCOUNT_ID" ]] && die "--account is required. Example: --account 123456789012"

ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
ECR_REPO="${ECR_REGISTRY}/${REPO_NAME}"

UV_TARGET_TAG="${ECR_REPO}:uv-0.9.6"
LAMBDA_TARGET_TAG="${ECR_REPO}:lambda-python-3.12-arm64"

echo ""
echo -e "${BOLD}============================================================"
echo -e " GenAI IDP Accelerator — Air-Gapped CodeBuild Setup"
echo -e "============================================================${NC}"
echo -e "  AWS Region:    ${REGION}"
echo -e "  AWS Account:   ${ACCOUNT_ID}"
echo -e "  ECR Registry:  ${ECR_REGISTRY}"
echo -e "  ECR Repo:      ${REPO_NAME}"
if [[ -n "$PYPI_URL" ]]; then
  echo -e "  PyPI Mirror:   ${PYPI_URL}"
fi
echo ""

# ── Step 1: Check prerequisites ───────────────────────────────────────────────
info "Checking prerequisites..."
command -v docker &>/dev/null || die "Docker is not installed or not running"
command -v aws    &>/dev/null || die "AWS CLI is not installed"
success "docker: $(docker --version | head -1)"
success "aws:    $(aws --version)"

# ── Step 2: Verify AWS credentials ───────────────────────────────────────────
info "Verifying AWS credentials..."
CALLER=$(aws sts get-caller-identity --region "$REGION" --output json 2>/dev/null) \
  || die "AWS credentials are not configured. Run 'aws configure' first."
CALLER_ACCOUNT=$(echo "$CALLER" | python3 -c "import sys,json; print(json.load(sys.stdin)['Account'])")
CALLER_ARN=$(echo "$CALLER"    | python3 -c "import sys,json; print(json.load(sys.stdin)['Arn'])")
if [[ "$CALLER_ACCOUNT" != "$ACCOUNT_ID" ]]; then
  warn "AWS credentials are for account ${CALLER_ACCOUNT}, but --account is ${ACCOUNT_ID}"
  warn "Make sure you're using the correct AWS profile for the customer account."
fi
success "Authenticated as: ${CALLER_ARN}"

# ── Step 3: Create ECR repository ────────────────────────────────────────────
info "Creating ECR repository: ${REPO_NAME}..."
aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$REGION" &>/dev/null \
  && success "ECR repository '${REPO_NAME}' already exists" \
  || {
    aws ecr create-repository \
      --repository-name "$REPO_NAME" \
      --region "$REGION" \
      --image-scanning-configuration scanOnPush=true \
      --output json > /dev/null
    success "Created ECR repository: ${REPO_NAME}"
  }

# ── Step 4: Login to ECR ──────────────────────────────────────────────────────
info "Logging into ECR (${ECR_REGISTRY})..."
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY" 2>/dev/null
success "Logged into ECR"

# ── Step 5: Login to AWS Public ECR (for Lambda base image) ──────────────────
info "Logging into AWS Public ECR (public.ecr.aws)..."
aws ecr-public get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin public.ecr.aws 2>/dev/null \
  && success "Logged into AWS Public ECR" \
  || warn "Could not log into public ECR — proceeding (may fail for Lambda image pull)"

# ── Step 6: Pull, re-tag, and push uv image ──────────────────────────────────
echo ""
echo -e "${BOLD}── Processing uv image ────────────────────────────────────────${NC}"
info "Pulling ${UV_SOURCE_IMAGE}..."
docker pull "${UV_SOURCE_IMAGE}"
success "Pulled ${UV_SOURCE_IMAGE}"

info "Re-tagging as ${UV_TARGET_TAG}..."
docker tag "${UV_SOURCE_IMAGE}" "${UV_TARGET_TAG}"

info "Pushing ${UV_TARGET_TAG} to ECR..."
docker push "${UV_TARGET_TAG}"
success "Pushed ${UV_TARGET_TAG}"

# ── Step 7: Pull, re-tag, and push Lambda base image ─────────────────────────
echo ""
echo -e "${BOLD}── Processing Lambda base image ───────────────────────────────${NC}"
info "Pulling ${LAMBDA_SOURCE_IMAGE}..."
docker pull "${LAMBDA_SOURCE_IMAGE}"
success "Pulled ${LAMBDA_SOURCE_IMAGE}"

info "Re-tagging as ${LAMBDA_TARGET_TAG}..."
docker tag "${LAMBDA_SOURCE_IMAGE}" "${LAMBDA_TARGET_TAG}"

info "Pushing ${LAMBDA_TARGET_TAG} to ECR..."
docker push "${LAMBDA_TARGET_TAG}"
success "Pushed ${LAMBDA_TARGET_TAG}"

# ── Step 8: Clean up local images (optional) ─────────────────────────────────
info "Cleaning up local re-tagged images..."
docker rmi "${UV_TARGET_TAG}" "${LAMBDA_TARGET_TAG}" 2>/dev/null || true
success "Cleaned up"

# ── Step 9: Print deployment parameters ──────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN} ✅ Air-gapped base images pushed successfully!${NC}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BOLD}Images pushed to ECR:${NC}"
echo -e "  UV image:          ${UV_TARGET_TAG}"
echo -e "  Lambda base image: ${LAMBDA_TARGET_TAG}"
echo ""

# Build the parameters string
EXTRA_PARAMS="UvImage=${UV_TARGET_TAG},LambdaBaseImage=${LAMBDA_TARGET_TAG}"
if [[ -n "$PYPI_URL" ]]; then
  EXTRA_PARAMS="${EXTRA_PARAMS},UvIndexUrl=${PYPI_URL}"
fi

echo -e "${BOLD}Use these parameters in your idp-cli deploy command:${NC}"
echo ""
echo -e "  ${CYAN}idp-cli deploy \\${NC}"
echo -e "    ${CYAN}--stack-name IDP-PRIVATE \\${NC}"
echo -e "    ${CYAN}--template-url <url-from-idp-cli-publish> \\${NC}"
echo -e "    ${CYAN}--admin-email admin@example.com \\${NC}"
echo -e "    ${CYAN}--region ${REGION} --wait \\${NC}"
echo -e "    ${CYAN}--parameters \"WebUIHosting=ALB,ALBVpcId=<vpc>,ALBSubnetIds=<s1>,<s2>,ALBCertificateArn=<arn>,ALBScheme=internal,AppSyncVisibility=PRIVATE,LambdaSubnetIds=<s1>,<s2>,EnableMCP=false,DocumentKnowledgeBase=DISABLED,${EXTRA_PARAMS}\"${NC}"
echo ""

if [[ -n "$PYPI_URL" ]]; then
  echo -e "${BOLD}Air-gapped parameters breakdown:${NC}"
  echo -e "  ${YELLOW}UvImage${NC}          = ${UV_TARGET_TAG}"
  echo -e "  ${YELLOW}LambdaBaseImage${NC}  = ${LAMBDA_TARGET_TAG}"
  echo -e "  ${YELLOW}UvIndexUrl${NC}       = ${PYPI_URL}"
else
  echo -e "${BOLD}Air-gapped parameters breakdown:${NC}"
  echo -e "  ${YELLOW}UvImage${NC}          = ${UV_TARGET_TAG}"
  echo -e "  ${YELLOW}LambdaBaseImage${NC}  = ${LAMBDA_TARGET_TAG}"
  echo ""
  echo -e "${YELLOW}TIP:${NC} If Lambda requirements.txt packages also fail (uv pip install),${NC}"
  echo -e "     add ${YELLOW}--pypi-url <your-artifactory-url>${NC} to this script and re-run."
  echo -e "     Then add ${YELLOW}UvIndexUrl=<url>${NC} to the --parameters string above."
fi

echo ""
echo -e "${BOLD}Also make sure the DockerBuildRole IAM role has ECR pull permissions${NC}"
echo -e "${BOLD}for ${ECR_REGISTRY}/${REPO_NAME} (already granted via AmazonEC2ContainerRegistryPowerUser).${NC}"
echo ""

# ── Step 10: Save parameters to a file for convenience ───────────────────────
PARAMS_FILE="airgapped-params-${REGION}.env"
cat > "${PARAMS_FILE}" << EOF
# Auto-generated by scripts/setup-airgapped-codebuild.sh
# Use these values in your idp-cli deploy --parameters string

UV_IMAGE=${UV_TARGET_TAG}
LAMBDA_BASE_IMAGE=${LAMBDA_TARGET_TAG}
UV_INDEX_URL=${PYPI_URL}
REGION=${REGION}
ACCOUNT_ID=${ACCOUNT_ID}

# Full parameter string for idp-cli deploy:
IDP_AIRGAPPED_PARAMS=UvImage=${UV_TARGET_TAG},LambdaBaseImage=${LAMBDA_TARGET_TAG}$([ -n "$PYPI_URL" ] && echo ",UvIndexUrl=${PYPI_URL}" || echo "")
EOF

success "Parameters saved to: ${PARAMS_FILE}"
echo -e "  Source this file to use the values: ${CYAN}source ${PARAMS_FILE}${NC}"
echo ""
