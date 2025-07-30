# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Analytics Agent implementation using Strands framework.
"""

import logging
import os
from typing import Any, Dict

import boto3
from strands import Agent, tool
from strands.models import BedrockModel

from ..common.dynamodb_logger import DynamoDBMessageTracker
from .config import load_python_plot_generation_examples, load_result_format_description
from .tools import CodeInterpreterTools, get_database_info, run_athena_query
from .utils import register_code_interpreter_tools

logger = logging.getLogger(__name__)


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
    # Load python code examples
    python_plot_generation_examples = load_python_plot_generation_examples()

    # Define the system prompt for the analytics agent
    system_prompt = f"""
    You are an AI agent that converts natural language questions into SQL queries, executes those queries, and writes python code to convert the query results into json representing either a plot, a table, or a string.
    
    # Task
    Your task is to:
    1. Understand the user's question
    2. Use get_database_info tool to understand the database schema
    3. Generate a valid SQL query that answers the question
    4. Execute the query using the run_athena_query tool. If you receive an error message, correct your SQL query and try again a maximum of 3 times, then STOP. Do not ever make up fake data.
    4. Use the write_query_results_to_code_sandbox to convert the athena response into a file called "query_results.csv" in the same environment future python scripts will be executed.
    5. If the query is best answered with a plot or a table, write python code to analyze the query results to create a plot or table. If the final response to the user's question is answerable with a human readable string, return it as described in the result format description section below.
    6. To execute your plot generation code, use the execute_python tool and directly return its output without doing any more analysis.
    
    When generating SQL:
    - Use standard SQL syntax compatible with Amazon Athena, for example use standard date arithmetic that's compatible with Athena.
    - Include appropriate table joins when needed
    - Use column names exactly as they appear in the schema
    - Always use the run_athena_query tool to execute your queries
    - If you cannot get your query to work successfully, stop. Do not generate fake or synthetic data.
    
    When writing python:
    - Only write python code to generate plots or tables. Do not use python for any other purpose.
    - The python code should read the query results from "query_results.csv" file provided, for example with a line like `df = pd.read_csv("query_results.csv")`
    - Make sure the python code will output json representing either "table" or "plotData" responseType as described in the above description of the result format.
    - Use built in python libraries, optionally with pandas or matplotlib.
    - Always use the execute_python tool to execute your python code, and be sure to include the reset_state=True flag each time you call this tool.
    
    # Here are some python code examples to guide you:
    {python_plot_generation_examples}
    
    # Result format
    Here is a description of the result format:
    ```markdown
    {final_result_format}
    ```
    
    Your final response should be directly parsable as json with no additional text before or after. The json should conform to the result format description shown above, with top level key "responseType" being one of "plotData", "table", or "text". You may have to clean up the output of the python code if, for example, it contains extra strings from logging or otherwise. Return only directly parsable json in your final response.
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

    # Initialize code interpreter tools
    code_interpreter_tools = CodeInterpreterTools(session)

    # Register for cleanup
    register_code_interpreter_tools(code_interpreter_tools)

    # Create the agent with tools and system prompt
    tools = [
        run_athena_query_with_config,
        code_interpreter_tools.write_query_results_to_code_sandbox,
        code_interpreter_tools.execute_python,
        get_database_info,
    ]

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
            # Add DynamoDB message tracker for persistence
            message_tracker = DynamoDBMessageTracker(
                job_id=job_id, user_id=user_id, enabled=enable_monitoring
            )
            agent.hooks.add_hook(message_tracker)
            logger.info(f"DynamoDB message tracking enabled for job {job_id}")

            # Also add the AgentMonitor for CloudWatch logging
            from ..common.monitoring import AgentMonitor

            agent_monitor = AgentMonitor(
                log_level=logging.INFO, enable_detailed_logging=True
            )
            agent.hooks.add_hook(agent_monitor)
            logger.info(f"CloudWatch agent monitoring enabled for job {job_id}")

        except Exception as e:
            logger.warning(f"Failed to initialize agent monitoring: {e}")
    elif enable_monitoring:
        logger.warning("Agent monitoring enabled but job_id or user_id not provided")

    logger.info("Analytics agent created successfully")
    return agent
