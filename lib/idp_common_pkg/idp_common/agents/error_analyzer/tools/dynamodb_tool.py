# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
DynamoDB tools for error analysis.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict

import boto3
from strands import tool

from ..config import create_error_response, create_response, decimal_to_float

logger = logging.getLogger(__name__)


@tool
def dynamodb_status(object_key: str) -> Dict[str, Any]:
    """
    Get the current processing status of a specific document.

    Retrieves document status, timestamps, and execution information from the
    DynamoDB tracking table to understand document processing state.
    If tracking table is unavailable, suggests using alternative tools.

    Use this tool to:
    - Check if a document is COMPLETED, FAILED, or IN_PROGRESS
    - Get document processing timestamps
    - Find the Step Function execution ARN
    - Verify document exists in the system

    Tool chaining: If tracking_available=False, use cloudwatch_document_logs or xray_trace instead.

    Example usage:
    - "What's the status of report.pdf?"
    - "Is lending_package.pdf completed?"
    - "Check the processing status of document xyz.pdf"

    Args:
        object_key: Document filename/S3 object key (e.g., "report.pdf", "lending_package.pdf")

    Returns:
        Dict with keys:
        - tracking_available (bool): Whether tracking table is configured
        - document_found (bool): Whether document exists in tracking table
        - object_key (str): The document identifier
        - status (str): Processing status (COMPLETED, FAILED, IN_PROGRESS) if found
        - initial_event_time (str): When processing started if found
        - completion_time (str): When processing finished if found
        - execution_arn (str): Step Function execution ARN if found
        - suggestion (str): Alternative tools to use if tracking unavailable
    """
    result = dynamodb_record(object_key)

    if result.get("document_found"):
        document = result.get("document", {})
        response = create_response(
            {
                "tracking_available": True,
                "document_found": True,
                "object_key": object_key,
                "status": document.get("ObjectStatus")
                or document.get("WorkflowStatus"),
                "initial_event_time": document.get("InitialEventTime"),
                "completion_time": document.get("CompletionTime"),
                "execution_arn": document.get("WorkflowExecutionArn")
                or document.get("ExecutionArn"),
            }
        )
        logger.info(f"DynamoDB status response for {object_key}: {response}")
        return response
    return result


@tool
def dynamodb_query(
    date: str = "", hours_back: int = 24, limit: int = 100
) -> Dict[str, Any]:
    """
    Query DynamoDB tracking table using efficient time-based partition scanning.
    Searches through time-partitioned data to find documents processed within the specified timeframe.
    Uses optimized querying to minimize DynamoDB read costs.
    If tracking table is unavailable, suggests using alternative tools.

    Use this tool to:
    - Find documents processed in a specific time window
    - Analyze processing patterns and volumes
    - Identify recent document processing activity

    Tool chaining: If tracking_available=False, use cloudwatch_logs or xray_performance_analysis for system-wide analysis.

    Example usage:
    - "Show me documents processed today"
    - "What documents were processed in the last 2 hours?"
    - "Find all documents processed on 2024-01-15"

    Args:
        date: Date in YYYY-MM-DD format (defaults to today)
        hours_back: Number of hours to look back from date (default 24)
        limit: Maximum number of items to return

    Returns:
        Dict with keys:
        - tracking_available (bool): Whether tracking table is configured
        - items_found (int): Number of documents found
        - items (list): Document records if found
        - table_name (str): Table name if available
        - query_date (str): Date queried
        - hours_back (int): Hours looked back
        - suggestion (str): Alternative tools to use if tracking unavailable
    """
    try:
        tracking_table, table_name = _get_tracking_table()
        if not tracking_table:
            return create_response(
                {
                    "tracking_available": False,
                    "reason": "Tracking table not configured",
                    "items_found": 0,
                    "items": [],
                    "suggestion": "Try using CloudWatch logs or X-Ray traces for analysis",
                }
            )

        # Use current date if not provided
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        # Generate time-based partition keys to query
        base_date = datetime.strptime(date, "%Y-%m-%d")
        end_time = base_date + timedelta(days=1)
        start_time = end_time - timedelta(hours=hours_back)

        all_items = []
        current_time = start_time

        # Query by hour partitions for efficiency
        while current_time < end_time and len(all_items) < limit:
            hour_str = current_time.strftime("%Y-%m-%dT%H")

            # Query the list partition for this hour
            partition_key = f"list#{current_time.strftime('%Y-%m-%d')}#s#{current_time.hour // 4:02d}"
            sort_key_prefix = f"ts#{hour_str}"

            try:
                response = tracking_table.query(
                    KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
                    ExpressionAttributeValues={
                        ":pk": partition_key,
                        ":sk_prefix": sort_key_prefix,
                    },
                    Limit=min(limit - len(all_items), 50),
                )

                items = response.get("Items", [])
                all_items.extend(items)

            except Exception as query_error:
                logger.debug(f"Query failed for {partition_key}: {query_error}")

            current_time += timedelta(hours=1)

        items = [decimal_to_float(item) for item in all_items[:limit]]

        response = create_response(
            {
                "tracking_available": True,
                "table_name": table_name,
                "items_found": len(items),
                "items": items,
                "query_date": date,
                "hours_back": hours_back,
            }
        )
        logger.info(f"DynamoDB query response for date={date}: {response}")
        return response

    except Exception as e:
        return _handle_dynamodb_error(
            "query", f"date={date}", e, items_found=0, items=[]
        )


