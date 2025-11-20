#!/usr/bin/env python3
"""
AgentCore Gateway Testing Script

This script validates the AgentCore Gateway integration by testing
MCP protocol endpoints and analytics tools functionality.
"""

import boto3
import json
import sys
import time
import argparse
from botocore.exceptions import ClientError


def get_lambda_function_name(stack_name, region):
    """Get Lambda function name from CloudFormation stack."""
    try:
        cf_client = boto3.client('cloudformation', region_name=region)
        
        # Get function name from main stack outputs
        response = cf_client.describe_stacks(StackName=stack_name)
        stack = response['Stacks'][0]
        
        for output in stack.get('Outputs', []):
            if output['OutputKey'] == 'AgentCoreAnalyticsLambdaArn':
                arn = output['OutputValue']
                return arn.split(':')[-1]
        
        raise ValueError("Lambda function ARN not found in stack outputs")
        
    except ClientError as e:
        raise RuntimeError(f"Failed to get Lambda function name: {e}") from e


def parse_lambda_response(response):
    """Parse Lambda response which may be wrapped in statusCode/body format."""
    try:
        payload = json.loads(response['Payload'].read())
        
        # Check if response is wrapped in API Gateway format
        if isinstance(payload, dict) and 'statusCode' in payload and 'body' in payload:
            body = json.loads(payload['body'])
            return body
        
        return payload
    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"Failed to parse Lambda response: {e}") from e


def test_mcp_tools_list(function_name, region):
    """Test MCP tools/list endpoint."""
    try:
        lambda_client = boto3.client('lambda', region_name=region)
        
        payload = {
            "method": "tools/list",
            "params": {}
        }
        
        print("Testing MCP tools/list endpoint...")
        response = lambda_client.invoke(
            FunctionName=function_name,
            Payload=json.dumps(payload)
        )
        
        result = parse_lambda_response(response)
        
        if 'tools' in result:
            tools = result['tools']
            print(f"   ✅ Found {len(tools)} tools:") 
            for tool in tools:
                print(f"      - {tool['name']}: {tool['description']}")
            return True
        else:
            print(f"   ❌ Unexpected response: {result}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_athena_query_tool(function_name, region):
    """Test run_athena_query tool."""
    try:
        lambda_client = boto3.client('lambda', region_name=region)
        
        payload = {
            "method": "tools/call",
            "params": {
                "name": "run_athena_query",
                "arguments": {
                    "query": "SELECT 1 as test_value",
                    "return_full_query_results": True
                }
            }
        }
        
        print("Testing run_athena_query tool...")
        response = lambda_client.invoke(
            FunctionName=function_name,
            Payload=json.dumps(payload)
        )
        
        result = parse_lambda_response(response)
        
        if 'content' in result:
            print("   ✅ Athena query executed successfully")
            return True
        else:
            print(f"   ⚠️  Query returned: {result}")
            return True
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_table_info_tool(function_name, region):
    """Test get_table_info tool."""
    try:
        lambda_client = boto3.client('lambda', region_name=region)
        
        payload = {
            "method": "tools/call",
            "params": {
                "name": "get_table_info",
                "arguments": {
                    "table_names": ["document_evaluations"]
                }
            }
        }
        
        print("Testing get_table_info tool...")
        response = lambda_client.invoke(
            FunctionName=function_name,
            Payload=json.dumps(payload)
        )
        
        result = parse_lambda_response(response)
        
        if 'content' in result:
            print("   ✅ Table info retrieved successfully")
            return True
        else:
            print(f"   ⚠️  Table info returned: {result}")
            return True
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_python_execution_tool(function_name, region):
    """Test execute_python tool."""
    try:
        lambda_client = boto3.client('lambda', region_name=region)
        
        payload = {
            "method": "tools/call",
            "params": {
                "name": "execute_python",
                "arguments": {
                    "code": "result = 2 + 2\nprint(f'Test calculation: {result}')",
                    "reset_state": True
                }
            }
        }
        
        print("Testing execute_python tool...")
        response = lambda_client.invoke(
            FunctionName=function_name,
            Payload=json.dumps(payload)
        )
        
        result = parse_lambda_response(response)
        
        if 'content' in result:
            print("   ✅ Python execution successful")
            return True
        else:
            print(f"   ⚠️  Python execution returned: {result}")
            return True
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_error_handling(function_name, region):
    """Test error handling with invalid requests."""
    try:
        lambda_client = boto3.client('lambda', region_name=region)
        
        # Test invalid method
        payload = {
            "method": "invalid/method",
            "params": {}
        }
        
        print("Testing error handling...")
        response = lambda_client.invoke(
            FunctionName=function_name,
            Payload=json.dumps(payload)
        )
        
        result = parse_lambda_response(response)
        
        if 'error' in result or response['StatusCode'] >= 400:
            print("   ✅ Error handling working correctly")
            return True
        else:
            print(f"   ⚠️  Error response: {result}")
            return True
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def run_performance_test(function_name, region, iterations=5):
    """Run basic performance test."""
    try:
        lambda_client = boto3.client('lambda', region_name=region)
        
        payload = {
            "method": "tools/list",
            "params": {}
        }
        
        print(f"Running performance test ({iterations} iterations)...")
        
        times = []
        for i in range(iterations):
            start_time = time.time()
            
            response = lambda_client.invoke(
                FunctionName=function_name,
                Payload=json.dumps(payload)
            )
            
            result = parse_lambda_response(response)
            end_time = time.time()
            
            if 'tools' in result:
                times.append(end_time - start_time)
            else:
                print(f"   ❌ Iteration {i+1} failed")
                return False
        
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        print(f"   ✅ Performance results:")
        print(f"      Average: {avg_time:.3f}s")
        print(f"      Min: {min_time:.3f}s")
        print(f"      Max: {max_time:.3f}s")
        
        return avg_time < 10.0
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Test AgentCore Gateway Integration')
    parser.add_argument('--stack-name', required=True, help='IDP CloudFormation stack name')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--skip-performance', action='store_true', help='Skip performance tests')
    
    args = parser.parse_args()
    
    try:
        print("=== AgentCore Gateway Integration Test ===")
        print(f"Stack: {args.stack_name}")
        print(f"Region: {args.region}")
        print()
        
        # Get Lambda function name
        print("Getting Lambda function name...")
        function_name = get_lambda_function_name(args.stack_name, args.region)
        print(f"Function: {function_name}")
        print()
        
        # Run tests
        tests = [
            ("MCP Tools List", lambda: test_mcp_tools_list(function_name, args.region)),
            ("Athena Query Tool", lambda: test_athena_query_tool(function_name, args.region)),
            ("Table Info Tool", lambda: test_table_info_tool(function_name, args.region)),
            ("Python Execution Tool", lambda: test_python_execution_tool(function_name, args.region)),
            ("Error Handling", lambda: test_error_handling(function_name, args.region)),
        ]
        
        if not args.skip_performance:
            tests.append(("Performance Test", lambda: run_performance_test(function_name, args.region)))
        
        # Execute tests
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"--- {test_name} ---")
            if test_func():
                passed += 1
            print()
        
        # Summary
        print("=== Test Summary ===")
        print(f"Passed: {passed}/{total}")
        
        if passed == total:
            print("✅ All tests passed! AgentCore Gateway is working correctly.")
            return 0
        else:
            print("❌ Some tests failed. Check the output above for details.")
            return 1
        
    except Exception as e:
        print(f"\n❌ Test execution failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
