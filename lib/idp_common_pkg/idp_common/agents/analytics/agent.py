# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Analytics Agent implementation using Strands framework.
"""

import json
import logging
import os
import re
from typing import Any, Dict

import boto3
from strands import Agent, tool
from strands.models import BedrockModel

from ..common.dynamodb_logger import DynamoDBMessageTracker
from .config import load_result_format_description
from .tools import generate_plot, get_database_info, run_athena_query

logger = logging.getLogger(__name__)


def extract_json_from_markdown(response: str) -> str:
    """
    Extract JSON content from markdown code blocks.

    The LLM often returns JSON wrapped in markdown code blocks like:
    ```json
    {"key": "value"}
    ```

    This function extracts the JSON content between the code block markers.

    Args:
        response: The raw response string from the LLM

    Returns:
        The extracted JSON string, or the original response if no code blocks found
    """
    # Pattern to match ```json ... ``` or ``` ... ``` code blocks
    json_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"

    match = re.search(json_pattern, response, re.DOTALL | re.IGNORECASE)
    if match:
        extracted_json = match.group(1).strip()
        logger.debug(
            f"Extracted JSON from markdown code block: {extracted_json[:100]}..."
        )
        return extracted_json

    # If no code blocks found, return the original response
    logger.debug("No markdown code blocks found, returning original response")
    return response.strip()


def parse_agent_response(response) -> Dict[str, Any]:
    """
    Parse the agent response, handling Strands AgentResult objects.

    Args:
        response: The response from the Strands agent (AgentResult)

    Returns:
        Parsed JSON response as a dictionary

    Raises:
        ValueError: If the response is not a valid AgentResult
    """
    # Check if response is a Strands AgentResult
    if not hasattr(response, "__str__"):
        raise ValueError(f"Expected Strands AgentResult, got {type(response)}")

    # Convert AgentResult to string using its __str__ method
    response_str = str(response)
    logger.debug(f"Processing AgentResult as string: {response_str[:100]}...")

    # Extract JSON from markdown code blocks if present
    json_str = extract_json_from_markdown(response_str)

    try:
        parsed_response = json.loads(json_str)
        logger.debug(
            f"Successfully parsed JSON response with type: {parsed_response.get('responseType', 'unknown')}"
        )
        return parsed_response
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse extracted JSON: {e}")
        logger.error(f"Extracted content: {json_str}")
        # Return a text response with the raw output as fallback
        return {"responseType": "text", "content": response_str}


def create_analytics_agent(
    config: Dict[str, Any],
    session: boto3.Session,
    job_id: str = None,
    user_id: str = None,
    enable_monitoring: bool = None,
) -> Agent:
    """
    Create and configure the analytics agent with appropriate tools and system prompt.

    Args:
        config: Configuration dictionary containing Athena settings and other parameters
        session: Boto3 session for AWS operations
        job_id: Analytics job ID for monitoring (optional)
        user_id: User ID for monitoring (optional)
        enable_monitoring: Whether to enable agent monitoring (defaults to env var or True)

    Returns:
        Agent: Configured Strands agent instance
    """
    # Load the output format description
    final_result_format = load_result_format_description()

    # Define the system prompt for the analytics agent
    system_prompt = f"""
    You are an AI agent that converts natural language questions into SQL queries, executes those queries, and writes python code to convert the query results into json representing either a plot, a table, or a string.
    
    # Task
    Your task is to:
    1. Understand the user's question
    2. Use get_database_info tool to understand the database schema
    3. Generate a valid SQL query that answers the question
    4. Execute the query using the run_athena_query tool. If you receive an error message, correct your SQL query and try again a maximum of 3 times.
    5. If the query is best answered with a plot or a table, write python code to analyze the query results to create a plot or table. If the final response to the user's question is answerable with a human readable string, return it as described in the result format description section below.
    6. To execute your plot generation code, use the generate_plot tool and directly return its output without doing any more analysis.
    
    When generating SQL:
    - Use standard SQL syntax compatible with Amazon Athena, for example use standard date arithmetic that's compatible with Athena.
    - Include appropriate table joins when needed
    - Use column names exactly as they appear in the schema
    - Always use the run_athena_query tool to execute your queries
    
    When writing python:
    - Only write python code to generate plots or tables. Do not use python for any other purpose.
    - Make sure the python code will output json representing either "table" or "plotData" responseType as described in the above description of the result format
    - Use built in python libraries, optionally with pandas
    - Always use the generate_plot tool to execute your python code
    
    # Result format
    
    Here is a description of the result format:
    ```markdown
    {final_result_format}
    ```
    
    Your final response should be directly parsable as json with no additional text before or after. The json should conform to the result format description shown above, with top level key "responseType" being one of "yyotData", "table", or "text".
    """

    # Create a new tool function that directly calls run_athena_query with the config
    @tool
    def run_athena_query_with_config(query: str) -> Dict[str, Any]:
        """
        Execute a SQL query on Amazon Athena.

        Args:
            query: SQL query string to execute

        Returns:
            Dict containing either query results or error information
        """
        return run_athena_query(query, config)

    # Create the agent with tools and system prompt
    tools = [run_athena_query_with_config, generate_plot, get_database_info]

    # Default is Claude 4 which gets throttled on dev machines
    bedrock_model = BedrockModel(
        model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0", boto_session=session
    )

    agent = Agent(tools=tools, system_prompt=system_prompt, model=bedrock_model)

    # Add monitoring if enabled and job context is provided
    if enable_monitoring is None:
        enable_monitoring = (
            os.environ.get("ENABLE_AGENT_MONITORING", "true").lower() == "true"
        )

    if enable_monitoring and job_id and user_id:
        try:
            message_tracker = DynamoDBMessageTracker(
                job_id=job_id, user_id=user_id, enabled=enable_monitoring
            )
            agent.hooks.add_hook(message_tracker)
            logger.info(f"Agent monitoring enabled for job {job_id}")
        except Exception as e:
            logger.warning(f"Failed to initialize agent monitoring: {e}")
    elif enable_monitoring:
        logger.warning("Agent monitoring enabled but job_id or user_id not provided")

    logger.info("Analytics agent created successfully")
    return agent
