# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
CloudWatch tools for error analysis.
"""

import logging
import os
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List

import boto3
from strands import tool

from ..config import create_error_response, safe_int_conversion
from .dynamodb_tool import dynamodb_record
from .models import LogEvent
from .xray_tool import extract_lambda_request_ids

logger = logging.getLogger(__name__)


# =============================================================================
# PUBLIC TOOL FUNCTIONS
# =============================================================================


@tool
def cloudwatch_document_logs(
    document_id: str,
    stack_name: str,
    filter_pattern: str = "ERROR",
    max_log_events: int = None,
    max_log_groups: int = 20,
) -> Dict[str, Any]:
    """
    Search CloudWatch logs for errors related to a specific document.

    Performs targeted log analysis using document execution context, X-Ray traces,
    and Lambda request IDs to find precise error information for document processing failures.

    Use this tool to:
    - Find specific errors for a failed document
    - Get detailed error messages with timestamps
    - Identify which Lambda function failed
    - Analyze document processing timeline

    Example usage:
    - "Find errors for document report.pdf"
    - "What went wrong with lending_package.pdf?"
    - "Show me the logs for document xyz.pdf"

    Args:
        document_id: Document filename/ObjectKey (e.g., "report.pdf", "lending_package.pdf")
        stack_name: CloudFormation stack name for log group discovery
        filter_pattern: CloudWatch filter pattern - "ERROR", "Exception", "Failed" (default: "ERROR")
        max_log_events: Maximum log events per group to return (default: 10, max: 50)
        max_log_groups: Maximum log groups to search (default: 20, max: 50)

    Returns:
        Dict with keys:
        - analysis_type (str): "document_specific" or "document_not_found"
        - document_id (str): The document being analyzed
        - total_events_found (int): Number of error events found
        - results (list): Log search results with events and metadata
        - log_search_strategy (dict): Strategy used for log searching
        - document_processing_time_window (dict): Time window used for search
    """
    try:
        # Use safe integer conversion with defaults
        max_log_events = safe_int_conversion(max_log_events, 10)
        max_log_groups = safe_int_conversion(max_log_groups, 20)
        # Get document context from DynamoDB tracking table
        dynamodb_response = dynamodb_record(document_id)

        if not dynamodb_response.get("document_found"):
            return {
                "analysis_type": "document_not_found",
                "document_id": document_id,
                "error": dynamodb_response.get(
                    "reason", "Document not found in tracking table"
                ),
                "events_found": 0,
                "tracking_available": dynamodb_response.get(
                    "tracking_available", False
                ),
            }

        document_record = dynamodb_response.get("document", {})

        # Get log group prefix
        prefix_info = _get_log_group_prefix(stack_name)
        if "error" in prefix_info:
            return {
                "error": f"Failed to get log prefix: {prefix_info['error']}",
                "events_found": 0,
            }

        log_prefix = prefix_info.get("log_group_prefix")
        log_groups = _get_cloudwatch_log_groups(prefix=log_prefix)
        logger.info(
            f"Found {log_groups.get('log_groups_found', 0)} log groups with prefix '{log_prefix}'"
        )

        if log_groups.get("log_groups_found", 0) > 0:
            group_names = [g["name"] for g in log_groups.get("log_groups", [])]
            logger.info(f"Log group names: {group_names[:3]}...")  # Show first 3

        if log_groups.get("log_groups_found", 0) == 0:
            return {
                "document_id": document_id,
                "log_prefix": log_prefix,
                "events_found": 0,
                "message": "No log groups found",
            }

        # Extract processing time window from DynamoDB record
        document_start_time = None
        document_end_time = None

        initial_event_time = document_record.get("InitialEventTime")
        completion_time = document_record.get("CompletionTime")

        if initial_event_time:
            document_start_time = datetime.fromisoformat(
                initial_event_time.replace("Z", "+00:00")
            )
        if completion_time:
            document_end_time = datetime.fromisoformat(
                completion_time.replace("Z", "+00:00")
            )

        # Add buffer for batch operation isolation
        if document_start_time and document_end_time:
            processing_duration = document_end_time - document_start_time
            time_buffer = min(timedelta(minutes=2), processing_duration * 0.1)
            document_start_time = document_start_time - time_buffer
            document_end_time = document_end_time + time_buffer
            logger.info(
                f"Using document processing window with {time_buffer.total_seconds()}s buffer for isolation"
            )

        # Extract X-Ray trace ID from DynamoDB record for Lambda request ID mapping
        xray_trace_id = document_record.get("XRayTraceId") or document_record.get(
            "TraceId"
        )
        lambda_function_to_request_id_map = {}

        if xray_trace_id:
            logger.info(
                f"Extracting Lambda request IDs from X-Ray trace: {xray_trace_id}"
            )
            lambda_function_to_request_id_map = extract_lambda_request_ids(
                xray_trace_id
            )
            logger.info(
                f"X-Ray trace analysis found {len(lambda_function_to_request_id_map)} Lambda functions with request IDs"
            )
        else:
            logger.warning("No X-Ray trace ID found in document record")

        all_lambda_request_ids = list(lambda_function_to_request_id_map.values())
        document_status = document_record.get("Status")
        step_function_execution_arn = document_record.get("ExecutionArn")

        # Determine failed functions based on document status
        failed_lambda_functions = []
        primary_failed_lambda_function = None

        if document_status == "FAILED":
            # For failed documents, prioritize functions that likely failed
            # This is a heuristic - in practice you might have more specific failure info
            if lambda_function_to_request_id_map:
                # Assume the last function in the map might be the failed one
                primary_failed_lambda_function = list(
                    lambda_function_to_request_id_map.keys()
                )[-1]
                failed_lambda_functions = [primary_failed_lambda_function]
                logger.info(
                    f"Document failed - prioritizing function: {primary_failed_lambda_function}"
                )

        # Priority 1: Request IDs from failed Lambda functions (highest priority)
        failed_lambda_request_ids = []
        if (
            primary_failed_lambda_function
            and primary_failed_lambda_function in lambda_function_to_request_id_map
        ):
            primary_failed_request_id = lambda_function_to_request_id_map[
                primary_failed_lambda_function
            ]
            failed_lambda_request_ids.append(primary_failed_request_id)
            logger.info(
                f"Primary failed Lambda function '{primary_failed_lambda_function}' has request ID: {primary_failed_request_id}"
            )

        # Add other failed Lambda function request IDs
        for failed_function_name in failed_lambda_functions:
            if failed_function_name in lambda_function_to_request_id_map:
                failed_request_id = lambda_function_to_request_id_map[
                    failed_function_name
                ]
                if failed_request_id not in failed_lambda_request_ids:
                    failed_lambda_request_ids.append(failed_request_id)
                    logger.info(
                        f"Failed Lambda function '{failed_function_name}' has request ID: {failed_request_id}"
                    )

        # Priority 2: All other Lambda request IDs (medium priority)
        other_lambda_request_ids = [
            request_id
            for request_id in all_lambda_request_ids
            if request_id not in failed_lambda_request_ids
        ]

        # Priority 3: Step Functions execution-based search (fallback only)
        step_function_execution_patterns = []
        if step_function_execution_arn and not failed_lambda_request_ids:
            execution_name = step_function_execution_arn.split(":")[-1]
            step_function_execution_patterns.append(execution_name)
            logger.info(
                f"Using Step Functions execution pattern as fallback: {execution_name}"
            )

        # Build prioritized log search strategy
        log_search_strategy = {
            "failed_lambda_request_ids": failed_lambda_request_ids,
            "other_lambda_request_ids": other_lambda_request_ids,
            "step_function_execution_patterns": step_function_execution_patterns,
        }

        # Search logs with prioritized strategy
        all_results = []
        total_events = 0
        groups_to_search = log_groups["log_groups"][:max_log_groups]

        # Search with failed Lambda function request IDs (highest priority)
        for failed_lambda_request_id in log_search_strategy[
            "failed_lambda_request_ids"
        ]:
            # Find Lambda function name for this request ID
            lambda_function_name = next(
                (
                    func_name
                    for func_name, req_id in lambda_function_to_request_id_map.items()
                    if req_id == failed_lambda_request_id
                ),
                "Unknown",
            )
            logger.info(
                f"Searching logs for failed Lambda function: {lambda_function_name}, request_id: {failed_lambda_request_id}"
            )

            for log_group in groups_to_search:
                log_group_name = log_group["name"]
                cloudwatch_search_result = _search_cloudwatch_logs(
                    log_group_name=log_group_name,
                    filter_pattern=filter_pattern,
                    max_events=max_log_events,
                    start_time=document_start_time,
                    end_time=document_end_time,
                    request_id=failed_lambda_request_id,
                )
                logger.debug(
                    f"CloudWatch search result for failed request ID '{failed_lambda_request_id}': {cloudwatch_search_result.get('events_found', 0)} events found"
                )

                if cloudwatch_search_result.get("events_found", 0) > 0:
                    logger.info(
                        f"Found {cloudwatch_search_result['events_found']} error events in {log_group_name} for failed Lambda request ID {failed_lambda_request_id}"
                    )

                    all_results.append(
                        {
                            "log_group": log_group_name,
                            "search_type": "failed_lambda_request_id",
                            "lambda_function_name": lambda_function_name,
                            "pattern_used": failed_lambda_request_id,
                            "events_found": cloudwatch_search_result["events_found"],
                            "events": cloudwatch_search_result["events"],
                        }
                    )
                    total_events += cloudwatch_search_result["events_found"]

            # If we found errors from failed Lambda functions, we have what we need
            if total_events > 0:
                logger.info(
                    f"Found {total_events} error events from failed Lambda function request IDs, stopping search"
                )
                break

        # Search with other Lambda request IDs if no errors found yet
        if total_events == 0 and log_search_strategy["other_lambda_request_ids"]:
            for other_lambda_request_id in log_search_strategy[
                "other_lambda_request_ids"
            ][:3]:  # Limit to first 3 for performance
                # Find Lambda function name for this request ID
                other_lambda_function_name = next(
                    (
                        func_name
                        for func_name, req_id in lambda_function_to_request_id_map.items()
                        if req_id == other_lambda_request_id
                    ),
                    "Unknown",
                )
                logger.info(
                    f"Searching logs for other Lambda function: {other_lambda_function_name}, request_id: {other_lambda_request_id}"
                )

                for log_group in groups_to_search:
                    log_group_name = log_group["name"]

                    other_search_result = _search_cloudwatch_logs(
                        log_group_name=log_group_name,
                        filter_pattern=filter_pattern,
                        max_events=max_log_events,
                        start_time=document_start_time,
                        end_time=document_end_time,
                        request_id=other_lambda_request_id,
                    )

                    if other_search_result.get("events_found", 0) > 0:
                        logger.info(
                            f"Found {other_search_result['events_found']} error events in {log_group_name} for other Lambda request ID {other_lambda_request_id}"
                        )

                        all_results.append(
                            {
                                "log_group": log_group_name,
                                "search_type": "other_lambda_request_id",
                                "lambda_function_name": other_lambda_function_name,
                                "pattern_used": other_lambda_request_id,
                                "events_found": other_search_result["events_found"],
                                "events": other_search_result["events"],
                            }
                        )
                        total_events += other_search_result["events_found"]

                if total_events > 0:
                    break

        # Fallback to Step Functions execution-based search if still no results
        if (
            total_events == 0
            and log_search_strategy["step_function_execution_patterns"]
        ):
            # Document-specific search using document ID for batch operation safety
            if total_events == 0:
                # Extract document identifier for precise filtering
                doc_identifier = document_id.replace(".pdf", "").replace(".", "-")

                for log_group in groups_to_search[:3]:  # Limit to first 3 groups
                    log_group_name = log_group["name"]
                    # Try document-specific search first
                    doc_search_result = _search_cloudwatch_logs(
                        log_group_name=log_group_name,
                        filter_pattern=doc_identifier,
                        max_events=max_log_events,
                        start_time=document_start_time,
                        end_time=document_end_time,
                    )

                    if doc_search_result.get("events_found", 0) > 0:
                        logger.info(
                            f"Found {doc_search_result['events_found']} document-specific events in {log_group_name}"
                        )

                        # Filter for actual errors in document-specific logs
                        document_error_events = []
                        for event in doc_search_result.get("events", []):
                            message = event.get("message", "")
                            if any(
                                error_term in message.upper()
                                for error_term in [
                                    "ERROR",
                                    "EXCEPTION",
                                    "FAILED",
                                    "TIMEOUT",
                                ]
                            ):
                                document_error_events.append(event)

                        if document_error_events:
                            logger.info(
                                f"Found {len(document_error_events)} actual errors in document-specific search"
                            )
                            for i, event in enumerate(document_error_events[:2]):
                                logger.info(
                                    f"Document Error {i + 1}: {event.get('message', '')[:300]}..."
                                )

                            all_results.append(
                                {
                                    "log_group": log_group_name,
                                    "search_type": "document_specific_error_search",
                                    "pattern_used": doc_identifier,
                                    "events_found": len(document_error_events),
                                    "events": document_error_events,
                                }
                            )
                            total_events += len(document_error_events)
                            break

                # Fallback to broad ERROR search only if document-specific search fails
                if total_events == 0:
                    for log_group in groups_to_search[
                        :2
                    ]:  # Further limit for broad search
                        log_group_name = log_group["name"]

                        fallback_search_result = _search_cloudwatch_logs(
                            log_group_name=log_group_name,
                            filter_pattern=filter_pattern,
                            max_events=max_log_events,
                            start_time=document_start_time,
                            end_time=document_end_time,
                        )

                        if fallback_search_result.get("events_found", 0) > 0:
                            logger.info(
                                f"Found {fallback_search_result['events_found']} events in {log_group_name} with broad error search fallback"
                            )

                            all_results.append(
                                {
                                    "log_group": log_group_name,
                                    "search_type": "broad_error_search_fallback",
                                    "pattern_used": filter_pattern,
                                    "events_found": fallback_search_result[
                                        "events_found"
                                    ],
                                    "events": fallback_search_result["events"],
                                    "warning": "May include errors from other concurrent documents",
                                }
                            )
                            total_events += fallback_search_result["events_found"]
                            break

            for step_function_pattern in log_search_strategy[
                "step_function_execution_patterns"
            ]:
                for log_group in groups_to_search:
                    log_group_name = log_group["name"]
                    execution_search_result = _search_cloudwatch_logs(
                        log_group_name=log_group_name,
                        filter_pattern=step_function_pattern,
                        max_events=max_log_events,
                        start_time=document_start_time,
                        end_time=document_end_time,
                    )
                    logger.debug(
                        f"CloudWatch search result for Step Functions execution pattern '{step_function_pattern}': {execution_search_result.get('events_found', 0)} events found"
                    )

                    if execution_search_result.get("events_found", 0) > 0:
                        logger.info(
                            f"Found {execution_search_result['events_found']} events in {log_group_name} with Step Functions execution pattern {step_function_pattern}"
                        )

                        all_results.append(
                            {
                                "log_group": log_group_name,
                                "search_type": "step_function_execution_fallback",
                                "pattern_used": step_function_pattern,
                                "events_found": execution_search_result["events_found"],
                                "events": execution_search_result["events"],
                            }
                        )
                        total_events += execution_search_result["events_found"]

                if total_events > 0:
                    break

        return {
            "analysis_type": "document_specific",
            "document_id": document_id,
            "document_status": document_status,
            "step_function_execution_arn": step_function_execution_arn,
            "xray_trace_id": xray_trace_id,
            "log_search_strategy": log_search_strategy,
            "extraction_method": "dynamodb_record_with_xray_trace",
            "failed_lambda_functions": failed_lambda_functions,
            "primary_failed_lambda_function": primary_failed_lambda_function,
            "lambda_function_to_request_id_map": lambda_function_to_request_id_map,
            "document_processing_time_window": {
                "start": document_start_time.isoformat()
                if document_start_time
                else None,
                "end": document_end_time.isoformat() if document_end_time else None,
            },
            "total_events_found": total_events,
            "log_groups_searched": len(groups_to_search),
            "log_groups_with_events": len(all_results),
            "results": all_results,
        }

    except Exception as e:
        logger.error(f"Document log search failed for {document_id}: {e}")
        return create_error_response(str(e), document_id=document_id, events_found=0)


@tool
def cloudwatch_logs(
    filter_pattern: str = "ERROR",
    hours_back: int = None,
    max_log_events: int = None,
    max_log_groups: int = 20,
) -> Dict[str, Any]:
    """
    Search CloudWatch logs across all stack services for system-wide error patterns.

    Performs comprehensive log analysis across all Lambda functions and services
    in the CloudFormation stack to identify system-wide issues and error patterns.

    Use this tool to:
    - Find recent system-wide errors and failures
    - Identify error patterns across multiple services
    - Analyze system health over time periods
    - Troubleshoot infrastructure-level issues

    Example usage:
    - "Show me recent errors in the system"
    - "Find all failures in the last 2 hours"
    - "What exceptions occurred today?"

    Args:
        filter_pattern: CloudWatch filter pattern - "ERROR", "Exception", "Failed", "Timeout" (default: "ERROR")
        hours_back: Hours to look back from now (default: 24, max: 168 for 1 week)
        max_log_events: Maximum events per log group (default: 10, max: 50)
        max_log_groups: Maximum log groups to search (default: 20, max: 50)

    Returns:
        Dict with keys:
        - stack_name (str): CloudFormation stack being analyzed
        - total_events_found (int): Total error events found
        - log_groups_searched (int): Number of log groups searched
        - results (list): Log search results from each group
        - filter_pattern (str): Pattern used for searching
        - log_prefix_used (str): Log group prefix used for discovery
    """
    stack_name = os.environ.get("AWS_STACK_NAME", "")

    if not stack_name:
        return {
            "error": "AWS_STACK_NAME not configured in environment",
            "events_found": 0,
        }

    try:
        # Use safe integer conversion with defaults
        max_log_events = safe_int_conversion(max_log_events, 10)
        max_log_groups = safe_int_conversion(max_log_groups, 20)
        hours_back = safe_int_conversion(hours_back, 24)
        logger.info(f"Starting log search for stack: {stack_name}")
        prefix_info = _get_log_group_prefix(stack_name)
        logger.info(f"Prefix info result: {prefix_info}")

        if "error" in prefix_info:
            logger.error(f"Failed to get log prefix: {prefix_info['error']}")
            return {
                "error": f"Failed to get log prefix: {prefix_info['error']}",
                "events_found": 0,
            }

        log_prefix = prefix_info.get("log_group_prefix")
        prefix_type = prefix_info.get("prefix_type")
        logger.info(f"Using log prefix: '{log_prefix}' (type: {prefix_type})")

        # Get log groups with the prefix
        log_groups = _get_cloudwatch_log_groups(prefix=log_prefix)
        logger.info(
            f"Found {log_groups.get('log_groups_found', 0)} log groups with prefix '{log_prefix}'"
        )

        if log_groups.get("log_groups_found", 0) > 0:
            group_names = [g["name"] for g in log_groups.get("log_groups", [])]
            logger.info(f"Log group names: {group_names[:5]}...")  # Show first 5

        if log_groups.get("log_groups_found", 0) == 0:
            return {
                "stack_name": stack_name,
                "log_prefix": log_prefix,
                "events_found": 0,
                "message": "No log groups found with the determined prefix",
            }

        # Search each log group
        groups_to_search = log_groups["log_groups"][:max_log_groups]
        all_results = []
        total_events = 0

        for log_group in groups_to_search:
            log_group_name = log_group["name"]

            search_result = _search_cloudwatch_logs(
                log_group_name=log_group_name,
                filter_pattern=filter_pattern,
                hours_back=hours_back,
                max_events=max_log_events,
            )

            if search_result.get("events_found", 0) > 0:
                logger.info(
                    f"Found {search_result['events_found']} events in {log_group_name}"
                )

                all_results.append(
                    {
                        "log_group": log_group_name,
                        "events_found": search_result["events_found"],
                        "events": search_result["events"],
                    }
                )
                total_events += search_result["events_found"]
            else:
                logger.debug(f"No events found in {log_group_name}")

        return {
            "stack_name": stack_name,
            "log_prefix_used": log_prefix,
            "prefix_type": prefix_type,
            "filter_pattern": filter_pattern,
            "total_log_groups_found": log_groups.get("log_groups_found", 0),
            "log_groups_searched": len(groups_to_search),
            "log_groups_with_events": len(all_results),
            "total_events_found": total_events,
            "max_log_events": max_log_events,
            "results": all_results,
        }

    except Exception as e:
        logger.error(f"Stack log search failed for '{stack_name}': {e}")
        return create_error_response(str(e), stack_name=stack_name, events_found=0)


# =============================================================================
# PUBLIC UTILITY FUNCTIONS
# =============================================================================


def extract_error_keywords(log_events: List[LogEvent]) -> Dict[str, int]:
    """
    Extract and count error keywords from log events.

    Args:
        log_events: List of LogEvent objects

    Returns:
        Dict mapping error keywords to their occurrence counts
    """
    error_keywords = [
        "error",
        "exception",
        "failed",
        "failure",
        "timeout",
        "fatal",
        "critical",
        "panic",
        "abort",
        "crash",
        "denied",
        "refused",
    ]

    keyword_counts = Counter()

    for event in log_events:
        message_lower = event.message.lower()
        for keyword in error_keywords:
            if keyword in message_lower:
                keyword_counts[keyword] += 1

    return dict(keyword_counts.most_common(10))


# =============================================================================
# PRIVATE HELPER FUNCTIONS
# =============================================================================


def _search_cloudwatch_logs(
    log_group_name: str,
    filter_pattern: str = "",
    hours_back: int = 24,
    max_events: int = 10,
    start_time: datetime = None,
    end_time: datetime = None,
    request_id: str = None,
) -> Dict[str, Any]:
    """
    Search CloudWatch logs within a specific log group for matching patterns.
    Enhanced with request ID-first search strategy for precise log correlation.

    Args:
        log_group_name: CloudWatch log group name to search
        filter_pattern: CloudWatch filter pattern for log events
        hours_back: Hours to look back from current time
        max_events: Maximum number of events to return
        start_time: Optional start time for search window
        end_time: Optional end time for search window
        request_id: Optional Lambda request ID for precise filtering

    Returns:
        Dict containing found events and search metadata
    """
    try:
        logger.debug(
            f"Searching CloudWatch logs in {log_group_name} with filter '{filter_pattern}'"
        )
        client = boto3.client("logs")

        # Use provided time window or default to hours_back from now
        if start_time and end_time:
            search_start = start_time
            search_end = end_time
        else:
            search_end = datetime.now()
            search_start = search_end - timedelta(hours=hours_back)

        # Use higher limit for error patterns to account for INFO log filtering
        search_limit = (
            int(max_events) * 5
            if filter_pattern
            in ["[ERROR]", "[WARN]", "ERROR:", "WARN:", "Exception", "Failed"]
            else int(max_events)
        )

        params = {
            "logGroupName": log_group_name,
            "startTime": int(search_start.timestamp() * 1000),
            "endTime": int(search_end.timestamp() * 1000),
            "limit": search_limit,
        }

        # Build filter pattern with request ID priority
        final_filter_pattern = _build_filter_pattern(filter_pattern, request_id)
        if final_filter_pattern:
            params["filterPattern"] = final_filter_pattern

        logger.debug(f"CloudWatch search params: {params}")
        response = client.filter_log_events(**params)
        logger.debug(
            f"CloudWatch API returned {len(response.get('events', []))} raw events"
        )

        events = []
        for event in response.get("events", []):
            message = event["message"]
            if _should_exclude_log_event(message, filter_pattern):
                continue
            events.append(
                {
                    "timestamp": datetime.fromtimestamp(
                        event["timestamp"] / 1000
                    ).isoformat(),
                    "message": message,
                    "log_stream": event.get("logStreamName", ""),
                }
            )
            # Stop when we have enough actual error events
            if len(events) >= max_events:
                break

        result = {
            "log_group": log_group_name,
            "events_found": len(events),
            "events": events,
            "filter_pattern": final_filter_pattern,
            "request_id_used": request_id,
            "search_strategy": "request_id" if request_id else "pattern",
        }

        if events:
            for i, event in enumerate(events[:3]):  # Log first 3 events
                logger.error(f"Found error: {event['message']}")
        else:
            logger.debug(
                f"No events found in {log_group_name} with filter '{final_filter_pattern}'"
            )

        return result

    except Exception as e:
        logger.error(f"CloudWatch search failed for log group '{log_group_name}': {e}")
        return create_error_response(str(e), events_found=0, events=[])


def _build_filter_pattern(base_pattern: str, request_id: str = None) -> str:
    """
    Build CloudWatch filter pattern combining request ID and error keywords.

    Args:
        base_pattern: Base filter pattern (e.g., "ERROR")
        request_id: Lambda request ID for precise filtering

    Returns:
        Optimized filter pattern string
    """
    if request_id and base_pattern:
        # Combine request ID with error pattern for precise error filtering
        sanitized_pattern = base_pattern.replace(":", "")
        combined_pattern = f"[{request_id}, {sanitized_pattern}]"
        logger.debug(f"Building combined filter pattern: {combined_pattern}")
        return combined_pattern
    elif request_id:
        logger.debug(f"Building filter pattern with request ID: {request_id}")
        return request_id
    elif base_pattern:
        sanitized_pattern = base_pattern.replace(":", "")
        logger.debug(f"Building filter pattern with base pattern: {sanitized_pattern}")
        return sanitized_pattern
    else:
        return ""


def _get_cloudwatch_log_groups(prefix: str = "") -> Dict[str, Any]:
    """
    Lists CloudWatch log groups matching specified prefix.
    Internal utility function that lists available log groups and their metadata.
    Filters by prefix to reduce API calls and focus on relevant groups.

    Args:
        prefix: Log group name prefix to filter by

    Returns:
        Dict containing found log groups and their metadata
    """
    try:
        if not prefix or len(prefix) < 5:
            return {
                "log_groups_found": 0,
                "log_groups": [],
                "warning": "Empty prefix provided",
            }

        client = boto3.client("logs")
        response = client.describe_log_groups(logGroupNamePrefix=prefix)

        groups = []
        for group in response.get("logGroups", []):
            groups.append(
                {
                    "name": group["logGroupName"],
                    "creation_time": datetime.fromtimestamp(
                        group["creationTime"] / 1000
                    ).isoformat(),
                    "retention_days": group.get("retentionInDays", "Never expire"),
                    "size_bytes": group.get("storedBytes", 0),
                }
            )

        return {"log_groups_found": len(groups), "log_groups": groups}

    except Exception as e:
        logger.error(f"Failed to get log groups with prefix '{prefix}': {e}")
        return create_error_response(str(e), log_groups_found=0, log_groups=[])


def _extract_prefix_from_state_machine_arn(arn: str) -> str:
    """
    Extracts log group prefix from Step Functions State Machine ARN.
    Parses the State Machine ARN to determine the appropriate CloudWatch log group prefix
    for finding related Lambda function logs.

    Args:
        arn: Step Functions State Machine ARN

    Returns:
        Extracted prefix string or empty string if parsing fails
    """
    if ":stateMachine:" in arn:
        state_machine_name = arn.split(":stateMachine:")[-1]
        if "-DocumentProcessingWorkflow" in state_machine_name:
            return state_machine_name.replace("-DocumentProcessingWorkflow", "")
        parts = state_machine_name.split("-")
        if len(parts) > 1:
            return "-".join(parts[:-1])
    return ""


def _get_log_group_prefix(stack_name: str) -> Dict[str, Any]:
    """
    Determines CloudWatch log group prefix from CloudFormation stack.
    Analyzes CloudFormation stack outputs to find the correct log group prefix pattern.
    Prioritizes pattern-based prefixes from State Machine ARNs over generic stack prefixes.

    Args:
        stack_name: CloudFormation stack name

    Returns:
        Dict containing prefix information and metadata
    """
    try:
        cf_client = boto3.client("cloudformation")
        stack_response = cf_client.describe_stacks(StackName=stack_name)
        stacks = stack_response.get("Stacks", [])

        if stacks:
            outputs = stacks[0].get("Outputs", [])

            for output in outputs:
                output_key = output.get("OutputKey", "")
                output_value = output.get("OutputValue", "")
                logger.debug(f"Checking output: {output_key} = {output_value}")

                if output_key == "StateMachineArn":
                    extracted_prefix = _extract_prefix_from_state_machine_arn(
                        output_value
                    )

                    if extracted_prefix:
                        pattern_prefix = f"/{extracted_prefix}/lambda"

                        return {
                            "stack_name": stack_name,
                            "prefix_type": "pattern",
                            "log_group_prefix": pattern_prefix,
                            "nested_stack_name": extracted_prefix,
                        }

        main_prefix = f"/aws/lambda/{stack_name}"

        return {
            "stack_name": stack_name,
            "prefix_type": "main",
            "log_group_prefix": main_prefix,
        }

    except Exception as e:
        logger.error(
            f"Failed to determine log group prefix for stack '{stack_name}': {e}"
        )
        return create_error_response(str(e), stack_name=stack_name)


def _should_exclude_log_event(message: str, filter_pattern: str = "") -> bool:
    """
    Consolidated log filtering - combines all exclusion logic.
    Filters out noise from LLM context while preserving relevant error information.

    Args:
        message: Log message to evaluate
        filter_pattern: CloudWatch filter pattern being used

    Returns:
        True if message should be excluded from LLM context
    """
    # Skip INFO logs when searching for error patterns
    if filter_pattern in [
        "[ERROR]",
        "[WARN]",
        "ERROR:",
        "WARN:",
        "Exception",
        "Failed",
    ]:
        if message.strip().startswith("[INFO]"):
            return True
        # Skip Lambda system logs
        if any(
            message.strip().startswith(prefix)
            for prefix in ["INIT_START", "START", "END", "REPORT"]
        ):
            return True

    # Exclude content patterns that add no value for error analysis
    EXCLUDE_CONTENT = [
        "Config:",  # Configuration dumps
        '"sample_json"',  # Config JSON structures
        "Processing event:",  # Generic event processing logs
        "Initialized",  # Initialization messages
        "Starting",  # Startup messages
        "Debug:",  # Debug information
        "Trace:",  # Trace logs
    ]

    # Skip if contains excluded content
    if any(exclude in message for exclude in EXCLUDE_CONTENT):
        return True

    # Skip very long messages (likely config dumps or verbose logs)
    if len(message) > 1000:
        return True

    return False
