# AgentCore Gateway Setup

This directory provides setup scripts and documentation for creating AWS Bedrock AgentCore Gateway integration with the GenAI IDP Accelerator.

## Overview

The AgentCore Gateway enables natural language analytics queries against processed document data. The analytics Lambda function is automatically deployed as part of the main IDP stack when `EnableMCPServer=true`, but the AgentCore Gateway itself must be created separately using the scripts in this directory.

## Architecture

```
AgentCore Gateway → Analytics Lambda Function → Analytics Tools
                                              ├── Amazon Athena (SQL queries)
                                              ├── AWS Glue (table metadata)
                                              └── Python execution environment
```

## Prerequisites

- Main IDP stack deployed with `EnableMCPServer=true`
- Analytics Lambda function automatically deployed (part of main stack)
- AWS Bedrock AgentCore service access
- Required Bedrock model access permissions

## Setup

After deploying the main IDP stack with `EnableMCPServer=true`, create the AgentCore Gateway:

```bash
cd options/agentcore
python3 scripts/setup_gateway.py --stack-name <your-stack-name>
```

## Configuration

The analytics Lambda function is automatically configured by the main stack with:
- `ATHENA_DATABASE`: Analytics database name
- `ATHENA_WORKGROUP`: Athena workgroup (primary)
- `QUERY_RESULTS_BUCKET`: S3 bucket for query results
- `LOG_LEVEL`: Logging level
- Least-privilege IAM permissions for Athena, Glue, S3, and KMS

## Analytics Tools

### run_athena_query

Execute SQL queries against the analytics database.

**Input:**
- `query` (string): SQL query to execute
- `return_full_query_results` (boolean): Whether to return full results

**Security Features:**
- SQL injection prevention (blocks dangerous keywords)
- Query timeout protection (5 minutes max)
- Result size limits (1000 rows max)

**Example:**
```sql
SELECT document_type, COUNT(*) as count 
FROM processed_documents 
WHERE processing_date >= '2024-01-01'
GROUP BY document_type
```

### get_table_info

Retrieve schema and metadata for database tables.

**Input:**
- `table_names` (array): List of table names to inspect

**Output:**
- Table schema (columns, types, comments)
- Storage information (location, format)
- Table parameters and metadata

### execute_python

Run Python code for data analysis in a restricted environment.

**Input:**
- `code` (string): Python code to execute
- `reset_state` (boolean): Whether to reset execution state

**Security Features:**
- Restricted imports (no file system, network, or subprocess access)
- Limited built-in functions
- Execution timeout protection
- State isolation between executions

**Available Libraries:**
- `json`: JSON processing
- `math`: Mathematical functions
- `statistics`: Statistical calculations
- `state`: Persistent state dictionary

## Testing

Validate the AgentCore Gateway integration:

```bash
python3 scripts/test_gateway.py --stack-name <your-stack-name>
```

## Usage Examples

### Quick Start

1. **Deploy main IDP stack with MCP Server enabled**:
   ```bash
   # Analytics Lambda function deploys automatically with EnableMCPServer=true
   ./publish.sh <bucket> <prefix> <region>
   # Then deploy with EnableMCPServer=true parameter
   ```

2. **Setup AgentCore Gateway**:
   ```bash
   cd options/agentcore
   python3 scripts/setup_gateway.py --stack-name <your-stack-name>
   ```

3. **Test the integration**:
   ```bash
   python3 scripts/test_gateway.py --stack-name <your-stack-name>
   ```

### Automated Setup

Use the deployment script for complete AgentCore Gateway setup:

```bash
# Complete gateway setup with validation
./scripts/deploy.sh --stack-name <your-stack-name> --region <region>

# Setup without tests (faster)
./scripts/deploy.sh --stack-name <your-stack-name> --skip-tests
```

### Natural Language Analytics

Once configured, you can ask natural language questions about your document processing data:

- "How many documents were processed last month?"
- "What are the most common document types?"
- "Show me the processing success rate by document type"
- "Calculate the average processing time for invoices"
- "Which documents had the lowest confidence scores?"
- "Generate a report of processing errors from the last week"

### Direct Tool Usage

You can also call the tools directly through the MCP protocol:

#### Query Analytics Data
```json
{
  "method": "tools/call",
  "params": {
    "name": "run_athena_query",
    "arguments": {
      "query": "SELECT document_type, COUNT(*) as count FROM document_evaluations WHERE date >= '2024-01-01' GROUP BY document_type",
      "return_full_query_results": true
    }
  }
}
```

#### Get Table Schema
```json
{
  "method": "tools/call",
  "params": {
    "name": "get_table_info",
    "arguments": {
      "table_names": ["document_evaluations", "metering"]
    }
  }
}
```

#### Execute Python Analysis
```json
{
  "method": "tools/call",
  "params": {
    "name": "execute_python",
    "arguments": {
      "code": "import statistics\nscores = [0.95, 0.87, 0.92, 0.88, 0.91]\navg_score = statistics.mean(scores)\nprint(f'Average confidence score: {avg_score:.2f}')",
      "reset_state": false
    }
  }
}
```

## Monitoring

### CloudWatch Logs

Analytics Lambda function logs are available in CloudWatch:
- Log Group: `/aws/lambda/{StackName}-agentcore-analytics`
- Retention: Configurable via main stack (default 30 days)
- Encryption: KMS encrypted using main stack key

### Metrics

Monitor these key metrics:
- Lambda invocation count and duration
- Athena query execution time and data scanned
- Error rates and timeout occurrences

## Troubleshooting

### Common Issues

**Query Timeouts:**
- Optimize SQL queries for better performance
- Consider adding indexes or partitioning
- Break large queries into smaller chunks

**Permission Errors:**
- Verify IAM roles have required permissions
- Check KMS key access for encrypted resources
- Ensure Athena workgroup configuration

**Python Execution Errors:**
- Review security restrictions on imports and functions
- Check for syntax errors in submitted code
- Verify state management between executions

### Debug Mode

Enable debug logging by setting `LogLevel=DEBUG` when deploying the main IDP stack.

## Security Considerations

### Data Access
- Lambda function has read-only access to analytics data
- All data access uses existing KMS encryption
- No direct database write permissions

### Code Execution
- Python execution is heavily restricted
- No file system or network access
- Limited to safe built-in functions and approved libraries

### Query Security
- SQL injection prevention through keyword filtering
- Query timeouts prevent resource exhaustion
- Result size limits prevent memory issues

## Cost Optimization

### Query Efficiency
- Use LIMIT clauses for large result sets
- Leverage Athena's columnar storage benefits
- Consider query result caching for repeated queries

### Lambda Optimization
- Function uses appropriate memory allocation (1024MB)
- Timeout set to balance functionality and cost (15 minutes)
- No reserved concurrency to allow scaling

## Documentation

### AgentCore Documentation
- [Architecture](./docs/architecture.md) - AgentCore Gateway architecture and integration
- [Troubleshooting](./docs/troubleshooting.md) - Common issues and solutions

### Setup Scripts
- [Gateway Setup](./scripts/setup_gateway.py) - Automated AgentCore Gateway creation
- [Integration Testing](./scripts/test_gateway.py) - Gateway validation and testing
- [Complete Setup](./scripts/deploy.sh) - End-to-end gateway setup automation

## Support

For issues or questions:
1. Check CloudWatch logs for Lambda function errors
2. Review the [troubleshooting guide](./docs/troubleshooting.md)
3. Run gateway tests: `python3 scripts/test_gateway.py`
4. Use setup scripts for validation
5. Refer to the main IDP documentation
6. Contact your AWS support team for AgentCore Gateway issues