@tool
def dynamodb_record(object_key: str) -> Dict[str, Any]:
    """
    Retrieve complete document record with all metadata from tracking table.

    Gets the full document record including processing details, timestamps,
    configuration, and execution information for comprehensive analysis.
    If tracking table is unavailable, suggests using alternative tools.

    Use this tool to:
    - Get complete document processing details
    - Access all document metadata and configuration
    - Retrieve processing timestamps and execution info
    - Get detailed document attributes

    Tool chaining: If tracking_available=False, use cloudwatch_document_logs,
    xray_trace, or lambda_lookup for document analysis.

    Example usage:
    - "Get full details for document report.pdf"
    - "Show me all information about lending_package.pdf"
    - "Retrieve complete record for document xyz.pdf"

    Args:
        object_key: Document filename/S3 object key (e.g., "report.pdf", "lending_package.pdf")

    Returns:
        Dict with keys:
        - tracking_available (bool): Whether tracking table is configured
        - document_found (bool): Whether document exists
        - document (dict): Complete document record with all fields if found
        - object_key (str): The document identifier
        - reason (str): Explanation if document not found or tracking unavailable
        - suggestion (str): Alternative tools to use if tracking unavailable
    """
    try:
        tracking_table, table_name = _get_tracking_table()
        if not tracking_table:
            return create_response(
                {
                    "tracking_available": False,
                    "reason": "Tracking table not configured",
                    "document_found": False,
                    "object_key": object_key,
                    "suggestion": "Try using CloudWatch logs or X-Ray traces for document analysis",
                }
            )

        # Direct key lookup
        dynamodb_response = tracking_table.get_item(
            Key={"PK": f"doc#{object_key}", "SK": "none"}
        )

        if "Item" in dynamodb_response:
            document_item = decimal_to_float(dynamodb_response["Item"])
            response = create_response(
                {
                    "tracking_available": True,
                    "document_found": True,
                    "document": document_item,
                    "object_key": object_key,
                }
            )
            logger.info(f"DynamoDB record response for {object_key}: {response}")
            return response
        else:
            response = create_response(
                {
                    "tracking_available": True,
                    "document_found": False,
                    "object_key": object_key,
                    "reason": f"Document not found for key: {object_key}",
                }
            )
            logger.info(
                f"DynamoDB record not found response for {object_key}: {response}"
            )
            return response

    except Exception as e:
        return _handle_dynamodb_error(
            "lookup", object_key, e, document_found=False, object_key=object_key
        )


def _get_tracking_table():
    """
    Internal utility to get tracking table resource with validation.

    Returns:
        Tuple of (table_resource, table_name) or (None, None) if not configured
    """
    table_name = os.environ.get("TRACKING_TABLE_NAME", "")
    if not table_name:
        return None, None

    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(table_name), table_name


def _handle_dynamodb_error(
    operation: str, identifier: str, error: Exception, **kwargs
) -> Dict[str, Any]:
    """
    Standardized error handling for DynamoDB operations.

    Args:
        operation: Operation being performed (e.g., "lookup", "query")
        identifier: Document key or operation identifier
        error: Exception that occurred
        **kwargs: Additional error response fields

    Returns:
        Standardized error response
    """
    logger.error(f"DynamoDB {operation} failed for '{identifier}': {error}")
    return create_error_response(str(error), **kwargs)
