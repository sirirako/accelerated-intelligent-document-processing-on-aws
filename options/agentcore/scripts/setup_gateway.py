#!/usr/bin/env python3
"""
AgentCore Gateway Setup Script

This script creates an AWS Bedrock AgentCore Gateway and configures it
with the deployed Lambda function for analytics capabilities.
Uses the existing user pool and app client from the main stack.
"""

import json
import sys
import time
import argparse
import os
import logging
from datetime import datetime
from botocore.exceptions import ClientError

import boto3
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_log_group(gateway_name, region):
    """Create CloudWatch log group for AgentCore Gateway."""
    log_group_name = f"/aws/bedrock/agentcore/gateway/{gateway_name}"
    try:
        logs_client = boto3.client('logs', region_name=region)
        logs_client.create_log_group(logGroupName=log_group_name)
        logger.info(f"Created log group: {log_group_name}")
        return log_group_name
    except logs_client.exceptions.ResourceAlreadyExistsException:
        logger.info(f"Log group already exists: {log_group_name}")
        return log_group_name
    except Exception as e:
        logger.error(f"Failed to create log group: {e}")
        return log_group_name


def get_stack_outputs(stack_name, region):
    """Extract required outputs from CloudFormation stack."""
    try:
        cf_client = boto3.client('cloudformation', region_name=region)
        response = cf_client.describe_stacks(StackName=stack_name)
        stack = response['Stacks'][0]
        
        outputs = {}
        for output in stack.get('Outputs', []):
            key = output['OutputKey']
            value = output['OutputValue']
            
            if key == 'AgentCoreAnalyticsLambdaArn':
                outputs['lambda_arn'] = value
            elif key == 'ExternalAppUserPoolId':
                outputs['user_pool_id'] = value
            elif key == 'ExternalAppClientId':
                outputs['client_id'] = value
            elif key == 'ExternalAppClientSecret':
                outputs['client_secret'] = value
        
        return outputs
    except ClientError as e:
        raise RuntimeError(f"Failed to get stack outputs: {e}") from e


def get_cognito_domain(user_pool_id, region):
    """Get Cognito domain from user pool."""
    try:
        cognito_client = boto3.client('cognito-idp', region_name=region)
        pool_response = cognito_client.describe_user_pool(UserPoolId=user_pool_id)
        return pool_response['UserPool'].get('Domain')
    except ClientError:
        return None


