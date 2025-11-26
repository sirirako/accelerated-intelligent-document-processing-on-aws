Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

# AgentCore Integration

The GenAI IDP solution provides AgentCore integration that enables external applications to access IDP functionality through AWS Bedrock AgentCore Gateway using the Model Context Protocol (MCP). This allows third-party applications to query processed document data and perform analytics operations through natural language interfaces.

## Overview

The AgentCore integration exposes IDP capabilities to external applications by:

- **Analytics Gateway**: Provides natural language access to processed document analytics data
- **Secure Authentication**: Uses AWS Cognito OAuth 2.0 for secure external application access
- **MCP Protocol**: Implements Model Context Protocol for standardized tool integration
- **Real-time Queries**: Enables external applications to query document processing results in real-time
- **Extensible Architecture**: Designed to support additional IDP functionality in future releases

## External Application Integration

External applications can integrate with the IDP system through the AgentCore Gateway by:

1. **Authentication**: Obtaining OAuth tokens from the IDP's Cognito User Pool
2. **Gateway Connection**: Connecting to the AgentCore Gateway endpoint
3. **Tool Discovery**: Discovering available analytics tools via MCP protocol
4. **Query Execution**: Executing natural language queries against processed document data

### Integration Flow

```
External App → Cognito Auth → AgentCore Gateway → Analytics Lambda → IDP Data
```

## Enabling and Disabling the Feature

### During Stack Deployment

The AgentCore integration is controlled by the `EnableAgentCore` parameter:

**Enable AgentCore Integration:**
```yaml
EnableAgentCore: 'true'  # Default value
```

**Disable AgentCore Integration:**
```yaml
EnableAgentCore: 'false'
```

When enabled, the stack automatically creates:
- AgentCore Gateway Manager Lambda function
- AgentCore Analytics Lambda function
- External App Client in Cognito User Pool
- Required IAM roles and policies
- AgentCore Gateway resource

When disabled, these resources are not created, reducing deployment complexity and costs.

## Current Capabilities

### Analytics Agent

The current implementation provides an Analytics Agent that processes natural language queries about processed document data. The agent follows the AgentCore schema and provides a single tool interface:

#### search_genaiidp
Provides information from the GenAI Intelligent Document Processing System and answers user questions using natural language queries.

**Input Schema:**
- `query` (string, required): Natural language question about processed documents or analytics data

**Capabilities:**
- Query processed document statistics and metadata
- Analyze document processing trends and patterns
- Retrieve information about document types, processing status, and results
- Generate analytics reports based on natural language requests

**Example Queries:**
- "How many documents were processed last month?"
- "What are the most common document types?"
- "Show me the processing success rate by document type"
- "Which documents had the lowest confidence scores?"
- "Generate a report of processing errors from the last week"

## Implementation Details

### Architecture Components

1. **AgentCore Gateway Manager Lambda**
   - Creates and manages the AgentCore Gateway
   - Handles CloudFormation custom resource lifecycle
   - Configures JWT authorization using Cognito

2. **AgentCore Analytics Lambda**
   - Implements MCP protocol following AgentCore schema
   - Processes natural language queries via search_genaiidp tool
   - Translates queries to appropriate backend operations
   - Returns structured responses in natural language

3. **AgentCore Gateway**
   - AWS Bedrock AgentCore Gateway resource
   - Routes requests between external applications and analytics Lambda
   - Handles authentication and authorization

### Authentication Flow

1. **External Application** requests access token from Cognito
2. **Cognito User Pool** validates credentials and returns JWT token
3. **External Application** calls AgentCore Gateway with Bearer token
4. **AgentCore Gateway** validates JWT token against Cognito
5. **Analytics Lambda** processes the request and returns results

### Data Access

The Analytics Lambda has read-only access to:
- **Analytics Database**: Glue catalog with processed document metadata
- **Reporting Bucket**: S3 bucket containing analytics data and query results
- **Configuration Tables**: DynamoDB tables with system configuration
- **Tracking Tables**: DynamoDB tables with processing status

## Cognito User Pool Utilization

### User Pool Configuration

The IDP solution creates a Cognito User Pool with:
- **Domain**: Auto-generated unique domain (e.g., `stack-name-timestamp.auth.region.amazoncognito.com`)
- **Password Policy**: Configurable security requirements
- **User Management**: Admin-managed user creation
- **OAuth Flows**: Authorization code flow for external applications

### External App Client

When AgentCore is enabled, an additional Cognito User Pool Client is created:

**Client Configuration:**
- **Client Name**: "External-App-Client"
- **Client Secret**: Generated automatically
- **Auth Flows**: USER_PASSWORD_AUTH, ADMIN_USER_PASSWORD_AUTH, REFRESH_TOKEN_AUTH
- **OAuth Flows**: Authorization code flow
- **OAuth Scopes**: openid, email, profile
- **Callback URLs**: 
  - CloudFront distribution URL
  - QuickSight OAuth callback
  - Cognito User Pool domain

