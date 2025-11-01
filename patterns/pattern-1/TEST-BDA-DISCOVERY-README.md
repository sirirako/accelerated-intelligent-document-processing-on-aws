# BDA Discovery Lambda Local Testing

This guide explains how to test the BDA Discovery Lambda function locally with the real AWS BDA service.

## Prerequisites

1. **AWS Credentials**: Ensure your AWS credentials are configured
   ```bash
   aws configure
   # or
   export AWS_PROFILE=your-profile
   ```

2. **Python Environment**: Python 3.12+ with dependencies installed
   ```bash
   cd lib/idp_common_pkg
   pip install -e ".[extraction]"
   ```

3. **Required Environment Variables**: The test script sets defaults but you can override:
   ```bash
   export BDA_PROJECT_ARN="your-project-arn"
   export STACK_NAME="your-stack-name"
   export CONFIGURATION_TABLE_NAME="your-config-table"
   export DISCOVERY_TRACKING_TABLE="your-tracking-table"
   ```

## Running the Test

From the project root:

```bash
cd patterns/pattern-1
python test-bda-discovery.py
```

Or make it executable and run directly:

```bash
./patterns/pattern-1/test-bda-discovery.py
```

## What the Test Does

1. Loads the Lambda handler from `src/bda_discovery_function/index.py`
2. Uses a real SQS event from CloudWatch logs
3. Calls the actual AWS BDA service to create/update blueprints
4. Reports success or failure with detailed output

## Expected Output

**Success:**
```
================================================================================
Testing BDA Discovery Lambda Function
================================================================================

Environment:
  BDA_PROJECT_ARN: arn:aws:bedrock:us-west-2:...:data-automation-project/...
  STACK_NAME: IDP-BDA-3
  CONFIGURATION_TABLE_NAME: IDP-BDA-3-ConfigurationTable-...
  LOG_LEVEL: INFO

================================================================================
Invoking handler...
================================================================================

[INFO logs from the function...]

================================================================================
Result:
================================================================================
{
  "batchItemFailures": []
}

================================================================================
✅ Test completed successfully!
================================================================================
```

**Failure:**
The script will show detailed error messages and stack traces to help diagnose issues.

## Troubleshooting

### Missing deepdiff Module
```bash
pip install deepdiff>=6.0.0
```

### AWS Permissions
Ensure your AWS credentials have permissions for:
- `bedrock:GetDataAutomationProject`
- `bedrock:ListBlueprints`
- `bedrock:GetBlueprint`
- `bedrock:CreateBlueprint`
- `bedrock:UpdateBlueprint`
- `bedrock:CreateBlueprintVersion`
- `dynamodb:GetItem` (for configuration table)

### Invalid Blueprint Schema Errors
If you see validation errors, check the CloudWatch logs output in the test for the actual schema being sent to BDA. Compare with working blueprints in your project.

## Modifying the Test

You can modify `test-bda-discovery.py` to:
- Change environment variables
- Use different test events
- Add more detailed logging
- Test specific configuration scenarios
