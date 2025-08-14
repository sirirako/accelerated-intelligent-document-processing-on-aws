# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Dummy Agent implementation for development purposes."""

import logging
import os
from typing import Any, Dict

import boto3
from strands import Agent
from strands.models import BedrockModel
from strands_tools import calculator

from ..common.idp_agent import IDPAgent

logger = logging.getLogger(__name__)


def create_dummy_agent(
    config: Dict[str, Any],
    session: boto3.Session,
    job_id: str = None,
    user_id: str = None,
    **kwargs,
) -> IDPAgent:
    """
    Create a minimal dummy agent with calculator tool.

    Args:
        config: Configuration dictionary
        session: Boto3 session for AWS operations
        job_id: Job ID for monitoring (optional)
        user_id: User ID for monitoring (optional)
        **kwargs: Additional arguments

    Returns:
        IDPAgent: Configured dummy agent instance
    """
    # Get model ID from environment variable
    model_id = os.environ.get(
        "DUMMY_AGENT_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"
    )

    # Create Bedrock model
    model = BedrockModel(model_id=model_id, session=session)

    # Create agent with calculator tool
    agent = Agent(model=model, tools=[calculator])

    # Wrap in IDPAgent
    return IDPAgent(
        agent=agent,
        agent_id="dummy-dev-v1",
        agent_name="Dummy Agent",
        agent_description="Simple development agent with calculator tool",
    )