def load_existing_config(stack_name):
    """Load existing gateway config if it exists."""
    config_file = f"gateway_config_{stack_name}.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def setup_gateway(stack_name, region, gateway_name=None):
    """Create and configure AgentCore Gateway with Lambda target."""
    try:
        # Check if gateway config already exists
        existing_config = load_existing_config(stack_name)
        if existing_config:
            print("✓ Gateway config already exists")
            print(f"Gateway URL: {existing_config.get('gateway_url', 'N/A')}")
            print(f"Gateway ID: {existing_config.get('gateway_id', 'N/A')}")
            return existing_config
        
        # Get stack outputs
        outputs = get_stack_outputs(stack_name, region)
        lambda_arn = outputs.get('lambda_arn')
        user_pool_id = outputs.get('user_pool_id')
        client_id = outputs.get('client_id')
        client_secret = outputs.get('client_secret')
        
        if not all([lambda_arn, user_pool_id, client_id, client_secret]):
            raise ValueError("Missing required stack outputs")
        
        # Generate unique gateway name with timestamp
        if not gateway_name:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            gateway_name = f"{stack_name}-analytics-gateway-{timestamp}"
        
        print("🚀 Setting up AgentCore Gateway")
        print(f"Gateway: {gateway_name}")
        print(f"Lambda: {lambda_arn}")
        print(f"User Pool: {user_pool_id}")
        print(f"Client ID: {client_id}")
        print(f"Region: {region}")
        print("=" * 60)
        
        client = GatewayClient(region_name=region)
        
        # Get Cognito domain
        domain_name = get_cognito_domain(user_pool_id, region)
        
        # Step 1: Create Gateway with JWT authorizer for Cognito
        print("Step 1: Creating Analytics Gateway...")
        authorizer_config = {
            "customJWTAuthorizer": {
                "discoveryUrl": f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration",
                "allowedAudience": [client_id],
                "allowedClients": [client_id]
            }
        }
        
        # Create log group for manual reference
        log_group_name = create_log_group(gateway_name, region)
        
        gateway = client.create_mcp_gateway(
            name=gateway_name,
            role_arn=None,
            authorizer_config=authorizer_config,
            enable_semantic_search=True,
        )
        print(f"✓ Gateway created: {gateway['gatewayUrl']}")
        
        # Step 2: Try to enable gateway logging
        print("Step 2: Configuring gateway logging...")
        try:
            # Try to configure logging using direct Bedrock API
            bedrock_client = boto3.client('bedrock-agent', region_name=region)
            bedrock_client.update_agent_gateway(
                gatewayId=gateway['gatewayId'],
                loggingConfiguration={
                    'cloudWatchLogsConfiguration': {
                        'logGroupName': log_group_name,
                        'logLevel': 'INFO'
                    }
                }
            )
            print(f"✓ Gateway logging configured to: {log_group_name}")
        except Exception as e:
            logger.warning(f"Could not configure gateway logging automatically: {e}")
            print(f"⚠️  Gateway logging not configured automatically. Configure manually in AWS Console.")
        
        # Step 3: Fix IAM permissions and wait
        print("Step 3: Fixing IAM permissions...")
        client.fix_iam_permissions(gateway)
        print("⏳ Waiting 30s for IAM propagation...")
        time.sleep(30)
        
        # Step 4: Add Lambda target with analytics tools
        print("Step 4: Adding Analytics Lambda target...")
        client.create_mcp_gateway_target(
            gateway=gateway,
            name="AnalyticsLambdaTarget",
            target_type="lambda",
            target_payload={
                "lambdaArn": lambda_arn,
                "toolSchema": {
                    "inlinePayload": [
                        {
                            "name": "run_query",
                            "description": "Execute SQL queries on analytics database",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "SQL query to execute"
                                    }
                                },
                                "required": ["query"]
                            }
                        }
                    ]
                },
            },
        )
        print("✓ Analytics Lambda target added")
        
        # Step 4: Save configuration
        config = {
            "gateway_url": gateway.get("gatewayUrl"),
            "gateway_id": gateway.get("gatewayId"),
            "gateway_arn": gateway.get("gatewayArn"),
            "gateway_name": gateway_name,
            "log_group_name": log_group_name,
            "region": region,
            "stack_name": stack_name,
            "lambda_arn": lambda_arn,
            "user_pool_id": user_pool_id,
            "client_id": client_id,
            "client_secret": client_secret,
            "domain_name": domain_name,
        }
        
        # Save to file
        config_file = f"gateway_config_{stack_name}.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        
        print("=" * 60)
        print("✅ AgentCore Gateway setup complete!")
        print(f"Gateway Name: {gateway_name}")
        print(f"Gateway URL: {gateway.get('gatewayUrl', 'N/A')}")
        print(f"Gateway ID: {gateway.get('gatewayId', 'N/A')}")
        print(f"Gateway ARN: {gateway.get('gatewayArn', 'N/A')}")
        print(f"Client ID: {client_id}")
        print(f"Client Secret: {client_secret}")
        print(f"Log Group: {log_group_name}")
        print(f"Config saved to: {config_file}")
        print("")
        print("📋 Troubleshooting Info:")
        print(f"• Gateway Logs: CloudWatch → Log Groups → {log_group_name}")
        print(f"• Lambda Logs: CloudWatch → Log Groups → /aws/lambda/[lambda-function-name]")
        print("=" * 60)
        
        return config
        
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(description='Setup AgentCore Gateway for IDP Analytics')
    parser.add_argument('--stack-name', required=True, help='IDP CloudFormation stack name')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--gateway-name', help='Gateway name (default: based on stack name with timestamp)')
    
    args = parser.parse_args()
    
    try:
        config = setup_gateway(args.stack_name, args.region, args.gateway_name)
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())