# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Search tool for natural language queries"""

import logging
from typing import Any, Dict
from .base import IDPTool

logger = logging.getLogger(__name__)


class SearchTool(IDPTool):
    """Natural language search and analytics for IDP"""

    def execute(self, query: str, **kwargs) -> Dict[str, Any]:
        """Execute search query using analytics agent"""
        from idp_common.agents.analytics.config import get_analytics_config
        from idp_common.agents.analytics.agent import create_analytics_agent
        import boto3

        if not query:
            return {"error": "No query provided"}

        try:
            session = boto3.Session()
            config = get_analytics_config()
            agent = create_analytics_agent(config=config, session=session)

            result = agent(query)

            return {
                "success": True,
                "query": query,
                "result": str(result)
            }

        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return {
                "success": False,
                "query": query,
                "error": str(e)
            }
