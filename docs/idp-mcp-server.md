Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

# IDP MCP Server

## Summary

The IDP MCP Server (`idp-mcp-server`) is an optional component of the GenAI IDP solution that exposes IDP functionality to external applications through the Model Context Protocol (MCP). This server enables external systems to access document analytics, processing status, and other IDP features via a standardized API interface.

## Overview

The IDP MCP Server provides external applications with programmatic access to:

- **Document Analytics**: Query document processing data, generate visualizations, and access reporting databases
- **Processing Status**: Monitor document processing jobs and retrieve results
- **System Health**: Access error analysis and system performance metrics
- **Future Capabilities**: Document upload, configuration management, and custom extraction rules

### Key Benefits

- **External Integration**: Connect BI tools, dashboards, and custom applications to IDP data
- **Standardized API**: Uses Model Context Protocol for consistent integration patterns
- **Enterprise Security**: Built-in Cognito authentication and role-based access control
- **Serverless Architecture**: Fully managed by AWS Agent Core with automatic scaling
- **Cost Effective**: Pay-per-use pricing with no infrastructure management

## Architecture

### High-Level Design

```
External Application → Cognito Auth → IDP MCP Server → IDP Analytics Agent → Athena/DynamoDB
```

### Components

**1. AWS Agent Core MCP Server**
- Hosts the MCP server using AWS managed infrastructure
- Handles HTTP requests and MCP protocol communication
- Provides automatic scaling and load balancing

**2. Authentication Layer**
- Uses existing IDP Cognito User Pool with separate client ID
- Validates bearer tokens and enforces access controls
- Supports role-based permissions for different user types

**3. Analytics Wrapper**
- Wraps existing IDP Analytics Agent functionality
- Translates MCP requests to Analytics Agent calls
- Handles user context and data filtering

**4. IDP Integration**
- Reuses existing Analytics Agent tools and infrastructure
- Accesses same Athena databases and S3 buckets
- Maintains consistent data access patterns

### Security Model

**Authentication Flow:**
1. External application authenticates with Cognito
2. Receives bearer token for API access
3. Includes token in MCP requests
4. MCP server validates token and extracts user context
5. Filters data access based on user permissions

**Access Control:**
- Separate Cognito client ID for MCP access
- Role-based permissions (read-only analytics access)
- User-based data filtering in SQL queries
- Rate limiting and quota management

## Exposed Functionality

### Phase 1: Analytics & Status

**Document Analytics Tools:**
```python
@mcp_tool
def query_document_analytics(query: str) -> dict:
    """Execute natural language queries against document processing data"""

@mcp_tool  
def get_database_schema() -> str:
    """Get available tables and schema information"""

@mcp_tool
def run_sql_query(sql: str) -> dict:
    """Execute direct SQL queries against Athena"""

@mcp_tool
def generate_visualization(query: str, chart_type: str) -> dict:
    """Generate charts/plots from query results"""
```

**Document Status Tools:**
```python
@mcp_tool
def get_job_status(job_id: str) -> dict:
    """Get processing status for a document job"""

@mcp_tool
def list_recent_jobs(limit: int = 10) -> list:
    """List recent document processing jobs"""

@mcp_tool
def get_job_results(job_id: str) -> dict:
    """Retrieve processing results for completed jobs"""
```

### Phase 2: Processing & Configuration (Future)

**Document Processing:**
- Submit documents for processing
- Configure processing patterns
- Manage extraction schemas

**System Management:**
- Update configuration settings
- Manage user permissions
- Access system health metrics

## Implementation Design

### File Structure

```
mcp_server/
├── server.py              # MCP server entry point and request handler
├── analytics_wrapper.py   # Wrapper around existing Analytics Agent
├── status_wrapper.py      # Document status and job management
├── auth_handler.py        # Cognito token validation and user context
├── config.py              # Configuration management
├── requirements.txt       # Python dependencies
└── manifest.json          # MCP server metadata
```

### Core Components

**1. MCP Server Entry Point (`server.py`):**
```python
import os
from analytics_wrapper import AnalyticsWrapper
from auth_handler import AuthHandler

def handler(event, context):
    """Main MCP server handler"""
    auth = AuthHandler(
        user_pool_id=os.environ['COGNITO_USER_POOL_ID'],
        region=os.environ['AWS_REGION']
    )
    
    # Validate authentication
    user_context = auth.validate_request(event)
    if not user_context:
        return {"error": "Authentication failed"}
    
    # Route to appropriate wrapper
    if event.get('tool') in ['query_document_analytics', 'run_sql_query']:
        wrapper = AnalyticsWrapper(user_context)
        return wrapper.handle_request(event)
    
    return {"error": "Unknown tool"}
```

