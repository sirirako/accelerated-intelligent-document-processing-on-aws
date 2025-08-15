# IDP Common Agents Module

This module provides agent-based functionality using the Strands framework for the GenAI IDP Accelerator. All agents are built on top of Strands agents and tools, providing intelligent document processing capabilities.

## Overview

The agents module is designed to support multiple types of intelligent agents while maintaining consistency and reusability across the IDP accelerator. Currently implemented:

- **Analytics Agent**: Natural language to SQL/visualization conversion with secure code execution
- **Dummy Agent**: Simple development agent with calculator tool for testing and development
- **Common Utilities**: Shared configuration, monitoring, and utilities for all agent types

## Architecture

```
idp_common/agents/
├── README.md                    # This file
├── __init__.py                  # Module initialization with lazy loading
├── common/                      # Shared utilities for all agent types
│   ├── __init__.py
│   ├── config.py               # Common configuration patterns
│   ├── idp_agent.py            # IDPAgent base class with metadata
│   ├── monitoring.py           # Agent execution monitoring and hooks
│   ├── dynamodb_logger.py      # DynamoDB integration for message persistence
│   └── response_utils.py       # Response parsing utilities
├── factory/                     # Agent factory for creating and managing agents
│   ├── __init__.py
│   ├── agent_factory.py        # IDPAgentFactory class
│   └── registry.py             # Global factory instance with registered agents
├── analytics/                   # Analytics agent implementation
│   ├── __init__.py
│   ├── agent.py                # Analytics agent factory
│   ├── config.py               # Analytics-specific configuration
│   ├── utils.py                # Cleanup and utility functions
│   ├── tools/                  # Strands tools for analytics
│   │   ├── __init__.py
│   │   ├── athena_tool.py      # Athena query execution
│   │   ├── get_database_info_tool.py # Database schema information
│   │   └── code_interpreter_tools.py # Secure Python code execution
│   └── assets/                 # Static assets (prompts, schemas)
│       └── db_description.md   # Database schema documentation
├── dummy/                      # Dummy agent for development
│   ├── __init__.py
│   └── agent.py                # Simple agent with calculator tool
└── testing/                    # Testing utilities and examples
    ├── __init__.py
    ├── README.md               # Comprehensive testing guide
    ├── test_analytics.py
    ├── run_analytics_test.py
    ├── .env.example
    └── .env                    # Local environment configuration (gitignored)
```

## Design Principles

### 1. Strands-First Approach
All agents use the Strands framework directly without unnecessary abstraction layers. This provides:
- Excellent tool abstractions via `@tool` decorator
- Built-in agent management and conversation handling
- Consistent patterns across all agent types

### 2. Agent Factory Pattern
Agents are managed through a centralized factory that provides:
- **Agent Registry**: Central registration of all available agent types
- **Metadata Management**: Each agent includes name, description, and unique ID
- **Consistent Creation**: Standardized interface for creating any agent type
- **Extensibility**: Easy addition of new agent types without modifying existing code

### 3. IDPAgent Base Class
All agents extend the IDPAgent class which provides:
- **Metadata**: Each agent has a name, description, unique identifier, and sample queries
- **Strands Compatibility**: Full compatibility with Strands Agent functionality
- **Factory Integration**: Seamless integration with the agent factory pattern
- **Automatic Monitoring**: Built-in DynamoDB message tracking when job_id and user_id are provided

#### Agent Metadata for Router Agents
Agent descriptions and sample queries are critical for router agents that route queries to appropriate sub-agents:
- **Detailed Descriptions**: Used in router agent prompts to determine which agent to select
- **Sample Queries**: Help router agents understand the types of queries each agent handles
- **UI Integration**: Sample queries are displayed in the frontend to guide users

#### Automatic Monitoring System
The IDPAgent base class automatically sets up monitoring when both `job_id` and `user_id` parameters are provided during agent creation. This monitoring system:

