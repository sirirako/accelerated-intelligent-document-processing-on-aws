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
    creator_func=create_analytics_agent,
)

# Register dummy agent
agent_factory.register_agent(
    agent_id="dummy-dev-v1",
    agent_name="Dummy Agent",
    agent_description="Simple development agent with calculator tool",
    creator_func=create_dummy_agent,
)
