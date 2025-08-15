# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Factory for creating IDP agents.
"""

from typing import Any, Callable, Dict, List

from ..common.idp_agent import IDPAgent


class IDPAgentFactory:
    """Factory for creating and managing IDP agents."""

    def __init__(self):
        """Initialize the factory with an empty registry."""
        self._registry: Dict[str, Dict[str, Any]] = {}

    def register_agent(
        self,
        agent_id: str,
        agent_name: str,
        agent_description: str,
        creator_func: Callable[..., IDPAgent],
        sample_queries: List[str] = None,
    ) -> None:
        """
        Register an agent creator function with metadata.

        Args:
            agent_id: Unique identifier for the agent
            agent_name: Human-readable name for the agent
            agent_description: Description of what the agent does
            creator_func: Function that creates and returns an IDPAgent instance
            sample_queries: List of example queries for the agent
        """
        self._registry[agent_id] = {
            "agent_name": agent_name,
            "agent_description": agent_description,
            "creator_func": creator_func,
            "sample_queries": sample_queries or [],
        }

    def list_available_agents(self) -> List[Dict[str, str]]:
        """
        List all available agents with their metadata.

        Returns:
            List of dicts containing agent_id, agent_name, agent_description, and sample_queries
        """
        return [
            {
                "agent_id": agent_id,
                "agent_name": info["agent_name"],
                "agent_description": info["agent_description"],
                "sample_queries": info["sample_queries"],
            }
            for agent_id, info in self._registry.items()
        ]

    def create_agent(self, agent_id: str, **kwargs) -> IDPAgent:
        """
        Create an agent instance by ID.

        Args:
            agent_id: The ID of the agent to create
            **kwargs: Arguments to pass to the agent creator function

        Returns:
            IDPAgent instance

        Raises:
            ValueError: If agent_id is not registered
        """
        if agent_id not in self._registry:
            raise ValueError(f"Agent ID '{agent_id}' not found in registry")

        info = self._registry[agent_id]
        creator_func = info["creator_func"]

        # Call creator function which returns an IDPAgent
        return creator_func(**kwargs)