- **Real-time UI Updates**: Logs agent conversations to DynamoDB for live progress tracking
- **Message Persistence**: Stores all agent interactions for debugging and audit purposes
- **Consistent Observability**: Provides the same monitoring across all agent types
- **Production Robustness**: Gracefully handles monitoring failures without breaking agent functionality

The monitoring is enabled automatically in Lambda environments where job tracking is needed, but can be disabled for testing or development scenarios.

### 4. Security-First Design
Agents are designed with security as a primary concern:
- **Sandboxed Code Execution**: Uses AWS Bedrock AgentCore for secure Python execution
- **Data Isolation**: Query results are transferred securely between services
- **Minimal Permissions**: Each agent requests only necessary AWS permissions
- **Audit Trail**: Comprehensive logging and monitoring for security reviews

### 5. IDP Integration
Agents are designed to integrate seamlessly with the IDP accelerator:
- Environment variable configuration for Lambda deployment
- AWS service integration (Athena, S3, AgentCore, etc.)
- Consistent logging patterns
- Error handling that works in serverless environments

## Security Architecture

### AgentCore Integration

The analytics agent uses **AWS Bedrock AgentCore** for secure Python code execution. This is a critical security decision that ensures:

- **Sandboxed Environment**: Python code runs in an isolated, secure sandbox
- **No Direct File System Access**: Code cannot access the Lambda file system
- **Controlled Data Transfer**: Query results are securely transferred via S3 and AgentCore APIs
- **Session Management**: Code interpreter sessions are properly managed and cleaned up

### Data Flow Security

1. **Query Execution**: SQL queries run against Athena with results stored in S3
2. **Secure Transfer**: Agent downloads CSV results from S3 using boto3
3. **Sandbox Injection**: CSV data is written to the AgentCore sandbox using the `writeFiles` API
4. **Code Execution**: Python visualization code runs in the isolated sandbox
5. **Result Extraction**: Generated plots/tables are returned as JSON through AgentCore APIs

This architecture ensures that arbitrary Python code (used for generating plots and tables) never executes in the Lambda environment, providing a secure foundation for future application security reviews.

## Usage

### Agent Factory

The recommended way to create agents is through the factory pattern:

```python
from idp_common.agents.factory import agent_factory

# List all available agents
available_agents = agent_factory.list_available_agents()
# Returns: [
#   {"agent_id": "analytics-20250813-v0-kaleko", "agent_name": "Analytics Agent", "agent_description": "..."},
#   {"agent_id": "dummy-dev-v1", "agent_name": "Dummy Agent", "agent_description": "..."}
# ]

# Create an agent by ID
agent = agent_factory.create_agent(
    agent_id="analytics-20250813-v0-kaleko",
    config=config,
    session=boto3.Session(),
    job_id="analytics-job-123",  # Enables automatic monitoring
    user_id="user-456"           # Required for monitoring
)

# The agent is an IDPAgent with metadata
print(agent.agent_name)        # "Analytics Agent"
print(agent.agent_description) # "Converts natural language questions..."
print(agent.agent_id)          # "analytics-20250813-v0-kaleko"

# Use the agent (same as any Strands agent)
response = agent("How many documents were processed last week?")
```

### Analytics Agent

The analytics agent provides natural language to SQL/visualization conversion with four main tools:

1. **Athena Query Tool** (`athena_tool.py`): Executes SQL queries against AWS Athena
2. **Database Info Tool** (`get_database_info_tool.py`): Provides database schema information
3. **Code Sandbox Writer** (`code_interpreter_tools.py`): Securely transfers query results to sandbox
4. **Python Executor** (`code_interpreter_tools.py`): Executes visualization code in secure sandbox

```python
from idp_common.agents.analytics import create_analytics_agent, get_analytics_config

# Get configuration from environment variables
config = get_analytics_config()

# Create the agent with monitoring context
agent = create_analytics_agent(
    config, 
    session=boto3.Session(), 
    job_id="analytics-job-123", 
    user_id="user-456"
)

# Use the agent
response = agent("How many documents were processed last week?")
```

