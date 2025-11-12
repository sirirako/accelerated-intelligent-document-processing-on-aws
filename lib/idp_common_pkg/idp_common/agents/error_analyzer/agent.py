# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Error Analyzer Agent - Enhanced with modular tools.
"""

import logging
from typing import Optional

import boto3
import strands

from idp_common.config import get_config

from ..common.strands_bedrock_model import create_strands_bedrock_model
from .tools import (
    analyze_document_trace,
    analyze_system_performance,
    analyze_workflow_execution,
    fetch_document_record,
    fetch_recent_records,
    retrieve_document_context,
    search_cloudwatch_logs,
    search_performance_issues,
)

logger = logging.getLogger(__name__)


def create_error_analyzer_agent(
    session: Optional[boto3.Session] = None,
    **kwargs,
) -> strands.Agent:
    """
    Creates configured error analyzer agent with AWS integrations.
    Create the Error Analyzer Agent with modular tools.

    Args:
        config: Legacy configuration (deprecated)
        session: Boto3 session
        pattern_config: Pattern configuration containing agents section
        **kwargs: Additional arguments
    """
    config = get_config(as_model=True)

    # Create session if not provided
    if session is None:
        session = boto3.Session()

    # Create agent with specific tools - let LLM choose directly
    tools = [
        search_cloudwatch_logs,
        search_performance_issues,
        fetch_document_record,
        fetch_recent_records,
        retrieve_document_context,
        analyze_workflow_execution,
        analyze_document_trace,
        analyze_system_performance,
    ]
    bedrock_model = create_strands_bedrock_model(
        model_id=config.agents.error_analyzer.model_id, boto_session=session
    )

    return strands.Agent(
        tools=tools,
        system_prompt=config.agents.error_analyzer.system_prompt,
        model=bedrock_model,
    )
