---
title: "IDP MCP Connector"
---

Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

# IDP MCP Connector

## 1. Overview

The **IDP MCP Connector** (`idp_mcp_connector`) is a lightweight local Python tool that bridges IDE-based AI coding assistants — such as [Cline](https://github.com/cline/cline) (VS Code) and [Kiro](https://kiro.dev) — to the IDP Accelerator's remote MCP Server running in AWS via Amazon Bedrock AgentCore Gateway.

### Why the Connector Exists

The IDP Accelerator exposes document intelligence capabilities (processing, analytics, results retrieval) through a remote MCP Server hosted on Amazon Bedrock AgentCore Gateway. This server requires **OAuth 2.0 authentication** using pre-registered credentials (client ID and client secret) issued by Amazon Cognito.

IDE tools like Cline support connecting to remote MCP servers, but their OAuth implementation follows the **OAuth 2.1 with Dynamic Client Registration** specification (RFC 7591). This standard requires the client to dynamically register itself with the authorization server — a capability that Amazon Cognito does not support by default. When Cline attempts to connect directly to the AgentCore Gateway, it receives `HTTP 403 Dynamic client registration failed`.

The IDP MCP Connector solves this by:

1. Running **locally** on the developer's machine as a standard stdio MCP server (which Cline and Kiro fully support without any OAuth complexity)
2. Handling **Cognito authentication** internally using the pre-registered client credentials
3. **Dynamically discovering** all available tools from the remote MCP Server and re-exposing them locally
4. **Transparently forwarding** all tool calls from the IDE to the remote server with proper authentication

### Key Features

- **Zero-code integration** — developers use IDP tools directly from their IDE chat interface
- **Automatic token management** — Cognito OAuth tokens are acquired and refreshed transparently
- **Dynamic tool discovery** — tools are fetched from the remote server at startup; no hardcoded tool definitions
- **Cross-platform** — works on macOS, Windows, and Linux
- **Multi-IDE** — works with Cline, Kiro, or any MCP client that supports stdio transport
- **Future-proof** — automatically picks up new tools added to the MCP Server without code changes

---

## 2. Architecture Design

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Developer's Machine                                                     │
│                                                                          │
│  ┌──────────────┐   stdio (MCP)   ┌──────────────────────────────────┐  │
│  │   Cline      │ ◄─────────────► │       idp_mcp_connector          │  │
│  │   or Kiro    │                  │       (local Python process)     │  │
│  └──────────────┘                  └──────────────────────────────────┘  │
│                                                    │                     │
│                                    ┌───────────────┘                     │
│                                    │  1. Cognito Auth (client_credentials)│
│                                    ▼                                     │
│                           ┌────────────────┐                            │
│                           │ AWS Cognito    │                            │
│                           │ Token Endpoint │                            │
│                           └────────────────┘                            │
└────────────────────────────────────────────────────────────────────────-┘
                                    │
                                    │  2. HTTPS + Bearer Token
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  AWS Cloud                                                               │
│                                                                          │
│  ┌──────────────────────┐       ┌──────────────────────────────────────┐ │
│  │  AgentCore Gateway   │ ────► │  agentcore_mcp_handler       │ │
│  │  (IDP MCP Server)    │       │  (AWS Lambda)                        │ │
│  │                      │ ◄──── │                                      │ │
│  └──────────────────────┘       │  Available Tools:                    │ │
│                                  │  ├── search     (NL analytics)      │ │
│                                  │  ├── process    (submit documents)  │ │
│                                  │  ├── reprocess  (re-run pipeline)   │ │
│                                  │  ├── status     (batch monitoring)  │ │
│                                  │  └── get_results (extracted data)   │ │
│                                  └──────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### Authentication Flow

```
Connector Startup
      │
      ▼
 Read config from
 environment vars
      │
      ▼
 POST /oauth2/token ──────────────► Cognito Token Endpoint
 grant_type=client_credentials      (MCPTokenURL)
 client_id=<MCPConnectorClientId>
 client_secret=<MCPConnectorClientSecret>
      │
      ◄─────────────────────────── access_token (JWT, ~1hr TTL)
      │
      ▼
 Call AgentCore Gateway
 GET tools/list ──────────────────► AgentCore Gateway
 Authorization: Bearer <token>       (MCPServerEndpoint)
      │
      ◄─────────────────────────── [{name, description, inputSchema}, ...]
      │
      ▼
 Dynamically register each
 discovered tool in local
 MCP server
      │
      ▼
 Start stdio MCP server
 (ready for Cline / Kiro)
```

### Runtime Request Flow

```
User types in Cline: "How many documents were processed this week?"
      │
      ▼
Cline calls: tools/call "search" {"query": "How many documents were processed this week?"}
      │  (stdio)
      ▼
idp_mcp_connector receives tool call
      │
      ├── Check if token is still valid (TTL check with 60s buffer)
      │       └── If expired: re-authenticate with Cognito
      │
      ▼
POST <MCPServerEndpoint>
Authorization: Bearer <token>
{"method": "tools/call", "params": {"name": "search", "arguments": {"query": "..."}}}
      │  (HTTPS)
      ▼
AgentCore Gateway → Lambda → Analytics Agent → IDP Data
      │
      ◄─── {"success": true, "result": "1,250 documents processed this week with 98.5% success rate."}
      │
      ▼
idp_mcp_connector returns result to Cline via stdio
      │
      ▼
Cline displays result in chat
```

### Component Details

#### `auth.py` — Cognito OAuth Token Manager

Manages the full OAuth token lifecycle:

- Obtains tokens using the **client credentials grant** (`grant_type=client_credentials`)
- Caches tokens in memory to avoid unnecessary authentication calls
- Validates token expiry with a 60-second buffer before making requests
- Automatically re-authenticates when tokens expire

#### `connector.py` — Transparent MCP Proxy

The core of the connector:

- On startup: discovers all tools from the remote MCP Server via `tools/list`
- Dynamically registers each discovered tool as a local MCP tool (preserving names, descriptions, and input schemas exactly)
- On tool call: validates/refreshes auth token, forwards the call to the remote server, and returns the result
- If new tools are added to the IDP MCP Server, they are automatically discovered on next restart

#### `__main__.py` — Entry Point

Reads configuration from environment variables, wires together `auth.py` and `server.py`, and starts the MCP server on stdio.

---

## 3. How to Install

### Prerequisites

- Python 3.11 or higher
- An IDP Accelerator stack deployed with `EnableMCP: true`
- The following values from your CloudFormation stack outputs:

| CloudFormation Output | Description |
|----------------------|-------------|
| `MCPServerEndpoint` | The AgentCore Gateway HTTPS endpoint |
| `MCPTokenURL` | Cognito OAuth token endpoint URL |
| `MCPConnectorClientId` | Cognito app client ID for the MCP Connector (machine-to-machine (M2M) `client_credentials` flow — no user login required) |
| `MCPConnectorClientSecret` | Cognito app client secret for the MCP Connector (machine-to-machine (M2M) flow) |
| `MCPContentBucket` | S3 bucket for uploading documents (optional, for `process` tool) |

### Installation

Navigate to the IDP Accelerator directory and install the package:

```bash
# Install in development mode (recommended — keeps it up to date with repo changes)
pip install -e genaiic-idp-accelerator/lib/idp_mcp_connector_pkg

# Or install with uv (faster)
uv pip install -e genaiic-idp-accelerator/lib/idp_mcp_connector_pkg
```

### Verify Installation

```bash
python -m idp_mcp_connector --version
# Output: idp_mcp_connector 1.0.0

python -m idp_mcp_connector --help
# Displays usage information and required environment variables
```

---

## 4. Usage

### Configuration

The connector is configured entirely through environment variables. All four authentication variables are required:

| Environment Variable | Required | CloudFormation Output | Description |
|---------------------|----------|----------------------|-------------|
| `IDP_MCP_ENDPOINT` | ✅ Yes | `MCPServerEndpoint` | AgentCore Gateway URL |
| `IDP_MCP_TOKEN_URL` | ✅ Yes | `MCPTokenURL` | Cognito OAuth token endpoint |
| `IDP_MCP_CLIENT_ID` | ✅ Yes | `MCPConnectorClientId` | Cognito app client ID (machine-to-machine (M2M) `client_credentials` flow — no user login required) |
| `IDP_MCP_CLIENT_SECRET` | ✅ Yes | `MCPConnectorClientSecret` | Cognito app client secret |

### Running the Connector Manually (for testing)

You can test the connector from the command line by setting environment variables and running it:

```bash
export IDP_MCP_ENDPOINT="https://xxx.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
export IDP_MCP_TOKEN_URL="https://idp-stack-xxx.auth.us-east-1.amazoncognito.com/oauth2/token"
export IDP_MCP_CLIENT_ID="abc123def456"
export IDP_MCP_CLIENT_SECRET="your-client-secret"

python -m idp_mcp_connector
```

On successful startup, you will see:
```
IDP MCP Connector starting...
Authenticating with Cognito...
Authentication successful. Token valid for 3600s.
Discovering tools from IDP MCP Server...
Discovered 5 tools: search, process, reprocess, status, get_results
IDP MCP Connector ready. Listening on stdio.
```

### Available Tools

The connector dynamically discovers and exposes all tools from the IDP MCP Server. The current IDP MCP Server provides the following tools:

| Tool | Description |
|------|-------------|
| `search` | Natural language queries on processed document analytics (e.g., "How many invoices failed last week?") |
| `process` | Submit documents for processing from S3 URI or base64-encoded content |
| `reprocess` | Re-run documents through the classification or extraction pipeline steps |
| `status` | Check processing status of a batch (total, completed, in-progress, failed counts) |
| `get_results` | Retrieve extracted fields, confidence scores, and metadata for processed documents |

---

## 5. Example: Working with Cline

This section walks through the complete setup and a realistic demo scenario using Cline in VS Code.

### Step 1: Deploy the IDP Stack with MCP Enabled

Ensure your `config.yaml` has MCP enabled before deploying:

```yaml
EnableMCP: 'true'
```

After deployment, navigate to the CloudFormation console and copy these output values:

```
MCPServerEndpoint       →  https://xxx.bedrock-agentcore.us-east-1.amazonaws.com/mcp
MCPTokenURL             →  https://idp-stack-xxx.auth.us-east-1.amazoncognito.com/oauth2/token
MCPConnectorClientId    →  abc123def456ghi789
MCPConnectorClientSecret →  <secret-value>
MCPContentBucket        →  idp-stack-mcp-content-bucket-xxx
```

### Step 2: Install the Connector

```bash
pip install -e genaiic-idp-accelerator/lib/idp_mcp_connector_pkg
```

### Step 3: Configure Cline

Cline stores MCP server configuration in a single shared file used by both VS Code and JetBrains IDEs:

```
~/.cline/data/settings/cline_mcp_settings.json
```

On macOS this expands to `/Users/<your-username>/.cline/data/settings/cline_mcp_settings.json`.

**Open the file:**
- **VS Code**: Cline sidebar → MCP Servers icon → Configure tab → "Configure MCP Servers"
- **JetBrains (PyCharm)**: Cline tool window → MCP Servers → Settings gear icon → "Edit MCP Settings"
- Or open it directly in any text editor using the path above

Add the IDP connector configuration, using the `MCPConnectorClientId` and `MCPConnectorClientSecret` values from your CloudFormation stack outputs:

```json
{
  "mcpServers": {
    "idp-mcp-server": {
      "command": "python3",
      "args": ["-m", "idp_mcp_connector"],
      "env": {
        "IDP_MCP_ENDPOINT": "https://xxx.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
        "IDP_MCP_TOKEN_URL": "https://idp-stack-xxx.auth.us-east-1.amazoncognito.com/oauth2/token",
        "IDP_MCP_CLIENT_ID": "abc123def456ghi789",
        "IDP_MCP_CLIENT_SECRET": "<your-client-secret>"
      },
      "alwaysAllow": [],
      "disabled": false
    }
  }
}
```

> **Windows note**: Use `"command": "python"` instead of `"python3"`.

After saving, Cline automatically detects the file change and starts the connector process.

### Step 4: Verify Connection

After saving the configuration, Cline automatically launches the connector process in the background. To confirm it is working:

1. Click the **MCP Servers icon** in the top-right corner of the Cline panel
2. Select the **"Installed"** tab (or **"Configure"** tab)
3. Find **`idp-mcp-server`** in the list and check its status indicator:
   - **🟢 Green dot** — connector is running, authenticated with Cognito, and ready
   - **🟡 Yellow dot** — connector is starting up (wait a few seconds, then refresh)
   - **🔴 Red dot** — connector failed to start (see Troubleshooting below)
4. Click on **`idp-mcp-server`** to expand the entry — you should see all 5 tools listed under it:

   | Tool | Status |
   |------|--------|
   | `search` | Available |
   | `process` | Available |
   | `reprocess` | Available |
   | `status` | Available |
   | `get_results` | Available |

5. If you see the green dot and all 5 tools — the connector is fully operational. You can now use IDP capabilities directly from the Cline chat.

> **Tip**: You can also verify from the terminal before configuring Cline. Run the connector manually with your environment variables set — if you see `"Discovered 5 tools: search, process, reprocess, status, get_results"` in the output, the credentials and endpoint are correct.

### Step 5: Demo Scenarios

Once connected, all IDP capabilities are available directly from the Cline chat interface.

---

#### Scenario 1: Process Documents

Upload documents to the MCP Content Bucket and trigger processing:

```bash
# Upload documents first
aws s3 cp ./invoices/ s3://idp-stack-mcp-content-bucket-xxx/demo-invoices/ --recursive
```

Then in Cline chat:
> **"Process the invoices I uploaded to s3://idp-stack-mcp-content-bucket-xxx/demo-invoices/"**

Cline calls the `process` tool and returns:
```
✅ Successfully queued 12 documents for processing.
   Batch ID: mcp-batch-20250316-143000
   Documents queued: 12
```

---

#### Scenario 2: Monitor Processing Status

> **"What's the status of batch mcp-batch-20250316-143000?"**

Cline calls the `status` tool and returns:
```
📊 Batch Status: mcp-batch-20250316-143000
   Total:       12
   Completed:   9  (75%)
   In Progress: 2
   Failed:      1
   Queued:      0
```

---

#### Scenario 3: Natural Language Analytics

> **"How many documents were processed this month and what's the overall success rate?"**

Cline calls the `search` tool and returns:
```
📈 This month's processing summary:
   1,847 documents processed in March 2026
   Success rate: 97.3% (1,797 completed, 50 failed)
   Most common document types: Invoice (42%), W2 (31%), Receipt (27%)
```

---

#### Scenario 4: Retrieve Extraction Results

> **"Get the extraction results for batch mcp-batch-20250316-143000 and show me the invoice data"**

Cline calls the `get_results` tool, receives structured JSON, and displays:
```json
{
  "document_id": "mcp-batch-20250316-143000/invoice-001.pdf",
  "document_class": "invoice",
  "fields": {
    "vendor_info": {"name": "Acme Corp", "address": "123 Main St"},
    "total_amount": "$4,250.00",
    "invoice_date": "2026-03-15"
  },
  "confidence": {
    "total_amount": 0.99,
    "invoice_date": 0.97
  }
}
```

You can then ask Cline to work with this data:
> **"Create a Python dataclass from this invoice schema"**

Cline generates:
```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class VendorInfo:
    name: str
    address: str

@dataclass
class Invoice:
    vendor_info: VendorInfo
    total_amount: str
    invoice_date: str
```

---

#### Scenario 5: Reprocess Failed Documents

> **"Reprocess the failed documents from the extraction step for batch mcp-batch-20250316-143000"**

Cline calls the `reprocess` tool:
```
🔄 Reprocessing initiated.
   Batch ID:  mcp-batch-20250316-143000
   Step:      extraction
   Queued:    1 document
```

---

### Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| Red dot in Cline MCP panel | Connector not starting | Check Python is on PATH; run `python -m idp_mcp_connector` manually to see error |
| `Authentication failed` | Wrong credentials | Verify `IDP_MCP_CLIENT_ID` and `IDP_MCP_CLIENT_SECRET` from CloudFormation outputs |
| `No tools discovered` | Wrong endpoint | Verify `IDP_MCP_ENDPOINT` value; check MCP is enabled in your IDP stack |
| `Tool call failed: 401` | Token expired (shouldn't happen — connector auto-refreshes) | Restart Cline MCP server |
| `Tool call failed: 403` | Insufficient permissions | Verify the Cognito client has the correct OAuth scopes |
| Tools not showing | Connector crashed silently | Check Cline's MCP server logs (MCP Servers panel → server name → logs) |

---

### Related Documentation

- [MCP Server](./mcp-server.md) — IDP MCP Server overview and tool reference
- [Custom MCP Agent](./custom-MCP-agent.md) — Connecting your own MCP servers to the IDP web interface
- [IDP CLI](./idp-cli.md) — Command-line interface for IDP operations
- [IDP SDK](./idp-sdk.md) — Python SDK for programmatic IDP access
