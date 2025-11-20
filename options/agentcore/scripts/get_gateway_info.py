#!/usr/bin/env python3
"""
Get AgentCore Gateway Configuration Info

This script retrieves and displays gateway resource details and Cognito configuration.
"""

import boto3
import json
import sys
import argparse
from botocore.exceptions import ClientError


def get_stack_info(stack_name, region):
    """Get stack outputs and parameters."""
    try:
        cf_client = boto3.client('cloudformation', region_name=region)
        response = cf_client.describe_stacks(StackName=stack_name)
        stack = response['Stacks'][0]
        
        info = {}
        
        # Extract outputs
        for output in stack.get('Outputs', []):
            key = output['OutputKey']
            value = output['OutputValue']
            
            if key == 'ExternalAppClientId':
                info['client_id'] = value
            elif key == 'ExternalAppClientSecret':
                info['client_secret'] = value
            elif key == 'ExternalAppUserPoolId':
                info['user_pool_id'] = value
        
        return info
        
    except ClientError as e:
        raise RuntimeError(f"Failed to get stack info: {e}") from e


def get_user_pool_name(user_pool_id, region):
    """Get user pool name."""
    try:
        cognito_client = boto3.client('cognito-idp', region_name=region)
        pool_response = cognito_client.describe_user_pool(UserPoolId=user_pool_id)
        return pool_response['UserPool']['Name']
    except ClientError:
        return None


def get_cognito_domain(user_pool_id, region):
    """Get Cognito domain name from user pool."""
    try:
        cognito_client = boto3.client('cognito-idp', region_name=region)
        pool_response = cognito_client.describe_user_pool(UserPoolId=user_pool_id)
        
        # Extract domain from user pool custom domain or default domain
        user_pool = pool_response['UserPool']
        if 'Domain' in user_pool:
            return user_pool['Domain']
        
        return None
    except ClientError:
        return None


def main():
    parser = argparse.ArgumentParser(description='Get AgentCore Gateway Configuration')
    parser.add_argument('--stack-name', required=True, help='IDP CloudFormation stack name')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    args = parser.parse_args()
    
    try:
        info = get_stack_info(args.stack_name, args.region)
        
        # Get user pool details
        if 'user_pool_id' in info:
            user_pool_name = get_user_pool_name(info['user_pool_id'], args.region)
            info['user_pool_name'] = user_pool_name
            
            # Get Cognito domain
            domain_name = get_cognito_domain(info['user_pool_id'], args.region)
            info['domain_name'] = domain_name
            
            # Construct URLs
            if domain_name:
                info['token_url'] = f"https://{domain_name}.auth.{args.region}.amazoncognito.com/oauth2/token"
                info['authorization_url'] = f"https://{domain_name}.auth.{args.region}.amazoncognito.com/oauth2/authorize"
        
        if args.json:
            print(json.dumps(info, indent=2))
        else:
            print("=== AgentCore Gateway Configuration ===\n")
            print(f"Gateway Resource ARN:  {info.get('gateway_arn', 'N/A (created via setup_gateway.py)')}")
            print(f"Gateway Resource URL:  {info.get('gateway_url', 'N/A (created via setup_gateway.py)')}")
            print(f"User Pool Name:        {info.get('user_pool_name', 'N/A')}")
            print(f"Cognito Client ID:     {info.get('client_id', 'N/A')}")
            print(f"Cognito Client Secret: {info.get('client_secret', 'N/A')}")
            print(f"Domain Name:           {info.get('domain_name', 'N/A')}")
            print(f"Token URL:             {info.get('token_url', 'N/A')}")
            print(f"Authorization URL:     {info.get('authorization_url', 'N/A')}")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