### Dummy Agent

The dummy agent provides a simple development and testing environment with basic calculator functionality:

```python
from idp_common.agents.dummy import create_dummy_agent

# Create the dummy agent
agent = create_dummy_agent(
    config={}, 
    session=boto3.Session()
)

# Use the agent for simple calculations
response = agent("What is 15 * 23 + 7?")
```

The dummy agent is useful for:
- Testing the agent framework without complex dependencies
- Development and debugging of agent infrastructure
- Simple mathematical calculations during development
```

### Response Parsing

The analytics agent returns structured responses that can be parsed:

```python
from idp_common.agents.analytics import parse_agent_response

# Parse the agent response
result = parse_agent_response(response)

# Result contains:
# - responseType: "text", "table", or "plotData"
# - content: Text content (for text responses)
# - tableData: Structured table data (for table responses)
# - plotData: Chart.js compatible plot data (for plot responses)
```

### Common Configuration

```python
from idp_common.agents.common import get_environment_config

# Get basic configuration with validation
config = get_environment_config(["REQUIRED_VAR1", "REQUIRED_VAR2"])
```

## Monitoring and Observability

The agents module includes comprehensive monitoring capabilities built into the IDPAgent base class:

### Automatic Monitoring

All agents automatically include DynamoDB message tracking when created with `job_id` and `user_id` parameters:

```python
from idp_common.agents.factory import agent_factory

# Agent with automatic monitoring (typical Lambda usage)
agent = agent_factory.create_agent(
    agent_id="analytics-20250813-v0-kaleko",
    config=config,
    session=boto3.Session(),
    job_id="analytics-job-123",  # Enables monitoring
    user_id="user-456"           # Required for monitoring
)

# Agent without monitoring (testing/development)
agent = agent_factory.create_agent(
    agent_id="dummy-dev-v1",
    config=config,
    session=boto3.Session()
    # No job_id/user_id = no monitoring
)
```

The automatic monitoring system provides:
- **Real-time UI Updates**: Agent conversations are logged to DynamoDB for live progress tracking
- **Message Persistence**: All agent interactions stored for debugging and audit purposes
- **Consistent Observability**: Same monitoring patterns across all agent types
- **Production Robustness**: Graceful handling of monitoring failures

### Manual Monitoring (Legacy)

For advanced use cases, you can still manually configure monitoring:

### Agent Monitoring

```python
from idp_common.agents.common.monitoring import AgentMonitor

# Create agent with monitoring
agent_monitor = AgentMonitor(
    log_level=logging.INFO, 
    enable_detailed_logging=True
)
agent.hooks.add_hook(agent_monitor)

# Get execution report
report = agent_monitor.get_execution_report()
```

### DynamoDB Message Persistence

```python
from idp_common.agents.common.dynamodb_logger import DynamoDBMessageTracker

# Add message persistence
message_tracker = DynamoDBMessageTracker(
    job_id="analytics-job-123", 
    user_id="user-456"
)
agent.hooks.add_hook(message_tracker)
```

## Adding New Agent Types

To add a new agent type to the factory system:

### Step 1: Create the Agent Implementation

Create your agent directory structure:
```
idp_common/agents/your_agent/
├── __init__.py             # Export your agent creator function
└── agent.py                # Agent creation function
```

For simple agents, you may not need additional directories like `tools/`, `config.py`, or `assets/`.

### Step 2: Implement the Agent Creator Function

In `agent.py`, create a function that returns an IDPAgent:

```python
from strands import Agent
from ..common.idp_agent import IDPAgent
from .tools import your_tool1, your_tool2

