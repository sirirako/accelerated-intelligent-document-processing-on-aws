# AgentCore Gateway Troubleshooting Guide

## Common Issues and Solutions

### Deployment Issues

#### Issue: AgentCore stack not found
```
Error: AgentCore nested stack not found. Ensure EnableMCPServer=true in main stack.
```

**Cause**: The main IDP stack was deployed without enabling the MCP Server.

**Solution**:
1. Update the main stack with `EnableMCPServer=true`:
   ```bash
   aws cloudformation update-stack \
     --stack-name your-idp-stack \
     --use-previous-template \
     --parameters ParameterKey=EnableMCPServer,ParameterValue=true
   ```
2. Wait for stack update to complete
3. Re-run the AgentCore setup

#### Issue: Lambda function not found in outputs
```
Error: Lambda function not found in AgentCore stack outputs
```

**Cause**: The nested stack deployment failed or is incomplete.

**Solution**:
1. Check the nested stack status:
   ```bash
   aws cloudformation describe-stacks --stack-name <nested-stack-id>
   ```
2. Review CloudFormation events for errors:
   ```bash
   aws cloudformation describe-stack-events --stack-name <nested-stack-id>
   ```
3. Common fixes:
   - Verify IAM permissions for stack deployment
   - Check resource limits (Lambda functions, IAM roles)
   - Ensure all required parameters are provided

### Lambda Function Issues

#### Issue: Lambda function timeout
```
Error: Task timed out after 900.00 seconds
```

**Cause**: Long-running Athena queries or Python execution.

**Solution**:
1. Optimize Athena queries:
   ```sql
   -- Add LIMIT clause for large result sets
   SELECT * FROM document_evaluations LIMIT 1000;
   
   -- Use partition pruning
   SELECT * FROM document_evaluations WHERE date >= '2024-01-01';
   ```
2. Break complex Python code into smaller chunks
3. Consider increasing Lambda timeout (max 15 minutes)

#### Issue: Memory limit exceeded
```
Error: Runtime exited with error: signal: killed Runtime.ExitError
```

**Cause**: Lambda function ran out of memory processing large datasets.

**Solution**:
1. Increase Lambda memory allocation in template:
   ```yaml
   AnalyticsLambdaFunction:
     Properties:
       MemorySize: 2048  # Increase from 1024
   ```
2. Optimize data processing:
   - Use streaming for large results
   - Process data in batches
   - Limit query result sizes

### MCP Protocol Issues

#### Issue: Invalid MCP request format
```
Error: Missing 'method' in request
```

**Cause**: Malformed MCP protocol request.

**Solution**:
Ensure requests follow MCP protocol format:
```json
{
  "method": "tools/list",
  "params": {}
}
```

#### Issue: Tool not found
```
Error: Unknown tool: invalid_tool_name
```

**Cause**: Requesting a tool that doesn't exist.

**Solution**:
1. List available tools:
   ```json
   {"method": "tools/list", "params": {}}
   ```
2. Use correct tool names:
   - `run_athena_query`
   - `get_table_info`
   - `execute_python`

### Athena Query Issues

#### Issue: Query execution failed
```
Error: SYNTAX_ERROR: line 1:1: mismatched input 'INVALID'
```

**Cause**: Invalid SQL syntax in Athena query.

**Solution**:
1. Validate SQL syntax before execution
2. Use Athena-compatible SQL:
   ```sql
   -- Correct: Use double quotes for identifiers
   SELECT "document_id" FROM document_evaluations;
   
   -- Incorrect: Single quotes for identifiers
   SELECT 'document_id' FROM document_evaluations;
   ```
3. Check table and column names exist

#### Issue: Permission denied accessing table
```
Error: Access Denied: User does not have permission to access table
```

**Cause**: Lambda function lacks permissions to access Glue tables.

**Solution**:
1. Verify IAM role permissions in template:
   ```yaml
   - Effect: Allow
     Action:
       - glue:GetTable
       - glue:GetTables
       - glue:GetDatabase
     Resource:
       - !Sub "arn:aws:glue:${AWS::Region}:${AWS::AccountId}:table/${AnalyticsDatabase}/*"
   ```
2. Check table exists in correct database
3. Verify KMS permissions for encrypted data

### Python Execution Issues

#### Issue: Dangerous operation detected
```
Error: Dangerous operation detected: os
```

**Cause**: Python code contains restricted operations.

**Solution**:
Use only allowed operations:
```python
# Allowed: Basic calculations and safe libraries
import json
import math
import statistics

result = statistics.mean([1, 2, 3, 4, 5])
print(f"Average: {result}")

# Not allowed: File system, network, subprocess
import os  # ❌ Blocked
import subprocess  # ❌ Blocked
```

#### Issue: Python execution timeout
```
Error: Python execution failed: execution timeout
```

**Cause**: Python code takes too long to execute.

**Solution**:
1. Optimize code for performance
2. Avoid infinite loops
3. Use efficient algorithms for data processing