### Token Management

External applications can obtain tokens using:

**Client Credentials Flow:**
```bash
curl -X POST <ExternalAppTokenURL> \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=<ExternalAppClientId>&client_secret=<ExternalAppClientSecret>"
```

**User Authentication Flow:**
```bash
# Step 1: Get authorization code
<ExternalAppAuthorizationURL>?
  response_type=code&
  client_id=<ExternalAppClientId>&
  redirect_uri=CALLBACK_URL&
  scope=openid+email+profile

# Step 2: Exchange code for tokens
curl -X POST <ExternalAppTokenURL> \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&client_id=<ExternalAppClientId>&client_secret=<ExternalAppClientSecret>&code=AUTH_CODE&redirect_uri=CALLBACK_URL"
```

## Output Parameters

When AgentCore integration is enabled, the CloudFormation stack provides the following outputs required for external application integration:

### AgentCore Gateway Outputs

- **`AgentCoreGatewayUrl`**: The HTTPS endpoint for the AgentCore Gateway
  - Format: `https://gateway-id.gateway.bedrock-agentcore.region.amazonaws.com/mcp`
  - Example: `https://analyticagentcoregateway-0kxp69ljko.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp`
  - Required for external applications to connect to the gateway via MCP protocol

- **`AgentCoreGatewayId`**: Unique identifier for the AgentCore Gateway
  - Used for management and monitoring operations

- **`AgentCoreGatewayArn`**: Full ARN of the AgentCore Gateway resource
  - Used for IAM policies and cross-account access

### Cognito Outputs

- **`ExternalAppClientId`**: Cognito User Pool Client ID for external applications
  - Required for OAuth authentication flows
  - Used in token requests and API calls

- **`ExternalAppClientSecret`**: Cognito User Pool Client Secret
  - Required for client authentication in OAuth flows
  - Should be securely stored and rotated regularly

- **`ExternalAppUserPoolId`**: Cognito User Pool ID for external application authentication
  - Required for token validation and user management
  - Used by external applications for authentication setup

- **`ExternalAppTokenURL`**: OAuth token endpoint URL
  - Format: `https://domain-name.auth.region.amazoncognito.com/oauth2/token`
  - Used for obtaining access tokens via OAuth flows

- **`ExternalAppAuthorizationURL`**: OAuth authorization endpoint URL
  - Format: `https://domain-name.auth.region.amazoncognito.com/oauth2/authorize`
  - Used for initiating OAuth authorization code flows

## Usage Examples

### External Application Setup

```python
import requests
import json

# Configuration from CloudFormation outputs
GATEWAY_URL = "<AgentCoreGatewayUrl>"  # From stack outputs
CLIENT_ID = "<ExternalAppClientId>"  # From stack outputs
CLIENT_SECRET = "<ExternalAppClientSecret>"  # From stack outputs
TOKEN_URL = "<ExternalAppTokenURL>"  # From stack outputs

# Get access token
token_response = requests.post(
    TOKEN_URL,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
)
access_token = token_response.json()["access_token"]

# Query analytics data using natural language
query_request = {
    "method": "tools/call",
    "params": {
        "name": "search_genaiidp",
        "arguments": {
            "query": "How many documents have been processed in total?"
        }
    }
}

response = requests.post(
    GATEWAY_URL,
    headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    },
    json=query_request
)

result = response.json()
print(f"Analytics result: {result}")
```

### Additional Query Examples

External applications can send various natural language queries:

```python
# Document processing trends
trend_query = {
    "method": "tools/call",
    "params": {
        "name": "search_genaiidp",
        "arguments": {
            "query": "Show me document processing trends by month for the last 6 months"
        }
    }
}

# Document type analysis
type_query = {
    "method": "tools/call",
    "params": {
        "name": "search_genaiidp",
        "arguments": {
            "query": "What are the top 5 most common document types and their processing success rates?"
        }
    }
}

for query in [trend_query, type_query]:
    response = requests.post(GATEWAY_URL, headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}, json=query)
    print(response.json())al language
query_request = {
    "method": "tools/call",
    "params": {
        "name": "search_genaiidp",
        "arguments": {
            "query": "How many documents have been processed in total?"
        }
    }
}

response = requests.post(
    GATEWAY_URL,
    headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    },
    json=query_request
)

result = response.json()
print(f"Analytics result: {result}")
```

### Additional Query Examples

External applications can send various natural language queries:

```python
# Document processing trends
trend_query = {
    "method": "tools/call",
    "params": {
        "name": "search_genaiidp",
        "arguments": {
            "query": "Show me document processing trends by month for the last 6 months"
        }
    }
}

# Document type analysis
type_query = {
    "method": "tools/call",
    "params": {
        "name": "search_genaiidp",
        "arguments": {
            "query": "What are the top 5 most common document types and their processing success rates?"
        }
    }
}

for query in [trend_query, type_query]:
    response = requests.post(GATEWAY_URL, headers=headers, json=query)
    print(response.json())
```