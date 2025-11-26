# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import boto3
import cfnresponse
import time
import logging
import os
from botocore.exceptions import ClientError
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event, context):
    """CloudFormation custom resource handler for AgentCore Gateway"""
    logger.info(f"Received event: {json.dumps(event)}")

    props = event.get('ResourceProperties', {})
    gateway_name = f"{props.get('StackName', 'UNKNOWN')}-analytics-gateway"

    try:
        request_type = event['RequestType']

        if request_type == 'Delete':
            delete_gateway(props, gateway_name)
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {}, physicalResourceId=gateway_name)
            return

        # Create or Update
        gateway_config = create_or_update_gateway(props, gateway_name)

        cfnresponse.send(event, context, cfnresponse.SUCCESS, {
            'GatewayUrl': gateway_config.get('gateway_url'),
            'GatewayId': gateway_config.get('gateway_id'),
            'GatewayArn': gateway_config.get('gateway_arn')
        }, physicalResourceId=gateway_name)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        cfnresponse.send(event, context, cfnresponse.FAILED, {},
                         physicalResourceId=gateway_name,
                         reason=str(e))


def create_or_update_gateway(props, gateway_name):
    """Create or update AgentCore Gateway using existing Cognito resources"""
    region = props['Region']
    lambda_arn = props['LambdaArn']
    user_pool_id = props['UserPoolId']
    client_id = props['ClientId']

    logger.info(f"Creating gateway: {gateway_name}")

    # Initialize gateway client
    client = GatewayClient(region_name=region)

    # Create JWT authorizer config using existing Cognito resources
    authorizer_config = {
        "customJWTAuthorizer": {
            "discoveryUrl": f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration",
            "allowedClients": [client_id]
        }
    }

    # Create log group for gateway
    stack_name = props.get('StackName', 'UNKNOWN')
    create_log_group(gateway_name, region, stack_name)

    # Create gateway
    gateway = client.create_mcp_gateway(
        name=gateway_name,
        role_arn=None,
        authorizer_config=authorizer_config,
        enable_semantic_search=True,
    )

    logger.info(f"Gateway created: {gateway.get('gatewayUrl')}")

    # Fix IAM permissions and wait for propagation
    logger.info("Fixing IAM permissions...")
    client.fix_iam_permissions(gateway)
    logger.info("Waiting for IAM propagation...")
    time.sleep(30)

    # Add analytics Lambda target
    logger.info("Adding analytics Lambda target...")
    client.create_mcp_gateway_target(
        gateway=gateway,
        name="AnalyticsLambdaTarget",
        target_type="lambda",
        target_payload={
            "lambdaArn": lambda_arn,
            "toolSchema": {
                "inlinePayload": [
                    {
                        "description": "Provides information from GenAI Intelligent Document Processing System and answer user questions",
                        "inputSchema": {
                            "properties": {
                                "query": {
                                    "type": "string"
                                }
                            },
                            "required": [
                                "query"
                            ],
                            "type": "object"
                        },
                        "name": "search_genaiidp"
                    }
                ]
            },
        },
    )

    logger.info("Gateway setup complete")

    return {
        'gateway_url': gateway.get('gatewayUrl'),
        'gateway_id': gateway.get('gatewayId'),
        'gateway_arn': gateway.get('gatewayArn')
    }


def delete_gateway(props, gateway_name):
    """Delete AgentCore Gateway"""
    try:
        region = props['Region']
        logger.info(f"Deleting gateway: {gateway_name}")

        # Use direct boto3 bedrock-agent client
        bedrock_client = boto3.client('bedrock-agent', region_name=region)

        # Try to find and delete the gateway by name
        try:
            # List agent gateways to find the one with our name
            response = bedrock_client.list_agent_gateways()
            target_gateway_id = None

            for gateway in response.get('agentGateways', []):
                if gateway.get('agentGatewayName') == gateway_name:
                    target_gateway_id = gateway.get('agentGatewayId')
                    break

            if target_gateway_id:
                logger.info(f"Found gateway to delete: {target_gateway_id}")

                # Delete the gateway
                bedrock_client.delete_agent_gateway(agentGatewayId=target_gateway_id)
                logger.info(f"Successfully deleted gateway: {gateway_name}")
            else:
                logger.info(f"Gateway {gateway_name} not found - may already be deleted")

        except Exception as delete_error:
            logger.warning(f"Error during gateway deletion: {delete_error}")
            # Continue to try log group cleanup

        # Clean up log group
        stack_name = props.get('StackName', 'UNKNOWN')
        delete_log_group(gateway_name, region, stack_name)

    except Exception as e:
        logger.warning(f"Error deleting gateway: {e}")
        # Don't fail the stack deletion for cleanup issues


def create_log_group(gateway_name, region, stack_name):
    """Create CloudWatch log group for AgentCore Gateway"""
    log_group_name = f"{stack_name}-AgentCoreAnalyticsGateway"

    logs_client = boto3.client('logs', region_name=region)
    try:
        logs_client.create_log_group(logGroupName=log_group_name)
        logger.info(f"Created log group: {log_group_name}")
    except logs_client.exceptions.ResourceAlreadyExistsException:
        logger.info(f"Log group already exists: {log_group_name}")
    except Exception as e:
        logger.warning(f"Failed to create log group: {e}")


def delete_log_group(gateway_name, region, stack_name):
    """Delete CloudWatch log group for AgentCore Gateway"""
    log_group_name = f"{stack_name}-AgentCoreAnalyticsGateway"
    logs_client = boto3.client('logs', region_name=region)
    try:
        logs_client.delete_log_group(logGroupName=log_group_name)
        logger.info(f"Deleted log group: {log_group_name}")
    except logs_client.exceptions.ResourceNotFoundException:
        logger.info(f"Log group already deleted: {log_group_name}")
    except Exception as e:
        logger.warning(f"Failed to delete log group: {e}")
