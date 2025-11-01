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
    cloudwatch_document_logs,
    cloudwatch_logs,
    dynamodb_query,
    dynamodb_record,
    dynamodb_status,
    lambda_lookup,
    stepfunction_details,
    xray_performance_analysis,
    xray_trace,
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
        cloudwatch_document_logs,
        cloudwatch_logs,
        dynamodb_record,
        dynamodb_status,
        dynamodb_query,
        lambda_lookup,
        stepfunction_details,
        xray_trace,
        xray_performance_analysis,
    ]
    bedrock_model = create_strands_bedrock_model(
        model_id=config.agents.error_analyzer.model_id, boto_session=session
    )

    return strands.Agent(
        tools=tools,
        system_prompt=config.agents.error_analyzer.system_prompt,
        model=bedrock_model,
    )
