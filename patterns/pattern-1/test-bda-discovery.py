#!/usr/bin/env python3
"""
Local test script for BDA Discovery Lambda function.
Tests the function with real AWS BDA service.
"""

import json
import os
import sys
from pathlib import Path

# Add the Lambda source to Python path
lambda_dir = Path(__file__).parent / "src" / "bda_discovery_function"
sys.path.insert(0, str(lambda_dir))

# Add idp_common to path
lib_dir = Path(__file__).parent.parent.parent / "lib" / "idp_common_pkg"
sys.path.insert(0, str(lib_dir))

# Set up environment variables before importing the handler
os.environ.setdefault("AWS_REGION", "us-west-2")
os.environ.setdefault("BDA_PROJECT_ARN", "arn:aws:bedrock:us-west-2:912625584728:data-automation-project/af1ddcfacc2d")
os.environ.setdefault("STACK_NAME", "IDP-BDA-3")
os.environ.setdefault("CONFIGURATION_TABLE_NAME", "IDP-BDA-3-ConfigurationTable-1XUJJGXYBUWCE")
os.environ.setdefault("DISCOVERY_TRACKING_TABLE", "IDP-BDA-3-DiscoveryTrackingTable")
os.environ.setdefault("METRIC_NAMESPACE", "IDP-BDA-3")
os.environ.setdefault("LOG_LEVEL", "DEBUG")  # Set to DEBUG for more details

# Now import the handler
from index import handler


def main():
    """Run the test."""
    # Test event from CloudWatch logs
    test_event = {
        "Records": [
            {
                "messageId": "3eaa9625-b753-4618-8ad6-908bc5b35cf8",
                "receiptHandle": "test-receipt-handle",
                "body": json.dumps({
                    "eventType": "CONFIGURATION_UPDATED",
                    "configurationKey": "Custom",
                    "timestamp": "2025-11-01T19:31:40.107471Z",
                    "data": {
                        "configurationKey": "Custom"
                    }
                }),
                "attributes": {
                    "ApproximateReceiveCount": "1",
                    "SentTimestamp": "1762025500193",
                    "SenderId": "test-sender",
                    "ApproximateFirstReceiveTimestamp": "1762025500211"
                },
                "messageAttributes": {
                    "configurationKey": {
                        "stringValue": "Custom",
                        "dataType": "String"
                    },
                    "eventType": {
                        "stringValue": "CONFIGURATION_UPDATED",
                        "dataType": "String"
                    }
                },
                "md5OfBody": "test-md5",
                "eventSource": "aws:sqs",
                "eventSourceARN": "arn:aws:sqs:us-west-2:912625584728:IDP-BDA-3-ConfigurationQueue-4idK3VtGNW2Z",
                "awsRegion": "us-west-2"
            }
        ]
    }

    # Mock context
    class Context:
        function_name = "BDADiscoveryFunction"
        function_version = "$LATEST"
        invoked_function_arn = "arn:aws:lambda:us-west-2:912625584728:function:BDADiscoveryFunction"
        memory_limit_in_mb = 4096
        aws_request_id = "test-request-id"
        log_group_name = "/aws/lambda/BDADiscoveryFunction"
        log_stream_name = "test-stream"

        @staticmethod
        def get_remaining_time_in_millis():
            return 900000

    context = Context()

    print("=" * 80)
    print("Testing BDA Discovery Lambda Function")
    print("=" * 80)
    print(f"\nEnvironment:")
    print(f"  BDA_PROJECT_ARN: {os.environ.get('BDA_PROJECT_ARN')}")
    print(f"  STACK_NAME: {os.environ.get('STACK_NAME')}")
    print(f"  CONFIGURATION_TABLE_NAME: {os.environ.get('CONFIGURATION_TABLE_NAME')}")
    print(f"  LOG_LEVEL: {os.environ.get('LOG_LEVEL')}")
    print("\n" + "=" * 80)
    print("Invoking handler...")
    print("=" * 80 + "\n")

    try:
        result = handler(test_event, context)
        
        print("\n" + "=" * 80)
        print("Result:")
        print("=" * 80)
        print(json.dumps(result, indent=2))
        print("\n" + "=" * 80)
        print("✅ Test completed successfully!")
        print("=" * 80)
        
        # Check for batch item failures
        if result.get("batchItemFailures"):
            print("\n⚠️  Warning: Batch item failures detected:")
            print(json.dumps(result["batchItemFailures"], indent=2))
            return 1
        
        return 0
        
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ Test failed with error:")
        print("=" * 80)
        print(f"{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())
