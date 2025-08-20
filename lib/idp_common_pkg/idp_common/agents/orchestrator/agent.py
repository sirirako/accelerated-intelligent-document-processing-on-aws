# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Orchestrator Agent implementation using Strands framework.

This agent coordinates multiple specialized agents, routing queries to the most
appropriate agent based on the user's request and the capabilities of each agent.
"""

import logging
import os
import types
from typing import Any, Dict, List

import strands
from strands import tool
from strands.models import BedrockModel

logger = logging.getLogger(__name__)


def create_orchestrator_agent(
    config: Dict[str, Any],
    session: Any,
    agent_tools: List[Dict[str, Any]],
    **kwargs,
) -> strands.Agent:
    """
    Create and configure the orchestrator agent with specialized agents as tools.

    Args:
        config: Configuration dictionary
        session: Boto3 session for AWS operations
        agent_tools: List of agent metadata dicts with keys: agent_id, agent_name,
                    agent_description, sample_queries, and creator_func
        **kwargs: Additional arguments

    Returns:
        strands.Agent: Configured orchestrator agent instance
    """

    # Create tool functions for each specialized agent
    #
    # IMPORTANT: We need to create uniquely named tool functions for each agent
    # because Strands uses function names to identify and call tools. If all
    # functions have the same name (like "agent_tool"), the orchestrator will
    # only see one tool instead of multiple specialized agents.
    #
    # The challenge is that Python closures created in a loop all reference
    # the same variables, so simply setting __name__ doesn't work reliably.
    # We solve this by creating entirely new function objects with unique names.
    tools = []
    agent_descriptions = []

    for agent_info in agent_tools:
        agent_id = agent_info["agent_id"]
        agent_name = agent_info["agent_name"]
        agent_description = agent_info["agent_description"]
        sample_queries = agent_info.get("sample_queries", [])
        creator_func = agent_info["creator_func"]

        # Create a unique function name based on the agent ID
        # Convert hyphens to underscores for valid Python identifiers
        # e.g., "analytics-20250813-v0-kaleko" -> "analytics_20250813_v0_kaleko_agent"
        func_name = f"{agent_id.replace('-', '_')}_agent"

        # Create the function body with proper closure
        # This factory function ensures each tool function has its own scope
        # and captures the correct agent metadata (avoiding closure issues)
        def create_tool_function(aid, aname, adesc, creator, fname):
            """
            Factory function to create a tool function with proper closure.

            This is necessary because:
            1. Each tool needs to capture different agent metadata
            2. Python closures in loops can have variable capture issues
            3. We need unique function names for Strands tool identification

            Args:
                aid: Agent ID for error logging
                aname: Agent name for error messages
                adesc: Agent description (used in docstring)
                creator: Function to create the specialized agent
                fname: Unique function name for this tool
            """

            def tool_func(query: str) -> str:
                """
                Tool function that routes queries to a specific specialized agent.

                This function:
                1. Creates an instance of the specialized agent using its creator function
                2. Passes the user's query to that agent
                3. Returns the agent's response as a string
                4. Handles errors gracefully with informative messages
                """
                try:
                    # Create the specialized agent instance
                    # Pass through config, session, and any additional kwargs
                    specialized_agent = creator(
                        config=config, session=session, **kwargs
                    )

                    # Execute the query on the specialized agent
                    response = specialized_agent(query)
                    return str(response)

                except Exception as e:
                    # Log the error for debugging while returning a user-friendly message
                    logger.error(f"Error in {aname}: {e}")
                    return f"Error processing query with {aname}: {str(e)}"

            # Create a new function object with the unique name
            # This is the key step that ensures Strands sees distinct tools
            #
            # types.FunctionType creates a new function with:
            # - Same code object (the actual function logic)
            # - Same globals (access to variables in this module)
            # - New name (unique identifier for Strands)
            # - Same defaults and closure (preserves behavior)
            new_func = types.FunctionType(
                tool_func.__code__,  # The compiled function code
                tool_func.__globals__,  # Global namespace access
                fname,  # NEW: Unique function name
                tool_func.__defaults__,  # Default parameter values
                tool_func.__closure__,  # Closure variables (captured scope)
            )

            # Set a descriptive docstring that Strands can use for tool selection
            # The LLM uses this to understand when to call this specific tool
            new_func.__doc__ = f"""
            Route query to {aname}.
            
            {adesc}
            
            Args:
                query: The user's question or request
                
            Returns:
                The agent's response to the query
            """

            # Apply the @tool decorator to register this as a Strands tool
            # The decorator makes this function available to the orchestrator agent
            return tool(new_func)

        # Create the tool function for this specific agent
        tool_func = create_tool_function(
            agent_id, agent_name, agent_description, creator_func, func_name
        )
        tools.append(tool_func)

        # Build description for system prompt
        # Include sample queries to help the orchestrator choose the right agent
        sample_queries_text = ""
        if sample_queries:
            sample_queries_text = f"\nExample queries: {', '.join(sample_queries[:3])}"

        agent_descriptions.append(
            f"- {agent_name}: {agent_description}{sample_queries_text}"
        )

    # Create system prompt with agent descriptions
    agents_list = "\n".join(agent_descriptions)

    system_prompt = f"""You are an intelligent orchestrator that routes user queries to specialized agents.

Available specialized agents:
{agents_list}

Your role is to:
1. Analyze the user's query to understand what they're asking for
2. Select the most appropriate specialized agent based on the query content and agent capabilities
3. Route the query to that agent using the corresponding tool
4. Return the agent's response to the user

Guidelines:
- Choose the agent whose description and sample queries best match the user's request
- If a query could fit multiple agents, choose the most specific/specialized one
- Always use exactly one agent tool per query
- Pass the user's original query directly to the selected agent
- Return the agent's response without modification

Remember: Your job is to route queries, not to answer them directly. Always use one of the available agent tools."""

    # Get model ID from environment variable
    model_id = os.environ.get(
        "DOCUMENT_ANALYSIS_AGENT_MODEL_ID",
        "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    )

    # Create the orchestrator agent
    model = BedrockModel(
        model_id=model_id,
        session=session,
    )

    orchestrator = strands.Agent(
        system_prompt=system_prompt,
        model=model,
        tools=tools,
        callback_handler=None,  # Suppress intermediate output
    )

    return orchestrator
