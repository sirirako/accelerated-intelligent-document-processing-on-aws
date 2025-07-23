# IDP Common Agents Module

This module provides agent-based functionality using the Strands framework for the GenAI IDP Accelerator. All agents are built on top of Strands agents and tools, providing intelligent document processing capabilities.

## Overview

The agents module is designed to support multiple types of intelligent agents while maintaining consistency and reusability across the IDP accelerator. Currently implemented:

- **Analytics Agent**: Natural language to SQL/visualization conversion
- **Common Utilities**: Shared configuration and utilities for all agent types

## Architecture

```
idp_common/agents/
├── README.md                    # This file
├── __init__.py                  # Module initialization with lazy loading
├── common/                      # Shared utilities for all agent types
│   ├── __init__.py
│   └── config.py               # Common configuration patterns
├── analytics/                   # Analytics agent implementation
│   ├── __init__.py
│   ├── agent.py                # Analytics agent factory
│   ├── config.py               # Analytics-specific configuration
│   ├── tools/                  # Strands tools for analytics
│   │   ├── __init__.py
│   │   ├── athena_tool.py      # Athena query execution
│   │   ├── generate_plot_tool.py # Python code execution for plots/tables
│   │   └── get_database_info_tool.py # Database schema information
│   └── assets/                 # Static assets (prompts, schemas)
│       ├── db_description.md
│       └── result_format_description.md
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

### 2. Simple Factory Pattern
Each agent type follows a simple pattern:
- `agent.py` - Factory function to create configured Strands agents
- `config.py` - Simple configuration management
- `tools/` - Strands tools specific to that agent type
- `assets/` - Static assets like prompts, schemas, etc.

### 3. IDP Integration
Agents are designed to integrate seamlessly with the IDP accelerator:
- Environment variable configuration for Lambda deployment
- AWS service integration (Athena, S3, etc.)
- Consistent logging patterns
- Error handling that works in serverless environments

## Usage

### Analytics Agent

The analytics agent provides natural language to SQL/visualization conversion with three main tools:

1. **Athena Query Tool** (`athena_tool.py`): Executes SQL queries against AWS Athena
2. **Plot Generation Tool** (`generate_plot_tool.py`): Executes Python code for creating visualizations and tables
3. **Database Info Tool** (`get_database_info_tool.py`): Provides database schema information

```python
from idp_common.agents.analytics import create_analytics_agent, get_analytics_config

# Get configuration from environment variables
config = get_analytics_config()

# Create the agent
agent = create_analytics_agent(config)

# Use the agent
response = agent("How many documents were processed last week?")
```

### Common Configuration

```python
from idp_common.agents.common import get_environment_config

# Get basic configuration with validation
config = get_environment_config(["REQUIRED_VAR1", "REQUIRED_VAR2"])
```

## Adding New Agent Types

To add a new agent type (e.g., `document_analysis`):

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
   
   def create_document_analysis_agent(config):
       tools = [your_tool1, your_tool2, your_tool3]
       system_prompt = "Your agent prompt here..."
       return Agent(tools=tools, system_prompt=system_prompt)
   ```

3. **Add configuration management** (`config.py`):
   ```python
   from ..common.config import get_environment_config
   
   def get_document_analysis_config():
       return get_environment_config(["REQUIRED_ENV_VAR"])
   ```

4. **Create Strands tools** (`tools/`):
   ```python
   from strands import tool
   
   @tool
   def your_tool(input_param: str) -> dict:
       # Tool implementation
       return {"result": "processed"}
   
   @tool
   def get_database_info() -> str:
       # Database schema information tool
       return "Database schema details..."
   
   @tool
   def generate_plot(code: str) -> dict:
       # Python code execution for visualizations
       return {"stdout": "output", "stderr": "", "success": True}
   ```

5. **Update the main module** (`__init__.py`):
   ```python
   # Add to the lazy loading list
   if name in ["analytics", "common", "document_analysis"]:
   ```

## Testing

The `testing/` directory provides utilities for testing agents locally:

- **Direct Testing**: Test agents outside of Lambda environment
- **Configuration Validation**: Verify environment setup
- **Response Analysis**: Parse and validate agent responses

See [`testing/README.md`](./testing/README.md) for detailed testing instructions.

## Dependencies

### Core Dependencies
- `strands-agents>=1.0.0` - Core agent framework
- `boto3` - AWS service integration

### Analytics-Specific Dependencies
- `pandas>=2.0.0` - Data manipulation

### Optional Dependencies
Install specific agent dependencies as needed:
```bash
# For analytics agents
pip install "idp_common[agents,analytics]"

# For all agent functionality
pip install "idp_common[all]"
```

## Integration with Lambda Functions

Agents are designed to work seamlessly in AWS Lambda:

```python
# In your Lambda function
from idp_common.agents.analytics import create_analytics_agent, get_analytics_config

def handler(event, context):
    config = get_analytics_config()  # Loads from environment variables
    agent = create_analytics_agent(config)
    
    query = event.get("query")
    response = agent(query)
    
    return {"response": response}
```

## Future Agent Types

The framework is designed to easily support additional agent types:

- **Document Analysis**: Understanding document structure and content
- **Workflow Automation**: Process automation and orchestration
- **Quality Assurance**: Validation and quality checking
- **Custom Agents**: Customer-specific implementations

Each would follow the same simple pattern established by the analytics agent.

## Contributing

When adding new agents or modifying existing ones:

1. Follow the established directory structure
2. Use Strands tools with the `@tool` decorator
3. Implement comprehensive unit tests
4. Update this README with new agent types
5. Ensure Lambda compatibility
6. Follow existing logging and error handling patterns

## Support

For questions about the agents module:
- Check the testing utilities in `testing/`
- Review existing agent implementations
- Consult the main IDP documentation