**2. Analytics Wrapper (`analytics_wrapper.py`):**
```python
from idp_common.agents.analytics.agent import create_analytics_agent

class AnalyticsWrapper:
    def __init__(self, user_context):
        self.user_context = user_context
        self.config = self._load_config()
        
    def handle_request(self, event):
        """Handle MCP requests for analytics functionality"""
        # Create analytics agent with user context
        agent = create_analytics_agent(self.config, self._get_session())
        
        # Filter queries based on user permissions
        filtered_query = self._apply_user_filters(event['query'])
        
        # Execute and return results
        return agent.invoke(filtered_query)
        
    def _apply_user_filters(self, query):
        """Apply user-based data filtering to queries"""
        # Add WHERE clauses to limit data access based on user context
        return query
```

**3. Authentication Handler (`auth_handler.py`):**
```python
import jwt
from jwt import PyJWKSClient

class AuthHandler:
    def __init__(self, user_pool_id, region):
        self.user_pool_id = user_pool_id
        self.region = region
        self.jwks_client = PyJWKSClient(
            f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"
        )
    
    def validate_request(self, event):
        """Validate Cognito token and extract user context"""
        auth_header = event.get('headers', {}).get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None
            
        token = auth_header[7:]
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            decoded_token = jwt.decode(token, signing_key.key, algorithms=["RS256"])
            return {
                'user_id': decoded_token.get('sub'),
                'username': decoded_token.get('cognito:username'),
                'groups': decoded_token.get('cognito:groups', [])
            }
        except jwt.InvalidTokenError:
            return None
```

## Build and Deployment

### Prerequisites

- Existing IDP stack deployed
- AWS CLI configured with appropriate permissions
- Python 3.11+ for local development

### Build Process

**1. Add to Existing Build Script:**
```bash
# Add to build.sh
build_mcp_server() {
    if [ "$ENABLE_MCP_SERVER" = "true" ]; then
        echo "Building IDP MCP Server..."
        cd mcp_server
        
        # Install dependencies
        pip install -r requirements.txt -t .
        
        # Create deployment package
        zip -r ../artifacts/idp-mcp-server.zip . -x "*.pyc" "__pycache__/*" "*.git*"
        
        cd ..
        echo "MCP Server build complete"
    fi
}
```

**2. CloudFormation Template Updates:**

Add to `idp-main.yaml`:
```yaml
Parameters:
  EnableIDPMCPServer:
    Type: String
    Default: "false"
    AllowedValues: ["true", "false"]
    Description: "Enable IDP MCP Server for external API access"

Conditions:
  CreateMCPServer: !Equals [!Ref EnableIDPMCPServer, "true"]

Resources:
  # MCP Server Client ID (separate from Web UI)
  IDPMCPServerClient:
    Type: AWS::Cognito::UserPoolClient
    Condition: CreateMCPServer
    Properties:
      ClientName: "IDP-MCP-Server-Client"
      UserPoolId: !Ref CognitoUserPool
      GenerateSecret: true
      AllowedOAuthFlows: ["client_credentials"]
      ExplicitAuthFlows: ["USER_PASSWORD_AUTH"]

  # MCP Server Role
  IDPMCPServerRole:
    Type: AWS::IAM::Role
    Condition: CreateMCPServer
    Properties:
      AssumeRolePolicyDocument:
        Statement:
          - Effect: Allow
            Principal:
              Service: bedrock-agentcore.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: MCPServerPolicy
          PolicyDocument:
            Statement:
              - Effect: Allow
                Action:
                  - athena:*
                  - s3:GetObject
                  - s3:PutObject
                  - dynamodb:Query
                  - dynamodb:GetItem
                Resource: "*"

  # MCP Server
  IDPMCPServer:
    Type: AWS::BedrockAgentCore::Agent
    Condition: CreateMCPServer
    Properties:
      AgentName: !Sub "${AWS::StackName}-mcp-server"
      CodeS3Bucket: !Ref DeploymentBucket
      CodeS3Key: "idp-mcp-server.zip"
      Runtime: python3.11
      Handler: server.handler
      Timeout: 300
      MemorySize: 512
      Environment:
        Variables:
          ATHENA_DATABASE: !Ref AthenaDatabase
          ATHENA_OUTPUT_LOCATION: !Sub "s3://${OutputBucket}/athena-results/"
          COGNITO_USER_POOL_ID: !Ref CognitoUserPool
          COGNITO_CLIENT_ID: !Ref IDPMCPServerClient
          AWS_REGION: !Ref AWS::Region
      ExecutionRole: !Ref IDPMCPServerRole
      AuthenticationConfiguration:
        Type: COGNITO_USER_POOL
        CognitoUserPoolId: !Ref CognitoUserPool
        CognitoClientId: !Ref IDPMCPServerClient

Outputs:
  IDPMCPServerEndpoint:
    Condition: CreateMCPServer
    Description: "IDP MCP Server endpoint for external applications"
    Value: !GetAtt IDPMCPServer.AgentEndpoint
    
  IDPMCPServerClientId:
    Condition: CreateMCPServer
    Description: "Cognito Client ID for MCP Server authentication"
    Value: !Ref IDPMCPServerClient
```