def create_your_agent(config, session, **kwargs) -> IDPAgent:
    """
    Create and configure your agent.
    
    Args:
        config: Configuration dictionary
        session: Boto3 session
        **kwargs: Additional arguments
        
    Returns:
        IDPAgent: Configured agent instance
    """
    # Create tools
    tools = [your_tool1, your_tool2]
    
    # Define system prompt
    system_prompt = "Your agent system prompt here..."
    
    # Create Strands agent
    strands_agent = Agent(tools=tools, system_prompt=system_prompt, model=your_model)
    
    # Wrap in IDPAgent with metadata and automatic monitoring
    return IDPAgent(
        agent_name="Your Agent Name",
        agent_description="Description of what your agent does",  # Be detailed - used by router agents
        agent_id="your-agent-YYYYMMDD-v0-yourname",  # Use this naming convention
        sample_queries=[  # Provide 2-3 example queries - used by router agents and UI
            "Example query 1 that demonstrates your agent's capabilities",
            "Example query 2 showing different functionality",
            "Example query 3 for another use case"
        ],
        agent=strands_agent,
        job_id=job_id,      # Enables automatic monitoring when provided
        user_id=user_id     # Required for monitoring
    )
```

#### Example: Dummy Agent Implementation

Here's the complete implementation of the dummy agent as a concrete example:

**`idp_common/agents/dummy/__init__.py`:**
```python
from .agent import create_dummy_agent

__all__ = ["create_dummy_agent"]
```

**`idp_common/agents/dummy/agent.py`:**
```python
import logging
import os
from typing import Any, Dict

import boto3
from strands import Agent
from strands.models import BedrockModel
from strands_tools import calculator

from ..common.idp_agent import IDPAgent

def create_dummy_agent(
    config: Dict[str, Any],
    session: boto3.Session,
    job_id: str = None,
    user_id: str = None,
    **kwargs,
) -> IDPAgent:
    # Get model ID from environment variable
    model_id = os.environ.get("DUMMY_AGENT_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0")

    # Create Bedrock model
    model = BedrockModel(model_id=model_id, session=session)

    # Create agent with calculator tool
    agent = Agent(model=model, tools=[calculator])

    # Wrap in IDPAgent with automatic monitoring
    return IDPAgent(
        agent=agent,
        agent_id="dummy-dev-v1",
        agent_name="Dummy Agent",
        agent_description="Simple development agent with calculator tool",
        sample_queries=[
            "Calculate 25 * 4 + 10",
            "What is the square root of 144?",
            "Help me solve 15% of 200"
        ],
        job_id=job_id,      # Enables automatic monitoring when provided
        user_id=user_id,    # Required for monitoring
    )
```

### Step 3: Register the Agent

Add your agent to the factory registry in `factory/registry.py`:

```python
# Import your agent creator
from ..your_agent.agent import create_your_agent

# Register with the factory
agent_factory.register_agent(
    agent_id="your-agent-YYYYMMDD-v0-yourname",
    agent_name="Your Agent Name",
    agent_description="Description of what your agent does",
    creator_func=create_your_agent
)
```

#### Example: Dummy Agent Registration

**`factory/registry.py`:**
```python
from ..analytics.agent import create_analytics_agent
from ..dummy.agent import create_dummy_agent
from .agent_factory import IDPAgentFactory

# Create global factory instance
agent_factory = IDPAgentFactory()

# Register analytics agent
agent_factory.register_agent(
    agent_id="analytics-20250813-v0-kaleko",
    agent_name="Analytics Agent",
    agent_description="Converts natural language questions into SQL queries and generates visualizations from document data",
    sample_queries=[
        "Show me a chart of document processing volume by month",
        "What are the most common document types processed?",
        "Create a visualization showing extraction accuracy trends over time"
    ],
    creator_func=create_analytics_agent,
)

