#!/usr/bin/env python3
"""
Local test script for AgentCore Analytics Processor
"""

import json
import os
import sys
from unittest.mock import Mock

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

# Set required environment variables for testing
os.environ['ATHENA_DATABASE'] = 'test-db'
os.environ['ATHENA_OUTPUT_LOCATION'] = 's3://test-bucket/athena-results/'
os.environ['LOG_LEVEL'] = 'DEBUG'

# Import the lambda handler
from index import lambda_handler

def test_analytics_processor():
    """Test the analytics processor locally"""
    
    # Mock context
    context = Mock()
    context.aws_request_id = 'test-request-123'
    
    # Test event
    event = {
        'query': 'how many documents were processed today?'
    }
    
    print("Testing AgentCore Analytics Processor...")
    print(f"Event: {json.dumps(event, indent=2)}")
    print("-" * 50)
    
    try:
        response = lambda_handler(event, context)
        print("Response:")
        print(json.dumps(response, indent=2))
        
        if response['statusCode'] == 200:
            print("\n✅ Test passed!")
        else:
            print(f"\n❌ Test failed with status code: {response['statusCode']}")
            
    except Exception as e:
        print(f"\n❌ Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_analytics_processor()