# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Athena Query Tool for executing SQL queries using Strands framework.
"""

import logging
import time
from typing import Any, Dict

import boto3
from strands import tool

logger = logging.getLogger(__name__)


@tool
def run_athena_query(query: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a SQL query on Amazon Athena.

    Uses boto3 to execute the query on Athena and returns the results.

    Args:
        query: SQL query string to execute
        config: Configuration dictionary containing Athena settings

    Returns:
        Dict containing either query results or error information
    """
    try:
        # Create Athena client
        athena_client = boto3.client("athena", region_name=config.get("aws_region"))

        # Start query execution
        logger.info(f"Executing Athena query: {query}")
        response = athena_client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={"Database": config["athena_database"]},
            ResultConfiguration={"OutputLocation": config["athena_output_location"]},
        )

        query_execution_id = response["QueryExecutionId"]
        logger.info(f"Query execution ID: {query_execution_id}")

        # Wait for query to complete by polling its status
        max_polling_attempts = config.get("max_polling_attempts", 20)
        attempts = 0
        state = "RUNNING"  # Initialize state

        while attempts < max_polling_attempts:
            response = athena_client.get_query_execution(
                QueryExecutionId=query_execution_id
            )
            state = response["QueryExecution"]["Status"]["State"]
            if state == "SUCCEEDED":
                logger.info("Query succeeded!")
                break
            elif state in ["FAILED", "CANCELLED"]:
                logger.error(f"Query {state.lower()}.")
                break
            else:
                logger.debug(f"Query state: {state}, sleeping for 2 seconds (attempt {attempts+1}/{max_polling_attempts})")
                time.sleep(2)
                attempts += 1

        # Check final state
        if state == "SUCCEEDED":
            # Get query results
            results = athena_client.get_query_results(
                QueryExecutionId=query_execution_id
            )

            # Process results
            columns = [
                col["Label"]
                for col in results["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
            ]
            rows = results["ResultSet"]["Rows"][1:]  # Skip header row

            data = []
            for row in rows:
                item = {}
                for i, value in enumerate(row["Data"]):
                    # Handle null values
                    if "VarCharValue" in value:
                        item[columns[i]] = value["VarCharValue"]
                    else:
                        item[columns[i]] = None
                data.append(item)

            logger.info(f"Query returned {len(data)} rows")
            return {"success": True, "data": data, "query": query}
        elif state == "RUNNING":
            # Query is still running after max polling attempts
            logger.warning(f"Query still running after {max_polling_attempts} polling attempts. Query execution ID: {query_execution_id}")
            return {
                "success": False,
                "error": f"Query timed out after {max_polling_attempts} polling attempts. The query is still running in Athena and may complete later.",
                "query": query,
                "query_execution_id": query_execution_id,
                "state": "RUNNING"
            }
        else:
            # Query failed
            error_message = response["QueryExecution"]["Status"].get(
                "StateChangeReason", "Query failed with an Unknown error"
            )
            error_details = response["QueryExecution"]["Status"].get(
                "AthenaError", {})
            logger.error(
                f"Query failed with state {state}. Reason: {error_message}"
            )

            return {
                "success": False,
                "error": error_message,
                "state": state,
                "athena_error_details": error_details,
                "query": query,
            }

    except Exception as e:
        logger.exception("Error executing Athena query")
        return {"success": False, "error": str(e), "query": query}
