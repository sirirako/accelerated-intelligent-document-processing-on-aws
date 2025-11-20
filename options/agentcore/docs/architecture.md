# AgentCore Gateway Architecture

## Overview

The AgentCore Gateway component integrates AWS Bedrock AgentCore Gateway with the GenAI IDP Accelerator to provide natural language analytics capabilities over processed document data.

## Architecture Diagram

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   Natural       │    │   AgentCore      │    │   Analytics         │
│   Language      │───▶│   Gateway        │───▶│   Lambda Function   │
│   Query         │    │   (AWS Bedrock)  │    │   (MCP Protocol)    │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
                                                          │
                                                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Analytics Tools                                 │
├─────────────────┬─────────────────┬─────────────────────────────────┤
│  run_athena_    │  get_table_     │  execute_python                 │
│  query          │  info           │                                 │
│                 │                 │                                 │
│ ┌─────────────┐ │ ┌─────────────┐ │ ┌─────────────────────────────┐ │
│ │   Amazon    │ │ │   AWS Glue  │ │ │   Restricted Python         │ │
│ │   Athena    │ │ │   Catalog   │ │ │   Execution Environment     │ │
│ │             │ │ │             │ │ │                             │ │
│ └─────────────┘ │ └─────────────┘ │ └─────────────────────────────┘ │
└─────────────────┴─────────────────┴─────────────────────────────────┘
          │                   │                           │
          ▼                   ▼                           ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────────────┐
│   Analytics     │ │   Table Schema  │ │   In-Memory State           │
│   Database      │ │   & Metadata    │ │   Management                │
│   (Glue)        │ │                 │ │                             │
└─────────────────┘ └─────────────────┘ └─────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Data Sources                                    │
├─────────────────┬─────────────────┬─────────────────────────────────┤
│  Document       │  Section        │  Attribute                      │
│  Evaluations    │  Evaluations    │  Evaluations                    │
│                 │                 │                                 │
│  • Accuracy     │  • Section-     │  • Field-level                  │
│  • Precision    │    level        │    accuracy                     │
│  • Recall       │    metrics      │  • Confidence                   │
│  • F1 Score     │  • Document     │    scores                       │
│                 │    sections     │  • Extraction                   │
│                 │                 │    results                      │
└─────────────────┴─────────────────┴─────────────────────────────────┘
```

## Component Architecture

### 1. AgentCore Gateway (AWS Bedrock)
- **Purpose**: Provides natural language interface for analytics queries
- **Protocol**: Model Context Protocol (MCP) for tool integration
- **Authentication**: Integrated with existing Cognito User Pool
- **Scaling**: Managed by AWS Bedrock service

### 2. Analytics Lambda Function
- **Runtime**: Python 3.11
- **Memory**: 1024 MB
- **Timeout**: 15 minutes
- **Protocol**: MCP server implementation
- **Security**: Least-privilege IAM permissions

### 3. Analytics Tools

#### run_athena_query
```python
# Tool specification
{
    "name": "run_athena_query",
    "description": "Execute SQL queries against analytics database",
    "inputSchema": {
        "query": "string",           # SQL query to execute
        "return_full_query_results": "boolean"  # Return full results or summary
    }
}
```

**Data Flow:**
1. Receive SQL query from AgentCore Gateway
2. Validate query for security (SQL injection prevention)
3. Execute query using Amazon Athena
4. Wait for completion with timeout handling
5. Return results or execution summary

#### get_table_info
```python
# Tool specification
{
    "name": "get_table_info", 
    "description": "Get schema and metadata for database tables",
    "inputSchema": {
        "table_names": ["string"]   # Array of table names
    }
}
```

**Data Flow:**
1. Receive table names from AgentCore Gateway
2. Query AWS Glue Catalog for table metadata
3. Extract schema, columns, and storage information
4. Return structured table information

#### execute_python
```python
# Tool specification
{
    "name": "execute_python",
    "description": "Execute Python code in restricted environment", 
    "inputSchema": {
        "code": "string",           # Python code to execute
        "reset_state": "boolean"    # Reset execution state
    }
}
```

**Data Flow:**
1. Receive Python code from AgentCore Gateway
2. Validate code for security restrictions
3. Execute in restricted environment (no file/network access)
4. Capture output and return results

## Security Architecture

### 1. Network Security
- **VPC**: Lambda function runs in AWS managed VPC
- **Encryption**: All data encrypted in transit and at rest
- **Access Control**: IAM-based resource access

### 2. Authentication & Authorization
- **Gateway Access**: Cognito User Pool authentication
- **Lambda Execution**: Service-linked IAM role
- **Resource Access**: Least-privilege permissions

### 3. Input Validation
- **SQL Injection Prevention**: Keyword filtering and validation
- **Python Security**: Restricted execution environment
- **MCP Protocol**: Schema validation for all requests

### 4. Data Protection
- **KMS Encryption**: All data encrypted with customer-managed keys
- **Access Logging**: CloudWatch logs for audit trail
- **Data Retention**: Configurable retention policies

## Integration Points

### 1. Main IDP Stack Integration
```yaml
# Conditional deployment
Condition: CreateMCPServer  # Only when EnableMCPServer=true

