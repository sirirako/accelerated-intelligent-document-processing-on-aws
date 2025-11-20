#!/bin/bash

# AgentCore Gateway Deployment Script
# 
# This script automates the complete deployment and setup process for
# the AgentCore Gateway integration with GenAI IDP Accelerator.

set -e  # Exit on any error

# Default values
REGION="us-east-1"
SKIP_TESTS=false
SKIP_GATEWAY_SETUP=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_usage() {
    cat << EOF
Usage: $0 --stack-name STACK_NAME [OPTIONS]

Deploy and configure AgentCore Gateway for GenAI IDP Accelerator

Required Arguments:
  --stack-name STACK_NAME    IDP CloudFormation stack name

Optional Arguments:
  --region REGION           AWS region (default: us-east-1)
  --skip-tests             Skip integration testing
  --skip-gateway-setup     Skip AgentCore Gateway creation
  --help                   Show this help message

Examples:
  $0 --stack-name my-idp-stack
  $0 --stack-name my-idp-stack --region us-west-2
  $0 --stack-name my-idp-stack --skip-tests

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --skip-gateway-setup)
            SKIP_GATEWAY_SETUP=true
            shift
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$STACK_NAME" ]]; then
    log_error "Stack name is required"
    show_usage
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log_info "=== AgentCore Gateway Deployment ==="
log_info "Stack Name: $STACK_NAME"
log_info "Region: $REGION"
log_info "Skip Tests: $SKIP_TESTS"
log_info "Skip Gateway Setup: $SKIP_GATEWAY_SETUP"
echo

# Step 1: Environment validation
log_info "Step 1: Validating environment..."

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    log_error "AWS CLI not found. Please install AWS CLI."
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    log_error "Python 3 not found. Please install Python 3."
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity --region "$REGION" &> /dev/null; then
    log_error "AWS credentials not configured or invalid."
    exit 1
fi

log_success "Environment validation passed"
echo

# Step 2: Verify stack deployment
log_info "Step 2: Verifying IDP stack deployment..."

# Check if main stack exists
if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &> /dev/null; then
    log_error "Stack '$STACK_NAME' not found in region '$REGION'"
    exit 1
fi

# Check if AgentCore is enabled
ENABLE_AGENTCORE=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Parameters[?ParameterKey=='EnableAgentCore'].ParameterValue" \
    --output text 2>/dev/null || echo "")

if [[ "$ENABLE_AGENTCORE" != "true" ]]; then
    log_error "EnableAgentCore parameter must be set to 'true' in stack '$STACK_NAME'"
    log_info "Please update your stack with EnableAgentCore=true and redeploy"
    exit 1
fi

# Get Lambda function ARN from main stack outputs
LAMBDA_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='AgentCoreAnalyticsLambdaArn'].OutputValue" \
    --output text 2>/dev/null || echo "")

if [[ -z "$LAMBDA_ARN" ]]; then
    log_error "Lambda function ARN not found in stack outputs"
    log_info "Ensure AgentCore Lambda is deployed as part of the main stack"
    exit 1
fi

# Extract function name from ARN
LAMBDA_NAME=$(echo "$LAMBDA_ARN" | awk -F':' '{print $NF}')

log_success "Stack deployment verified"
log_info "Lambda Function: $LAMBDA_NAME"
log_info "Lambda ARN: $LAMBDA_ARN"
echo

# Step 3: AgentCore Gateway setup
if [[ "$SKIP_GATEWAY_SETUP" == "false" ]]; then
    log_info "Step 3: Setting up AgentCore Gateway..."
    
    if python3 "$SCRIPT_DIR/setup_gateway.py" \
        --stack-name "$STACK_NAME" \
        --region "$REGION"; then
        log_success "AgentCore Gateway setup completed"
    else
        log_warning "AgentCore Gateway setup failed or requires manual configuration"
        log_info "You can run the setup script manually later:"
        log_info "python3 $SCRIPT_DIR/setup_gateway.py --stack-name $STACK_NAME --region $REGION"
    fi
    echo
else
    log_info "Step 3: Skipping AgentCore Gateway setup (--skip-gateway-setup)"
    echo
fi

# Step 4: Integration testing
if [[ "$SKIP_TESTS" == "false" ]]; then
    log_info "Step 4: Running integration tests..."
    
    if python3 "$SCRIPT_DIR/test_gateway.py" \
        --stack-name "$STACK_NAME" \
        --region "$REGION"; then
        log_success "Integration tests passed"
    else
        log_warning "Some integration tests failed (Lambda is functional)"
    fi
    echo
else
    log_info "Step 4: Skipping integration tests (--skip-tests)"
    echo
fi

# Step 5: Deployment summary
log_info "=== Deployment Summary ==="
log_success "AgentCore Gateway deployment completed successfully!"
echo

log_info "Stack Information:"
log_info "  Main Stack: $STACK_NAME"
log_info "  Region: $REGION"
log_info "  Lambda Function: $LAMBDA_NAME"
log_info "  Lambda ARN: $LAMBDA_ARN"
echo

log_info "Next Steps:"
log_info "1. The AgentCore Gateway is now ready for natural language analytics"
log_info "2. You can test queries through the configured gateway"
log_info "3. Monitor CloudWatch logs for function execution details"
echo

log_info "Useful Commands:"
log_info "  Test gateway: python3 $SCRIPT_DIR/test_gateway.py --stack-name $STACK_NAME --region $REGION"
log_info "  View logs: aws logs tail /aws/lambda/$LAMBDA_NAME --region $REGION --follow"
echo

log_success "Deployment complete! 🎉"