### Gateway Configuration Issues

#### Issue: Gateway creation failed
```
Error: Failed to create AgentCore Gateway
```

**Cause**: AgentCore Gateway service not available or configuration error.

**Solution**:
1. Verify AWS Bedrock AgentCore service availability in your region
2. Check AWS service quotas and limits
3. Ensure proper IAM permissions for gateway creation
4. Use AWS Console to create gateway manually if needed

#### Issue: Gateway authentication failed
```
Error: Authentication failed for gateway access
```

**Cause**: Cognito authentication not properly configured.

**Solution**:
1. Verify Cognito User Pool configuration
2. Check user permissions and group membership
3. Ensure gateway is configured with correct User Pool ARN

## Debugging Steps

### 1. Check Lambda Function Logs
```bash
# View recent logs
aws logs tail /aws/lambda/your-stack-agentcore-analytics --follow

# Search for specific errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/your-stack-agentcore-analytics \
  --filter-pattern "ERROR"
```

### 2. Test Lambda Function Directly
```bash
# Test tools/list endpoint
aws lambda invoke \
  --function-name your-stack-agentcore-analytics \
  --payload '{"method": "tools/list", "params": {}}' \
  response.json

cat response.json
```

### 3. Validate CloudFormation Stack
```bash
# Check main stack status
aws cloudformation describe-stacks --stack-name your-idp-stack

# Check nested stack status
aws cloudformation describe-stacks --stack-name <agentcore-stack-id>

# Review stack events for errors
aws cloudformation describe-stack-events --stack-name your-idp-stack
```

### 4. Test Athena Connectivity
```bash
# Test Athena query directly
aws athena start-query-execution \
  --query-string "SELECT 1 as test" \
  --result-configuration OutputLocation=s3://your-reporting-bucket/test/ \
  --work-group primary
```

### 5. Verify IAM Permissions
```bash
# Check Lambda function role
aws iam get-role --role-name your-stack-AgentCore-Analytics-Role

# List attached policies
aws iam list-attached-role-policies --role-name your-stack-AgentCore-Analytics-Role
```

## Performance Optimization

### 1. Query Optimization
```sql
-- Use partition pruning
SELECT * FROM document_evaluations 
WHERE date >= '2024-01-01' AND date < '2024-02-01';

-- Limit result sets
SELECT document_id, accuracy FROM document_evaluations LIMIT 100;

-- Use aggregations instead of raw data
SELECT document_type, AVG(accuracy) as avg_accuracy 
FROM document_evaluations 
GROUP BY document_type;
```

### 2. Lambda Optimization
```yaml
# Increase memory for better performance
AnalyticsLambdaFunction:
  Properties:
    MemorySize: 2048
    
# Enable provisioned concurrency for consistent performance
ProvisionedConcurrencyConfig:
  ProvisionedConcurrencyUnits: 5
```

### 3. Caching Strategies
```python
# Cache query results in Lambda memory
query_cache = {}

def cached_athena_query(query):
    if query in query_cache:
        return query_cache[query]
    
    result = execute_athena_query(query)
    query_cache[query] = result
    return result
```

## Monitoring and Alerting

### 1. CloudWatch Alarms
```yaml
# Lambda error rate alarm
LambdaErrorAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    MetricName: Errors
    Namespace: AWS/Lambda
    Statistic: Sum
    Period: 300
    EvaluationPeriods: 2
    Threshold: 5
    ComparisonOperator: GreaterThanThreshold
```

### 2. Custom Metrics
```python
# Add custom metrics in Lambda function
import boto3
cloudwatch = boto3.client('cloudwatch')

cloudwatch.put_metric_data(
    Namespace='AgentCore/Analytics',
    MetricData=[
        {
            'MetricName': 'QueryExecutionTime',
            'Value': execution_time_ms,
            'Unit': 'Milliseconds'
        }
    ]
)
```

### 3. Log Analysis
```bash
# Create CloudWatch Insights queries
aws logs start-query \
  --log-group-name /aws/lambda/your-stack-agentcore-analytics \
  --start-time $(date -d '1 hour ago' +%s) \
  --end-time $(date +%s) \
  --query-string 'fields @timestamp, @message | filter @message like /ERROR/'
```

## Getting Help

### 1. Enable Debug Logging
Set `LogLevel=DEBUG` in the main stack parameters for detailed logging.

### 2. Run Integration Tests
```bash
cd options/agentcore
python3 test_integration.py
```

### 3. Use Test Scripts
```bash
# Test specific functionality
python3 scripts/test_gateway.py --stack-name your-stack --region us-east-1

# Test with performance metrics
python3 scripts/test_gateway.py --stack-name your-stack --region us-east-1
```

### 4. Contact Support
If issues persist:
1. Collect CloudWatch logs and error messages
2. Document steps to reproduce the issue
3. Include stack configuration and parameters
4. Contact AWS Support or create GitHub issue with details