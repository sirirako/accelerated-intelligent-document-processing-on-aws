# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Lambda function for AgentCore Gateway analytics processing.
Provides analytics tools through AgentCore Gateway's built-in MCP server.
"""

import json
import logging
import os
from typing import Any, Dict

import boto3

from idp_common.agents.analytics import get_analytics_config
from idp_common.agents.common.config import configure_logging
from idp_common.agents.factory import agent_factory

# Configure logging for both application and Strands framework
configure_logging()

# Get logger for this module
logger = logging.getLogger(__name__)

# Track Lambda cold/warm starts for debugging
_lambda_invocation_count = 0


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Process analytics queries through agent orchestrator."""
    global _lambda_invocation_count
    _lambda_invocation_count += 1
    is_cold_start = _lambda_invocation_count == 1
    
    request_id = context.aws_request_id if context else 'unknown'
    logger.info(f"[{request_id}] Lambda invocation #{_lambda_invocation_count} ({'COLD START' if is_cold_start else 'WARM'})")
    logger.info(f"[{request_id}] Received agentcore analytics event: {json.dumps(event, default=str)}")
    
    try:
        # Create fresh AWS session for each invocation
        session = boto3.Session()
        logger.info(f"[{request_id}] Created fresh boto3 session")
        
        # Extract query from event
        query = event.get('query', 'Unknown')
        logger.info(f"[{request_id}] Received query from gateway: {query}")
        
        if not query or query == 'Unknown':
            logger.warning(f"[{request_id}] No query provided in event")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'query': query,
                    'result': 'No query provided'
                })
            }
        
        # Get analytics configuration
        config = get_analytics_config()
        logger.info(f"[{request_id}] Configuration loaded successfully")
        
        # Create analytics agent using factory
        analytics_agents = agent_factory.list_available_agents()
        analytics_agent_ids = [agent["agent_id"] for agent in analytics_agents if "analytics" in agent["agent_id"].lower()]
        
        if not analytics_agent_ids:
            logger.warning(f"[{request_id}] No analytics agents found")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'query': query,
                    'result': 'No analytics agents available'
                })
            }
        
        logger.info(f"[{request_id}] Using analytics agents: {analytics_agent_ids}")
        
        # Create orchestrator with analytics agents
        orchestrator = agent_factory.create_conversational_orchestrator(
            agent_ids=analytics_agent_ids,
            session_id=request_id,
            config=config,
            session=session
        )
        logger.info(f"[{request_id}] Analytics orchestrator created")
        
        try:
            # Process query through orchestrator
            logger.info(f"[{request_id}] Processing query through orchestrator")
            
            # Try different methods based on what's available
            if hasattr(orchestrator, 'invoke'):
                result = orchestrator.invoke(query)
            elif hasattr(orchestrator, '__call__'):
                result = orchestrator(query)
            else:
                # Log available methods for debugging
                available_methods = [method for method in dir(orchestrator) if not method.startswith('_') and callable(getattr(orchestrator, method))]
                logger.error(f"[{request_id}] No suitable method found. Available methods: {available_methods}")
                raise AttributeError(f"Orchestrator has no invoke method. Available: {available_methods}")
            
            logger.info(f"[{request_id}] Query processing completed")
            
            # Format response
            response = {
                'statusCode': 200,
                'body': json.dumps({
                    'query': query,
                    'result': str(result)
                })
            }
            
            logger.info(f"[{request_id}] Returning successful response")
            logger.debug(f"[{request_id}] Response: {response}")
            return response
            
        finally:
            # Clean up orchestrator resources
            try:
                if hasattr(orchestrator, '__exit__'):
                    orchestrator.__exit__(None, None, None)
                elif hasattr(orchestrator, 'close'):
                    orchestrator.close()
                logger.info(f"[{request_id}] Orchestrator resources cleaned up")
            except Exception as e:
                logger.warning(f"[{request_id}] Error cleaning up orchestrator: {e}")
        
    except Exception as e:
        logger.error(f"[{request_id}] Error in agentcore analytics processor: {str(e)}")
        return {
            'statusCode': 200,
            'body': json.dumps({
                'query': event.get('query', 'Unknown'),
                'result': f'Error: {str(e)}'
            })
        }