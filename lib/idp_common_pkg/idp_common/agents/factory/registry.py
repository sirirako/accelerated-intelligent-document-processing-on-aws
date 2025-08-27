# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Global agent factory registry.

This module provides a pre-configured global instance of IDPAgentFactory with all
available agents registered. Import `agent_factory` to access registered agents.

Example:
    from idp_common.agents.factory import agent_factory

    # List available agents
    agents = agent_factory.list_available_agents()

    # Create an agent
    agent = agent_factory.create_agent("analytics-20250813-v0-kaleko", config=config)
"""

import logging

from ..analytics.agent import create_analytics_agent
from ..dummy.agent import create_dummy_agent
from .agent_factory import IDPAgentFactory

logger = logging.getLogger(__name__)

# Create global factory instance
agent_factory = IDPAgentFactory()

# Register analytics agent
agent_factory.register_agent(
    agent_id="analytics-20250813-v0-kaleko",
    agent_name="Analytics Agent",
    agent_description="""
    Converts natural language questions into SQL queries and generates visualizations from document data.
    This agent has access to all databases within the IDP system, including metering databases which track
    the document processing volume and statistics, document-specific tables for different classes of documents,
    entity-specific information like names of people, numbers, and other entities extracted from documents,
    as well as evaluation tables which include confidence scores for extracted entities as well as
    accuracy metrics for evaluation jobs computed against provided ground truth data.
    """,
    creator_func=create_analytics_agent,
    sample_queries=[
        "How many input and output tokens have I processed in each of the last 10 days?",
        "What are the most common document types processed?",
        "In extracted W2 forms, what is the average state tax paid?",
    ],
)

# Register dummy agent
agent_factory.register_agent(
    agent_id="dummy-dev-v1",
    agent_name="Dummy Agent",
    agent_description="Simple development agent with calculator tool",
    creator_func=create_dummy_agent,
    sample_queries=[
        "Calculate 25 * 4 + 10",
        "What is the square root of 144?",
        "Help me solve 15% of 200",
    ],
)

# Conditionally register External MCP Agent if credentials are available
try:
    import json

    import boto3

    from ..external_mcp.agent import create_external_mcp_agent
    from ..external_mcp.config import get_external_mcp_config

    # Test if External MCP Agent credentials are available (without creating the agent)
    test_session = boto3.Session()
    test_config = get_external_mcp_config()

    # Just test if we can access the secret - don't create the full agent
    secret_name = test_config["secret_name"]
    region = test_config.get("region", test_session.region_name or "us-east-1")

    secrets_client = test_session.client("secretsmanager", region_name=region)
    response = secrets_client.get_secret_value(SecretId=secret_name)
    secret_value = response["SecretString"]
    credentials = json.loads(secret_value)

    # Validate required fields exist
    required_fields = [
        "mcp_url",
        "cognito_user_pool_id",
        "cognito_client_id",
        "cognito_username",
        "cognito_password",
    ]
    for field in required_fields:
        if field not in credentials:
            raise ValueError(f"Missing required field '{field}' in MCP credentials")

    # Try to discover available tools for dynamic description by creating temporary agent
    try:
        # Create temporary agent with dummy model ID just for tool discovery
        test_result = create_external_mcp_agent(
            config=test_config,
            session=test_session,
            model_id="dummy-model-for-tool-discovery",
        )
        test_strands_agent, test_mcp_client = test_result

        # Extract the dynamic description from the test agent's system prompt
        dynamic_description = "Agent which connects to external MCP servers to provide additional tools and capabilities"
        if (
            hasattr(test_strands_agent, "system_prompt")
            and test_strands_agent.system_prompt
        ):
            # Extract the description from the system prompt
            prompt_lines = test_strands_agent.system_prompt.strip().split("\n")
            for line in prompt_lines:
                if "tools available from this external server" in line:
                    dynamic_description = line.strip()
                    break

        # Clean up the test MCP client
        if test_mcp_client:
            try:
                with test_mcp_client:
                    pass  # Just enter and exit to clean up
            except Exception:
                pass  # Ignore cleanup errors

    except Exception as e:
        logger.warning(f"Could not discover MCP tools for description: {e}")
        dynamic_description = "Agent which connects to external MCP servers to provide additional tools and capabilities"

    # If successful, register the agent with static description
    agent_factory.register_agent(
        agent_id="external-mcp-agent-0",
        agent_name="External MCP Agent",
        agent_description=dynamic_description,
        creator_func=create_external_mcp_agent,
        sample_queries=[
            "What tools are available from the external MCP server?",
            "Help me use the external tools to solve my problem",
            "Show me what capabilities the MCP server provides",
        ],
    )
    logger.info("External MCP Agent registered successfully")

except Exception as e:
    logger.warning(
        f"External MCP Agent not registered - credentials not available or invalid: {str(e)}"
    )
    # Don't register the agent if it can't be created
