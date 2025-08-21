# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Lambda function to list all available agents.
"""

import json
import logging
import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Initialize agent factory at module level for caching across invocations
_cached_agents = None

def get_available_agents():
    """Get available agents, using cache if available."""
    global _cached_agents
    
    if _cached_agents is None:
        from idp_common.agents.factory import agent_factory
        _cached_agents = agent_factory.list_available_agents()
        logger.info(f"Cached {len(_cached_agents)} available agents")
    
    return _cached_agents


def handler(event, context):
    """
    List all available agents from the factory.
    
    Args:
        event: The event dict from AppSync
        context: The Lambda context
        
    Returns:
        List of available agents with metadata
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Get list of available agents (cached)
        available_agents = get_available_agents()
        
        logger.info(f"Returning {len(available_agents)} available agents")
        return available_agents
        
    except Exception as e:
        error_msg = f"Error listing available agents: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