# Register dummy agent
agent_factory.register_agent(
    agent_id="dummy-dev-v1",
    agent_name="Dummy Agent",
    agent_description="Simple development agent with calculator tool",
    sample_queries=[
        "Calculate 25 * 4 + 10",
        "What is the square root of 144?",
        "Help me solve 15% of 200"
    ],
    creator_func=create_dummy_agent,
)
```

### Step 4: Update Module Exports

Update `__init__.py` files to include your new agent:

```python
# In idp_common/agents/__init__.py
def __getattr__(name):
    if name in ["analytics", "common", "testing", "factory", "your_agent"]:
        # ... existing code

# In idp_common/agents/your_agent/__init__.py
from .agent import create_your_agent
from .config import get_your_agent_config

__all__ = ["create_your_agent", "get_your_agent_config"]
```

### Step 5: Test Your Agent

Create tests and verify your agent works:

```python
from idp_common.agents.factory import agent_factory

# Test that your agent is registered
agents = agent_factory.list_available_agents()
assert any(a["agent_id"] == "your-agent-YYYYMMDD-v0-yourname" for a in agents)

# Test agent creation
agent = agent_factory.create_agent("your-agent-YYYYMMDD-v0-yourname", config=config)
assert agent.agent_name == "Your Agent Name"

# Test agent functionality
response = agent("Test query")
```

#### Example: Testing the Dummy Agent

```python
from idp_common.agents.factory import agent_factory
import boto3

# Test that dummy agent is registered
agents = agent_factory.list_available_agents()
assert any(a["agent_id"] == "dummy-dev-v1" for a in agents)

# Test agent creation
config = {'aws_region': 'us-east-1'}
session = boto3.Session()
agent = agent_factory.create_agent("dummy-dev-v1", config=config, session=session)
assert agent.agent_name == "Dummy Agent"

# Test agent functionality
response = agent("What is 15 * 23 + 7?")
```

### Agent ID Naming Convention

Use this naming pattern for agent IDs:
- `{agent-type}-{YYYYMMDD}-v{version}-{creator}`
- Example: `analytics-20250813-v0-kaleko`
- Example: `document-analysis-20250815-v1-smith`

This ensures:
- **Uniqueness**: No ID conflicts between different agents
- **Versioning**: Clear version tracking for agent updates
- **Attribution**: Clear ownership/creator identification
- **Chronology**: Easy to see when agents were created

### Legacy Direct Creation Pattern (Deprecated)

The old pattern of creating agents directly is still supported but deprecated:

1. **Create the directory structure**:
   ```
   idp_common/agents/document_analysis/
   ├── __init__.py
   ├── agent.py
   ├── config.py
   ├── tools/
   │   └── __init__.py
   └── assets/
   ```

2. **Implement the factory function** (`agent.py`):
   ```python
   from strands import Agent
   from .tools import your_tool1, your_tool2, your_tool3
   
   def create_document_analysis_agent(config, session, **kwargs):
       tools = [your_tool1, your_tool2, your_tool3]
       system_prompt = "Your agent prompt here..."
       return Agent(tools=tools, system_prompt=system_prompt)
   ```

**Note**: New agents should use the factory pattern described above for consistency and better metadata management.

## Testing

The `testing/` directory provides utilities for testing agents locally:

- **Direct Testing**: Test agents outside of Lambda environment
- **Configuration Validation**: Verify environment setup
- **Response Analysis**: Parse and validate agent responses
- **AgentCore Integration**: Test code interpreter functionality

See [`testing/README.md`](./testing/README.md) for detailed testing instructions.

## Dependencies

### Core Dependencies
- `strands-agents>=1.0.0` - Core agent framework
- `boto3` - AWS service integration
- `bedrock-agentcore` - Secure code execution sandbox

### Analytics-Specific Dependencies
- `pandas>=2.0.0` - Data manipulation (used in sandbox)

### Required AWS Permissions

For analytics agents, the following IAM permissions are required:

```yaml
# Athena and Glue permissions
- athena:StartQueryExecution
- athena:GetQueryExecution
- athena:GetQueryResults
- glue:GetTable
- glue:GetTables
- glue:GetDatabase
- glue:GetDatabases

