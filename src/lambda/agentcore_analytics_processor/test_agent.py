#!/usr/bin/env python3
"""
Test script for AgentCore Analytics Processor with real agent
"""

import json
import os
import sys
from unittest.mock import Mock

# Set required environment variables
os.environ['ATHENA_DATABASE'] = 'test-reporting-db'
os.environ['ATHENA_OUTPUT_LOCATION'] = 's3://test-bucket/athena-results/'
os.environ['LOG_LEVEL'] = 'DEBUG'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

# Add paths for imports
current_dir = os.path.dirname(__file__)
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, '../../../lib/idp_common_pkg'))

def test_agent():
    """Test the actual agent implementation"""
    
    try:
        from index import lambda_handler
        
        # Mock context
        context = Mock()
        context.aws_request_id = 'test-request-123'
        
        # Test event
        event = {
            'query': 'how many documents were processed today?'
        }
        
        print("Testing AgentCore Analytics Processor with real agent...")
        print(f"Event: {json.dumps(event, indent=2)}")
        print("-" * 60)
        
        response = lambda_handler(event, context)
        
        print("Response:")
        print(json.dumps(response, indent=2))
        
        if response['statusCode'] == 200:
            print("\n✅ Agent test passed!")
        else:
            print(f"\n❌ Agent test failed with status code: {response['statusCode']}")
            
    except Exception as e:
        print(f"\n❌ Agent test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_agent()