### Deployment Instructions

**1. Enable MCP Server During Deployment:**
```bash
# Deploy with MCP Server enabled
./deploy.sh --stack-name MyIDPStack --enable-mcp-server

# Or update existing stack
aws cloudformation update-stack \
  --stack-name MyIDPStack \
  --use-previous-template \
  --parameters ParameterKey=EnableIDPMCPServer,ParameterValue=true
```

**2. Create External Users:**
```bash
# Get stack outputs
MCP_CLIENT_ID=$(aws cloudformation describe-stacks \
  --stack-name MyIDPStack \
  --query 'Stacks[0].Outputs[?OutputKey==`IDPMCPServerClientId`].OutputValue' \
  --output text)

USER_POOL_ID=$(aws cloudformation describe-stacks \
  --stack-name MyIDPStack \
  --query 'Stacks[0].Outputs[?OutputKey==`CognitoUserPoolId`].OutputValue' \
  --output text)

# Create MCP user group
aws cognito-idp create-group \
  --group-name "mcp-analytics-users" \
  --user-pool-id $USER_POOL_ID \
  --description "Users with access to IDP MCP Server"

# Create external user
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username "external-analytics-user" \
  --user-attributes Name=email,Value=user@company.com \
  --message-action SUPPRESS

# Set permanent password
aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username "external-analytics-user" \
  --password "SecurePassword123!" \
  --permanent

# Add to MCP group
aws cognito-idp admin-add-user-to-group \
  --user-pool-id $USER_POOL_ID \
  --username "external-analytics-user" \
  --group-name "mcp-analytics-users"
```

**3. Test MCP Server:**
```python
import requests
import boto3

# Authenticate with Cognito
cognito = boto3.client('cognito-idp')
response = cognito.initiate_auth(
    ClientId='your-mcp-client-id',
    AuthFlow='USER_PASSWORD_AUTH',
    AuthParameters={
        'USERNAME': 'external-analytics-user',
        'PASSWORD': 'SecurePassword123!'
    }
)

access_token = response['AuthenticationResult']['AccessToken']

# Call MCP Server
mcp_endpoint = "https://your-mcp-server-endpoint/mcp"
headers = {
    'Authorization': f'Bearer {access_token}',
    'Content-Type': 'application/json'
}

# Query document analytics
payload = {
    'tool': 'query_document_analytics',
    'query': 'How many documents were processed today?'
}

response = requests.post(mcp_endpoint, json=payload, headers=headers)
print(response.json())
```

## Configuration Options

### Stack Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `EnableIDPMCPServer` | `false` | Enable/disable MCP Server deployment |
| `MCPServerMemorySize` | `512` | Memory allocation for MCP Server |
| `MCPServerTimeout` | `300` | Timeout for MCP Server requests |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ATHENA_DATABASE` | Athena database name for analytics queries |
| `ATHENA_OUTPUT_LOCATION` | S3 location for Athena query results |
| `COGNITO_USER_POOL_ID` | Cognito User Pool ID for authentication |
| `COGNITO_CLIENT_ID` | MCP Server specific client ID |

## Security Considerations

### Access Control
- Separate Cognito client ID for MCP access
- Role-based permissions with least privilege
- User-based data filtering in queries
- Rate limiting and quota management

### Data Protection
- All communication over HTTPS
- Token-based authentication
- Audit logging for all external access
- Data masking for sensitive information

### Monitoring
- CloudWatch metrics for request volume and errors
- Audit trails for user access and data queries
- Performance monitoring and alerting
- Cost tracking and optimization

## Future Enhancements

### Phase 2 Features
- Document upload and processing submission
- Configuration management APIs
- Real-time processing status updates
- Batch processing capabilities

### Phase 3 Features
- Custom extraction rule management
- Advanced analytics and reporting
- Knowledge base integration
- Multi-tenant data isolation

## Troubleshooting

### Common Issues

**Authentication Failures:**
- Verify Cognito client ID and user pool configuration
- Check token expiration and refresh logic
- Validate user group membership

**Query Failures:**
- Check Athena database permissions
- Verify S3 bucket access for query results
- Review user-based data filtering logic

**Performance Issues:**
- Monitor memory usage and timeout settings
- Optimize SQL queries for large datasets
- Consider caching for frequently accessed data

### Support Resources
- CloudWatch logs for detailed error information
- AWS Support for Agent Core issues
- IDP documentation for analytics functionality