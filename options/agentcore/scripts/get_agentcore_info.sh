#!/bin/bash

# Get AgentCore Gateway Configuration Info

set -e

STACK_NAME="${1:-}"
REGION="${2:-us-east-1}"

if [[ -z "$STACK_NAME" ]]; then
    echo "Usage: $0 <stack-name> [region]"
    exit 1
fi

# Get stack outputs
OUTPUTS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs' \
    --output json)

# Extract values
CLIENT_ID=$(echo "$OUTPUTS" | jq -r '.[] | select(.OutputKey=="ExternalAppClientId") | .OutputValue // "N/A"')
CLIENT_SECRET=$(echo "$OUTPUTS" | jq -r '.[] | select(.OutputKey=="ExternalAppClientSecret") | .OutputValue // "N/A"')
USER_POOL_ID=$(echo "$OUTPUTS" | jq -r '.[] | select(.OutputKey=="ExternalAppUserPoolId") | .OutputValue // "N/A"')

# Get user pool name and domain
if [[ "$USER_POOL_ID" != "N/A" ]]; then
    USER_POOL_NAME=$(aws cognito-idp describe-user-pool \
        --user-pool-id "$USER_POOL_ID" \
        --region "$REGION" \
        --query 'UserPool.Name' \
        --output text 2>/dev/null || echo "N/A")
    
    DOMAIN_NAME=$(aws cognito-idp describe-user-pool \
        --user-pool-id "$USER_POOL_ID" \
        --region "$REGION" \
        --query 'UserPool.Domain' \
        --output text 2>/dev/null || echo "N/A")
else
    USER_POOL_NAME="N/A"
    DOMAIN_NAME="N/A"
fi

# Construct URLs
if [[ "$DOMAIN_NAME" != "N/A" && "$DOMAIN_NAME" != "None" ]]; then
    TOKEN_URL="https://${DOMAIN_NAME}.auth.${REGION}.amazoncognito.com/oauth2/token"
    AUTH_URL="https://${DOMAIN_NAME}.auth.${REGION}.amazoncognito.com/oauth2/authorize"
else
    TOKEN_URL="N/A"
    AUTH_URL="N/A"
fi

# Get gateway info from config file
GATEWAY_ARN="N/A"
GATEWAY_URL="N/A"
GATEWAY_ID="N/A"

CONFIG_FILE="gateway_config_${STACK_NAME}.json"
if [[ -f "$CONFIG_FILE" ]]; then
    GATEWAY_ARN=$(jq -r '.gateway_arn // "N/A"' "$CONFIG_FILE" 2>/dev/null || echo "N/A")
    GATEWAY_URL=$(jq -r '.gateway_url // "N/A"' "$CONFIG_FILE" 2>/dev/null || echo "N/A")
    GATEWAY_ID=$(jq -r '.gateway_id // "N/A"' "$CONFIG_FILE" 2>/dev/null || echo "N/A")
fi

# Print output
echo "=== AgentCore Gateway Configuration ==="
echo ""
echo "Gateway Resource ARN:  $GATEWAY_ARN"
echo "Gateway Resource URL:  $GATEWAY_URL"
echo "Gateway ID:            $GATEWAY_ID"
echo ""
echo "User Pool Name:        $USER_POOL_NAME"
echo "Cognito Client ID:     $CLIENT_ID"
echo "Cognito Client Secret: $CLIENT_SECRET"
echo "Domain Name:           $DOMAIN_NAME"
echo "Token URL:             $TOKEN_URL"
echo "Authorization URL:     $AUTH_URL"
