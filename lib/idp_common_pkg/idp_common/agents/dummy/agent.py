# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Dummy Agent implementation for development purposes."""

import logging

import boto3
from strands import Agent
from strands.models import BedrockModel
from strands_tools import calculator

from ..common.idp_agent import IDPAgent

logger = logging.getLogger(__name__)


def create_dummy_agent(
    session: boto3.Session,
    job_id: str = None,
    user_id: str = None,
    **kwargs,
) -> IDPAgent:
    """
    Create a minimal dummy agent with calculator tool.

    Args:
        session: Boto3 session for AWS operations
        job_id: Job ID for monitoring (optional)
        user_id: User ID for monitoring (optional)
        **kwargs: Additional arguments

    Returns:
        IDPAgent: Configured dummy agent instance
    """
    # Use hardcoded model ID
    model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"

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
            "Help me solve 15% of 200",
        ],
        job_id=job_id,
        user_id=user_id,
    )
