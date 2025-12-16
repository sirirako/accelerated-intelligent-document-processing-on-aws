# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Lambda function for AgentCore Gateway analytics processing.
Provides analytics tools through AgentCore Gateway's built-in MCP server.
"""

import json
import logging
import time
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError, EventStreamError

from idp_common.agents.analytics.config import get_analytics_config
from idp_common.agents.common.config import configure_logging
from idp_common.agents.analytics.agent import create_analytics_agent

# Configure logging for both application and Strands framework
configure_logging()

# Get logger for this module
logger = logging.getLogger(__name__)

# Cache at module level
_session = None
_config = None

def log_analytics_events(context_msg: str = ""):
    """Helper to log analytics events safely."""
    try:
        from idp_common.agents.analytics.analytics_logger import analytics_logger
        events = analytics_logger.get_events()
        if events:
            logger.info(f"Analytics Events {context_msg}:")
            logger.info(f"{'TOOL':<40} {'TIME':<8}")
            logger.info("-" * 48)
            total_time = 0.0
            for event, duration_str in events.items():
                logger.info(f"{event:<40} {duration_str}s")
                total_time += float(duration_str)
            logger.info("-" * 48)
            logger.info(f"{'TOTAL':<40} {total_time:.2f}s")
        else:
            logger.info(f"No analytics events recorded {context_msg}")
    except Exception as e:
        logger.warning(f"Failed to log analytics events: {e}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Process analytics queries through agent."""
    global _session, _config
    
    query = event.get('query')
    if not query:
        return {
            'statusCode': 200,
            'body': json.dumps({'query': '', 'result': 'No query provided'})
        }
    
    try:
        # Reuse session and config across warm starts
        if _session is None:
            _session = boto3.Session()
        if _config is None:
            _config = get_analytics_config()
        
        # Create analytics agent directly
        agent = create_analytics_agent(config=_config, session=_session)

        start_time = time.time()
        logger.info(f"Query:[{query}]")
        result = agent(query)
        elapsed = time.time() - start_time
        # Log events
        log_analytics_events("[SUCCESS]")
        logger.info(f"Process completed in {elapsed:.2f}s")
        return {
            'statusCode': 200,
            'body': json.dumps({'query': query, 'result': str(result)})
        }
    except Exception as e:
        # Log events
        log_analytics_events("[ERROR]")
        
        # Determine message
        error_str = str(e).lower()
        error_code = getattr(e, 'response', {}).get('Error', {}).get('Code', '') if isinstance(e, (EventStreamError, ClientError)) else ''
        
        if 'unavailable' in error_str or error_code in ['ThrottlingException', 'ServiceUnavailable']:
            message = 'Service temporarily unavailable due to high demand. Please retry in a moment.'
        elif isinstance(e, (EventStreamError, ClientError)):
            message = f'Error: {str(e)}'
        else:
            message = 'An error occurred processing your request. Please try again.'
        
        # Single logging point
        logger.error(f"Query failed: {e}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({'query': query, 'result': message})
        }