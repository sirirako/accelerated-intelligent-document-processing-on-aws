# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
CloudWatch tools for error analysis.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict

import boto3
from strands import tool

from ..config import create_error_response, safe_int_conversion
from .lambda_tool import lambda_lookup
from .xray_tool import extract_lambda_request_ids

logger = logging.getLogger(__name__)


def search_cloudwatch_logs(
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
            search_end = datetime.utcnow()
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


def get_cloudwatch_log_groups(prefix: str = "") -> Dict[str, Any]:
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


def get_log_group_prefix(stack_name: str) -> Dict[str, Any]:
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
        - search_strategy (dict): Strategy used for log searching
        - processing_time_window (dict): Time window used for search
    """
    try:
        # Use safe integer conversion with defaults
        max_log_events = safe_int_conversion(max_log_events, 10)
        max_log_groups = safe_int_conversion(max_log_groups, 20)
        # Get document execution context with enhanced request ID mapping
        context = lambda_lookup(document_id, stack_name)

        if not context.get("document_found"):
            return {
                "analysis_type": "document_not_found",
                "document_id": document_id,
                "error": context.get("error", "Document not found"),
                "events_found": 0,
            }

        # Get log group prefix
        prefix_info = get_log_group_prefix(stack_name)
        if "error" in prefix_info:
            return {
                "error": f"Failed to get log prefix: {prefix_info['error']}",
                "events_found": 0,
            }

        log_prefix = prefix_info.get("log_group_prefix")
        log_groups = get_cloudwatch_log_groups(prefix=log_prefix)
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

        # Use precise time window from document context with buffer for batch operations
        start_time = context.get("processing_start_time")
        end_time = context.get("processing_end_time")

        # Add small buffer for batch operations but keep window tight
        if start_time and end_time:
            time_diff = end_time - start_time
            buffer = min(
                timedelta(minutes=2), time_diff * 0.1
            )  # Max 2min buffer or 10% of processing time
            start_time = start_time - buffer
            end_time = end_time + buffer
            logger.info(
                f"Using time window with {buffer.total_seconds()}s buffer for batch operation isolation"
            )

        # X-Ray based request ID extraction
        trace_id = context.get("trace_id")
        function_request_map = {}

        if trace_id:
            logger.info(f"Extracting Lambda request IDs from X-Ray trace: {trace_id}")
            function_request_map = extract_lambda_request_ids(trace_id)
            logger.info(
                f"X-Ray extraction found {len(function_request_map)} Lambda functions: {function_request_map}"
            )
        else:
            logger.warning("No trace_id found in document context")

        request_ids = list(function_request_map.values())
        failed_functions = context.get("failed_functions", [])
        primary_failed_function = context.get("primary_failed_function")
        execution_arn = context.get("execution_arn")

        # Priority 1: Request IDs from failed functions (highest priority)
        failed_function_request_ids = []
        if primary_failed_function and primary_failed_function in function_request_map:
            req_id = function_request_map[primary_failed_function]
            failed_function_request_ids.append(req_id)
            logger.info(
                f"Primary failed function '{primary_failed_function}' has request ID: {req_id}"
            )

        # Add other failed function request IDs
        for func in failed_functions:
            if func in function_request_map:
                req_id = function_request_map[func]
                if req_id not in failed_function_request_ids:
                    failed_function_request_ids.append(req_id)
                    logger.info(f"Failed function '{func}' has request ID: {req_id}")

        # Priority 2: All other request IDs (medium priority)
        other_request_ids = [
            rid for rid in request_ids if rid not in failed_function_request_ids
        ]

        # Priority 3: Step Functions execution-based search (fallback only)
        execution_patterns = []
        if execution_arn and not failed_function_request_ids:
            execution_name = execution_arn.split(":")[-1]
            execution_patterns.append(execution_name)
            logger.info(f"Using execution based pattern: {execution_name}")

        # Build search strategy
        search_strategy = {
            "failed_function_request_ids": failed_function_request_ids,
            "other_request_ids": other_request_ids,
            "execution_patterns": execution_patterns,
        }

        # Search logs with prioritized strategy
        all_results = []
        total_events = 0
        groups_to_search = log_groups["log_groups"][:max_log_groups]

        # Search with failed function request IDs (highest priority)
        for request_id in search_strategy["failed_function_request_ids"]:
            # Find function name for this request ID
            function_name = next(
                (
                    func
                    for func, rid in function_request_map.items()
                    if rid == request_id
                ),
                "Unknown",
            )
            logger.info(
                f"Filtering logs with Lambda function: {function_name}, request_id: {request_id}"
            )

            for group in groups_to_search:
                log_group_name = group["name"]
                search_result = search_cloudwatch_logs(
                    log_group_name=log_group_name,
                    filter_pattern="ERROR",
                    max_events=max_log_events,
                    start_time=start_time,
                    end_time=end_time,
                    request_id=request_id,
                )
                logger.debug(
                    f"Search result for request ID '{request_id}': {search_result.get('events_found', 0)} events found"
                )

                if search_result.get("events_found", 0) > 0:
                    logger.info(
                        f"Found {search_result['events_found']} events in {log_group_name} with request ID {request_id}"
                    )

                    all_results.append(
                        {
                            "log_group": log_group_name,
                            "search_type": "failed_function_request_id",
                            "pattern_used": request_id,
                            "events_found": search_result["events_found"],
                            "events": search_result["events"],
                        }
                    )
                    total_events += search_result["events_found"]

            # If we found errors from failed functions, we have what we need
            if total_events > 0:
                logger.info(
                    f"Found {total_events} events from failed function request IDs, stopping search"
                )
                break

        # Search with other request IDs if no errors found yet
        if total_events == 0 and search_strategy["other_request_ids"]:
            for request_id in search_strategy["other_request_ids"][
                :3
            ]:  # Limit to first 3
                # Find function name for this request ID
                function_name = next(
                    (
                        func
                        for func, rid in function_request_map.items()
                        if rid == request_id
                    ),
                    "Unknown",
                )
                logger.info(
                    f"Filtering logs with Lambda function: {function_name}, request_id: {request_id}"
                )

                for group in groups_to_search:
                    log_group_name = group["name"]

                    search_result = search_cloudwatch_logs(
                        log_group_name=log_group_name,
                        filter_pattern="ERROR",
                        max_events=max_log_events,
                        start_time=start_time,
                        end_time=end_time,
                        request_id=request_id,
                    )

                    if search_result.get("events_found", 0) > 0:
                        logger.info(
                            f"Found {search_result['events_found']} events in {log_group_name} with request ID {request_id}"
                        )

                        all_results.append(
                            {
                                "log_group": log_group_name,
                                "search_type": "other_request_id",
                                "pattern_used": request_id,
                                "events_found": search_result["events_found"],
                                "events": search_result["events"],
                            }
                        )
                        total_events += search_result["events_found"]

                if total_events > 0:
                    break

        # Fallback to execution-based search if still no results
        if total_events == 0 and search_strategy["execution_patterns"]:
            # Document-specific search using document ID for batch operation safety
            if total_events == 0:
                # Extract document identifier for precise filtering
                doc_identifier = document_id.replace(".pdf", "").replace(".", "-")

                for group in groups_to_search[:3]:  # Limit to first 3 groups
                    log_group_name = group["name"]
                    # Try document-specific search first
                    search_result = search_cloudwatch_logs(
                        log_group_name=log_group_name,
                        filter_pattern=doc_identifier,
                        max_events=max_log_events,
                        start_time=start_time,
                        end_time=end_time,
                    )

                    if search_result.get("events_found", 0) > 0:
                        logger.info(
                            f"Found {search_result['events_found']} document-specific events in {log_group_name}"
                        )

                        # Filter for actual errors in document-specific logs
                        error_events = []
                        for event in search_result.get("events", []):
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
                                error_events.append(event)

                        if error_events:
                            logger.info(
                                f"Found {len(error_events)} actual errors in document-specific search"
                            )
                            for i, event in enumerate(error_events[:2]):
                                logger.info(
                                    f"Document Error {i + 1}: {event.get('message', '')[:300]}..."
                                )

                            all_results.append(
                                {
                                    "log_group": log_group_name,
                                    "search_type": "document_specific_error_search",
                                    "pattern_used": doc_identifier,
                                    "events_found": len(error_events),
                                    "events": error_events,
                                }
                            )
                            total_events += len(error_events)
                            break

                # Fallback to broad ERROR search only if document-specific search fails
                if total_events == 0:
                    for group in groups_to_search[:2]:  # Further limit for broad search
                        log_group_name = group["name"]

                        search_result = search_cloudwatch_logs(
                            log_group_name=log_group_name,
                            filter_pattern="ERROR",
                            max_events=max_log_events,
                            start_time=start_time,
                            end_time=end_time,
                        )

                        if search_result.get("events_found", 0) > 0:
                            logger.info(
                                f"Found {search_result['events_found']} events in {log_group_name} with broad ERROR search"
                            )

                            all_results.append(
                                {
                                    "log_group": log_group_name,
                                    "search_type": "broad_error_search_fallback",
                                    "pattern_used": "ERROR",
                                    "events_found": search_result["events_found"],
                                    "events": search_result["events"],
                                    "warning": "May include errors from other concurrent documents",
                                }
                            )
                            total_events += search_result["events_found"]
                            break

            for pattern in search_strategy["execution_patterns"]:
                for group in groups_to_search:
                    log_group_name = group["name"]
                    search_result = search_cloudwatch_logs(
                        log_group_name=log_group_name,
                        filter_pattern=pattern,
                        max_events=max_log_events,
                        start_time=start_time,
                        end_time=end_time,
                    )
                    logger.debug(
                        f"Search result for execution pattern '{pattern}': {search_result.get('events_found', 0)} events found"
                    )

                    if search_result.get("events_found", 0) > 0:
                        logger.info(
                            f"Found {search_result['events_found']} events in {log_group_name} with execution pattern {pattern}"
                        )

                        all_results.append(
                            {
                                "log_group": log_group_name,
                                "search_type": "execution_fallback",
                                "pattern_used": pattern,
                                "events_found": search_result["events_found"],
                                "events": search_result["events"],
                            }
                        )
                        total_events += search_result["events_found"]

                if total_events > 0:
                    break

        return {
            "analysis_type": "document_specific",
            "document_id": document_id,
            "document_status": context.get("document_status"),
            "execution_arn": execution_arn,
            "search_strategy": search_strategy,
            "extraction_method": "xray_trace",
            "failed_functions": failed_functions,
            "primary_failed_function": primary_failed_function,
            "processing_time_window": {
                "start": start_time.isoformat() if start_time else None,
                "end": end_time.isoformat() if end_time else None,
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
    start_time: datetime = None,
    end_time: datetime = None,
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
        start_time: Optional specific start time (overrides hours_back)
        end_time: Optional specific end time (overrides hours_back)

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
        prefix_info = get_log_group_prefix(stack_name)
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
        log_groups = get_cloudwatch_log_groups(prefix=log_prefix)
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

        for group in groups_to_search:
            log_group_name = group["name"]

            search_result = search_cloudwatch_logs(
                log_group_name=log_group_name,
                filter_pattern=filter_pattern,
                hours_back=hours_back,
                max_events=max_log_events,
                start_time=start_time,
                end_time=end_time,
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