# Parameter passing
Parameters:
  - StackName: !Ref AWS::StackName
  - CognitoUserPoolId: !Ref UserPool  
  - AnalyticsDatabase: !Ref ReportingDatabase
  - ReportingBucket: !Ref ReportingBucket
  - EncryptionKeyArn: !GetAtt CustomerManagedEncryptionKey.Arn
```

### 2. Analytics Database Integration
```sql
-- Available tables for querying
- document_evaluations     -- Document-level metrics
- section_evaluations      -- Section-level metrics  
- attribute_evaluations    -- Attribute-level metrics
- metering                 -- Usage and cost data
- document_sections_*      -- Dynamic document content tables
```

### 3. Build System Integration
```bash
# Automatic discovery by publish.sh
options/agentcore/
├── template.yaml      # CloudFormation template
├── buildspec.yml      # SAM build configuration
├── .checksum          # Build system tracking
└── src/               # Lambda source code
```

## Deployment Architecture

### 1. Nested Stack Pattern
```yaml
# Main template integration
AGENTCORESTACK:
  Type: AWS::CloudFormation::Stack
  Condition: CreateMCPServer
  Properties:
    TemplateURL: ./options/agentcore/.aws-sam/packaged.yaml
```

### 2. Resource Dependencies
```
Main Stack Resources:
├── UserPool (Cognito)           → AgentCore Authentication
├── ReportingDatabase (Glue)     → Analytics Data Source  
├── ReportingBucket (S3)         → Query Results Storage
├── CustomerManagedKey (KMS)     → Encryption
└── AGENTCORESTACK (Nested)      → AgentCore Components
    ├── AnalyticsLambdaFunction
    ├── AnalyticsLambdaRole
    └── AnalyticsLambdaLogGroup
```

### 3. Build Process
```bash
# Automatic build workflow
1. publish.sh discovers options/agentcore/
2. SAM builds Lambda function package
3. CloudFormation deploys nested stack
4. Lambda function ready for gateway configuration
```

## Performance Characteristics

### 1. Scalability
- **Lambda Concurrency**: Default scaling (up to account limits)
- **Athena Queries**: Parallel execution supported
- **Gateway Requests**: Managed by AWS Bedrock service

### 2. Performance Targets
- **Cold Start**: < 10 seconds
- **Query Response**: < 30 seconds (typical analytics queries)
- **Tool Execution**: < 5 seconds (simple operations)

### 3. Resource Limits
- **Lambda Memory**: 1024 MB
- **Lambda Timeout**: 15 minutes
- **Athena Results**: 1000 rows max (configurable)
- **Python Execution**: Restricted environment, no external access

## Monitoring & Observability

### 1. CloudWatch Metrics
- Lambda invocation count and duration
- Athena query execution time and data scanned
- Error rates and timeout occurrences

### 2. CloudWatch Logs
- Lambda function execution logs
- MCP protocol request/response logging
- Error details and stack traces

### 3. X-Ray Tracing
- End-to-end request tracing (if enabled in main stack)
- Performance bottleneck identification
- Service dependency mapping

## Cost Optimization

### 1. Lambda Costs
- Pay-per-invocation pricing
- Memory allocation optimized for workload
- No reserved concurrency (scales on demand)

### 2. Athena Costs
- Pay-per-query pricing based on data scanned
- Query result caching for repeated queries
- Partition pruning for efficient queries

### 3. Storage Costs
- S3 storage for query results (lifecycle policies)
- CloudWatch logs retention (configurable)
- No additional storage overhead

## Disaster Recovery

### 1. Multi-Region Support
- Component can be deployed in any AWS region
- No region-specific dependencies
- Cross-region replication supported via main stack

### 2. Backup & Recovery
- Lambda function code stored in S3 (via SAM)
- CloudFormation templates enable infrastructure recreation
- No persistent state in Lambda function

### 3. Failure Handling
- Automatic Lambda retry on transient failures
- Athena query timeout and error handling
- Graceful degradation for analytics unavailability