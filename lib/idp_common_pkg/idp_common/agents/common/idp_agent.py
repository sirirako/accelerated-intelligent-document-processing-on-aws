# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
IDPAgent base class that extends Strands Agent with IDP-specific metadata.
"""

from strands import Agent


class IDPAgent(Agent):
    """
    IDP agent that extends Strands Agent with metadata.
    """

    def __init__(
        self,
        agent_name: str,
        agent_description: str,
        agent_id: str,
        agent: Agent,
    ):
        """
        Initialize IDPAgent with metadata by wrapping an existing Strands Agent.

        Args:
            agent_name: Human-readable name for the agent
            agent_description: Description of what the agent does
            agent_id: Unique identifier for the agent
            agent: Existing Strands Agent instance to wrap (required)
        """
        # Initialize as empty Agent first, then copy all attributes from the provided agent
        super().__init__(tools=[], system_prompt="", model=None)
        # Copy all attributes from the existing agent
        for attr, value in agent.__dict__.items():
            setattr(self, attr, value)

        # Set our metadata attributes after copying (to ensure they don't get overwritten)
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.agent_id = agent_id
