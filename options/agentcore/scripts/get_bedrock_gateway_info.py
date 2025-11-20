#!/usr/bin/env python3
"""
Get Bedrock AgentCore Gateway Info

This script retrieves gateway details from AWS Bedrock Agent service.
"""

import boto3
import json
import sys
import argparse
from botocore.exceptions import ClientError


def list_gateways(region):
    """List all Bedrock Agent gateways."""
    try:
        bedrock_agent_client = boto3.client('bedrock-agent', region_name=region)
        response = bedrock_agent_client.list_agents()
        return response.get('agentSummaries', [])
    except ClientError as e:
        raise RuntimeError(f"Failed to list gateways: {e}") from e


def get_gateway_by_name(gateway_name, region):
    """Get gateway details by name."""
    try:
        bedrock_agent_client = boto3.client('bedrock-agent', region_name=region)
        
        # List all agents/gateways
        response = bedrock_agent_client.list_agents()
        
        for agent in response.get('agentSummaries', []):
            if gateway_name.lower() in agent.get('agentName', '').lower():
                agent_id = agent['agentId']
                # Get full agent details
                agent_details = bedrock_agent_client.get_agent(agentId=agent_id)
                return agent_details.get('agent', {})
        
        return None
    except ClientError as e:
        raise RuntimeError(f"Failed to get gateway: {e}") from e


def main():
    parser = argparse.ArgumentParser(description='Get Bedrock AgentCore Gateway Info')
    parser.add_argument('--gateway-name', help='Gateway name to search for')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    args = parser.parse_args()
    
    try:
        if args.gateway_name:
            gateway = get_gateway_by_name(args.gateway_name, args.region)
            if not gateway:
                print(f"Gateway '{args.gateway_name}' not found", file=sys.stderr)
                return 1
            
            if args.json:
                print(json.dumps(gateway, indent=2, default=str))
            else:
                print("=== Bedrock AgentCore Gateway Info ===\n")
                print(f"Gateway ID:     {gateway.get('agentId', 'N/A')}")
                print(f"Gateway Name:   {gateway.get('agentName', 'N/A')}")
                print(f"Gateway ARN:    {gateway.get('agentArn', 'N/A')}")
                print(f"Status:         {gateway.get('agentStatus', 'N/A')}")
                print(f"Description:    {gateway.get('description', 'N/A')}")
        else:
            # List all gateways
            gateways = list_gateways(args.region)
            
            if args.json:
                print(json.dumps(gateways, indent=2, default=str))
            else:
                print("=== Available Bedrock AgentCore Gateways ===\n")
                if not gateways:
                    print("No gateways found")
                else:
                    for gateway in gateways:
                        print(f"Name: {gateway.get('agentName', 'N/A')}")
                        print(f"ID:   {gateway.get('agentId', 'N/A')}")
                        print(f"ARN:  {gateway.get('agentArn', 'N/A')}")
                        print()
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