# S3 permissions for query results
- s3:GetObject
- s3:PutObject
- s3:DeleteObject

# Bedrock permissions
- bedrock:InvokeModel
- bedrock:InvokeModelWithResponseStream

# AgentCore permissions (CRITICAL for security)
- bedrock-agentcore:StartCodeInterpreterSession
- bedrock-agentcore:StopCodeInterpreterSession
- bedrock-agentcore:InvokeCodeInterpreter
- bedrock-agentcore:GetCodeInterpreterSession
- bedrock-agentcore:ListCodeInterpreterSessions
```

### Optional Dependencies
Install specific agent dependencies as needed:
```bash
# For analytics agents
pip install "idp_common[agents,analytics]"

# For all agent functionality
pip install "idp_common[all]"
```

## Integration with Lambda Functions

Agents are designed to work seamlessly in AWS Lambda with automatic monitoring:

```python
# In your Lambda function
from idp_common.agents.factory import agent_factory
from idp_common.agents.analytics import get_analytics_config

def handler(event, context):
    # Change to /tmp for AgentCore compatibility
    os.chdir('/tmp')
    
    # Get configuration
    config = get_analytics_config()  # Loads from environment variables
    
    # Create agent using factory with automatic monitoring
    agent = agent_factory.create_agent(
        agent_id="analytics-20250813-v0-kaleko",  # Or get from event
        config=config,
        session=boto3.Session(),
        job_id=event.get("jobId"),    # Enables DynamoDB monitoring
        user_id=event.get("userId")   # Required for monitoring
    )
    
    query = event.get("query")
    response = agent(query)  # Agent conversations automatically logged to DynamoDB
    
    return {"response": response}
```

### Monitoring in Lambda

When `job_id` and `user_id` are provided, the agent automatically:
- Logs all conversations to DynamoDB (AGENT_TABLE environment variable)
- Enables real-time UI progress updates
- Provides message history for debugging
- Maintains audit trails for compliance

The monitoring system is designed to be robust - if DynamoDB logging fails, the agent continues to function normally.

### Legacy Direct Creation (Still Supported)

```python
# Direct creation (deprecated but still works)
from idp_common.agents.analytics import create_analytics_agent, get_analytics_config

def handler(event, context):
    os.chdir('/tmp')
    config = get_analytics_config()
    agent = create_analytics_agent(
        config, 
        session=boto3.Session(),
        job_id=event.get("jobId"),
        user_id=event.get("userId")
    )
    # ... rest of handler
```

### Lambda Environment Considerations

- **Working Directory**: Change to `/tmp` before creating agents (AgentCore requirement)
- **Session Management**: AgentCore sessions are automatically cleaned up
- **Memory Requirements**: Analytics agents require at least 1024MB memory
- **Timeout**: Set appropriate timeout (900s recommended for complex queries)

## Future Agent Types

The framework is designed to easily support additional agent types:

- **Document Analysis**: Understanding document structure and content
- **Workflow Automation**: Process automation and orchestration
- **Quality Assurance**: Validation and quality checking
- **Custom Agents**: Customer-specific implementations

Each would follow the same simple pattern established by the analytics agent, with appropriate security considerations for their specific use cases.

## Contributing

When adding new agents or modifying existing ones:

1. Follow the established directory structure
2. Use Strands tools with the `@tool` decorator
3. Implement comprehensive unit tests
4. Update this README with new agent types
5. Ensure Lambda compatibility
6. Follow existing logging and error handling patterns
7. **Provide detailed descriptions and sample queries** - these are used by router agents for query routing
8. **Security Review**: Ensure any code execution is properly sandboxed
9. **Permission Audit**: Document required AWS permissions

## Support

For questions about the agents module:
- Check the testing utilities in `testing/`
- Review existing agent implementations
- Consult the main IDP documentation
- Review security architecture for compliance requirements
