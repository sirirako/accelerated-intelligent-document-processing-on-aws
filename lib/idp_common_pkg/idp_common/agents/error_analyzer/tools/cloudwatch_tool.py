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

    Args:
        document_id: Document filename/ObjectKey (e.g., "report.pdf", "lending_package.pdf")
        stack_name: CloudFormation stack name for log group discovery
        filter_pattern: CloudWatch filter pattern - "ERROR", "Exception", "Failed" (default: "ERROR")
        max_log_events: Maximum log events per group to return (default: 10, max: 50)
        max_log_groups: Maximum log groups to search (default: 20, max: 50)

    Returns:
        Dict with analysis results and error events found
    """
    try:
        max_log_events = safe_int_conversion(max_log_events, 10)
        max_log_groups = safe_int_conversion(max_log_groups, 20)

        # Get document context from DynamoDB
        dynamodb_response = dynamodb_record(document_id)
        if not dynamodb_response.get("document_found"):
            return {
                "analysis_type": "document_not_found",
                "document_id": document_id,
                "error": dynamodb_response.get("reason", "Document not found"),
                "events_found": 0,
            }

        document_record = dynamodb_response.get("document", {})

        # Extract stack name from Step Functions execution ARN
        step_function_execution_arn = document_record.get(
            "WorkflowExecutionArn"
        ) or document_record.get("ExecutionArn")
        actual_stack_name = stack_name
        if step_function_execution_arn:
            arn_parts = step_function_execution_arn.split(":")
            if len(arn_parts) >= 6:
                state_machine_name = arn_parts[6].split("-DocumentProcessingWorkflow")[
                    0
                ]
                if state_machine_name:
                    actual_stack_name = state_machine_name

        # Get X-Ray trace ID and extract Lambda request IDs
        xray_trace_id = document_record.get("TraceId")
        lambda_function_to_request_id_map = {}
        if xray_trace_id:
            lambda_function_to_request_id_map = extract_lambda_request_ids(
                xray_trace_id
            )

        # Get log groups for the stack
        log_groups = _get_log_groups_from_stack_prefix(actual_stack_name)
        logger.info(
            f"Found {log_groups.get('log_groups_found', 0)} log groups for stack {actual_stack_name}"
        )

        if log_groups.get("log_groups_found", 0) == 0:
            return {
                "document_id": document_id,
                "events_found": 0,
                "message": f"No log groups found for stack {actual_stack_name}",
            }

        # Extract processing time window
        document_start_time = None
        document_end_time = None
        if document_record.get("InitialEventTime"):
            document_start_time = datetime.fromisoformat(
                document_record["InitialEventTime"].replace("Z", "+00:00")
            )
        if document_record.get("CompletionTime"):
            document_end_time = datetime.fromisoformat(
                document_record["CompletionTime"].replace("Z", "+00:00")
            )

        # Add time buffer for isolation
        if document_start_time and document_end_time:
            processing_duration = document_end_time - document_start_time
            time_buffer = min(timedelta(minutes=2), processing_duration * 0.1)
            document_start_time = document_start_time - time_buffer
            document_end_time = document_end_time + time_buffer

        # Determine search strategy based on document status
        document_status = document_record.get("ObjectStatus") or document_record.get(
            "WorkflowStatus"
        )
        request_ids_to_search = list(lambda_function_to_request_id_map.values())

        # Prioritize failed function if document failed
        if document_status == "FAILED" and lambda_function_to_request_id_map:
            primary_failed_function = list(lambda_function_to_request_id_map.keys())[-1]
            primary_failed_request_id = lambda_function_to_request_id_map[
                primary_failed_function
            ]
            request_ids_to_search = [primary_failed_request_id] + [
                rid for rid in request_ids_to_search if rid != primary_failed_request_id
            ]

        # Search logs with request IDs
        all_results = []
        total_events = 0
        groups_to_search = log_groups["log_groups"][:max_log_groups]
        search_method_used = "none"

        for request_id in request_ids_to_search:
            function_name = next(
                (
                    func
                    for func, rid in lambda_function_to_request_id_map.items()
                    if rid == request_id
                ),
                "Unknown",
            )

            # Extract function type from Lambda function name (e.g., "ClassificationFunction")
            function_type = _extract_function_type(function_name)

            # Find matching log group for this function type
            matching_log_groups = (
                [
                    lg
                    for lg in groups_to_search
                    if function_type and function_type in lg["name"]
                ]
                if function_type
                else []
            )

            # Only search the specific matching log group for this function's request ID
            log_groups_to_search = matching_log_groups

            if log_groups_to_search:
                for log_group in log_groups_to_search:
                    logger.info(
                        f"Searching log group {log_group['name']} for Lambda function {function_name} ({function_type}) with request ID {request_id}"
                    )
                    # Use ERROR pattern and filter by request ID in post-processing
                    search_result = _search_cloudwatch_logs(
                        log_group_name=log_group["name"],
                        filter_pattern="ERROR",  # Search for errors, filter by request ID later
                        max_events=max_log_events * 3,  # Get more events to filter
                        start_time=document_start_time,
                        end_time=document_end_time,
                        request_id=request_id,
                    )

                    if search_result.get("events_found", 0) > 0:
                        search_method_used = "lambda_request_id"
                        logger.info(
                            f"Found {search_result['events_found']} error events in {log_group['name']} for Lambda function {function_name} using request ID {request_id}"
                        )
                        all_results.append(
                            {
                                "log_group": log_group["name"],
                                "lambda_function_name": function_name,
                                "request_id": request_id,
                                "search_method": "lambda_request_id",
                                "events_found": search_result["events_found"],
                                "events": search_result["events"],
                            }
                        )
                        total_events += search_result["events_found"]
            else:
                logger.info(
                    f"No matching log group found for Lambda function {function_name} ({function_type})"
                )

            # Stop if we found errors from the first (likely failed) function
            if total_events > 0:
                break

        # Fallback to document-specific search if no request ID results
        if total_events == 0:
            doc_identifier = document_id.replace(".pdf", "").replace(".", "-")
            for log_group in groups_to_search[:3]:
                search_result = _search_cloudwatch_logs(
                    log_group_name=log_group["name"],
                    filter_pattern=doc_identifier,
                    max_events=max_log_events,
                    start_time=document_start_time,
                    end_time=document_end_time,
                )

                if search_result.get("events_found", 0) > 0:
                    # Filter for actual errors
                    error_events = [
                        e
                        for e in search_result.get("events", [])
                        if any(
                            term in e.get("message", "").upper()
                            for term in ["ERROR", "EXCEPTION", "FAILED", "TIMEOUT"]
                        )
                    ]

                    if error_events:
                        search_method_used = "document_specific_fallback"
                        logger.info(
                            f"Found {len(error_events)} document-specific error events in {log_group['name']} using fallback search"
                        )
                        all_results.append(
                            {
                                "log_group": log_group["name"],
                                "search_method": "document_specific_fallback",
                                "events_found": len(error_events),
                                "events": error_events,
                            }
                        )
                        total_events += len(error_events)
                        break

        response = {
            "analysis_type": "document_specific",
            "document_id": document_id,
            "document_status": document_status,
            "xray_trace_id": xray_trace_id,
            "stack_name_used": actual_stack_name,
            "search_method_used": search_method_used,
            "lambda_functions_found": list(lambda_function_to_request_id_map.keys()),
            "total_events_found": total_events,
            "results": all_results,
        }
        logger.info(
            f"CloudWatch document logs response - search method: {search_method_used}, events found: {total_events}"
        )
        return response

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

    Args:
        filter_pattern: CloudWatch filter pattern - "ERROR", "Exception", "Failed", "Timeout" (default: "ERROR")
        hours_back: Hours to look back from now (default: 24, max: 168 for 1 week)
        max_log_events: Maximum events per log group (default: 10, max: 50)
        max_log_groups: Maximum log groups to search (default: 20, max: 50)

    Returns:
        Dict with analysis results and error events found
    """
    stack_name = os.environ.get("AWS_STACK_NAME", "")
    if not stack_name:
        return {
            "error": "AWS_STACK_NAME environment variable not set",
            "events_found": 0,
        }

    try:
        max_log_events = safe_int_conversion(max_log_events, 10)
        max_log_groups = safe_int_conversion(max_log_groups, 20)
        hours_back = safe_int_conversion(hours_back, 24)

        # Get log group prefix
        prefix_info = _get_log_group_prefix(stack_name)
        if "error" in prefix_info:
            return {
                "error": f"Failed to get log prefix: {prefix_info['error']}",
                "events_found": 0,
            }

        log_prefix = prefix_info.get("log_group_prefix")

        # Get log groups with the prefix
        log_groups = _get_cloudwatch_log_groups(prefix=log_prefix)
        if log_groups.get("log_groups_found", 0) == 0:
            return {
                "stack_name": stack_name,
                "events_found": 0,
                "message": "No log groups found",
            }

        # Search each log group
        groups_to_search = log_groups["log_groups"][:max_log_groups]
        all_results = []
        total_events = 0

        for log_group in groups_to_search:
            search_result = _search_cloudwatch_logs(
                log_group_name=log_group["name"],
                filter_pattern=filter_pattern,
                hours_back=hours_back,
                max_events=max_log_events,
            )

            if search_result.get("events_found", 0) > 0:
                logger.info(
                    f"Found {search_result['events_found']} error events in {log_group['name']}"
                )
                all_results.append(
                    {
                        "log_group": log_group["name"],
                        "events_found": search_result["events_found"],
                        "events": search_result["events"],
                    }
                )
                total_events += search_result["events_found"]

        return {
            "stack_name": stack_name,
            "filter_pattern": filter_pattern,
            "total_events_found": total_events,
            "log_groups_searched": len(groups_to_search),
            "results": all_results,
        }

    except Exception as e:
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
    """
    try:
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

        logger.info(
            f"CloudWatch search params for {log_group_name}: filter='{final_filter_pattern}', request_id={request_id}"
        )

        response = client.filter_log_events(**params)
        logger.info(
            f"CloudWatch API returned {len(response.get('events', []))} raw events for {log_group_name}"
        )

        events = []
        for event in response.get("events", []):
            message = event["message"]
            if _should_exclude_log_event(message, filter_pattern):
                continue

            # When using request ID search, only include events with matching request ID
            if request_id and request_id not in message:
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
            if len(events) >= max_events:
                break

        return {
            "log_group": log_group_name,
            "events_found": len(events),
            "events": events,
            "filter_pattern": final_filter_pattern,
        }

    except Exception as e:
        return create_error_response(str(e), events_found=0, events=[])


def _build_filter_pattern(base_pattern: str, request_id: str = None) -> str:
    """
    Build CloudWatch filter pattern. Use ERROR pattern and filter by request ID in post-processing.
    """
    if request_id:
        # Use ERROR pattern, will filter by request ID in post-processing
        return base_pattern if base_pattern else "ERROR"
    elif base_pattern:
        return base_pattern
    else:
        return ""


def _get_cloudwatch_log_groups(prefix: str = "") -> Dict[str, Any]:
    """
    Lists CloudWatch log groups matching specified prefix.
    """
    try:
        if not prefix or len(prefix) < 5:
            return {"log_groups_found": 0, "log_groups": []}

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
        return create_error_response(str(e), log_groups_found=0, log_groups=[])


def _extract_prefix_from_state_machine_arn(arn: str) -> str:
    """
    Extracts log group prefix from Step Functions State Machine ARN.
    """
    if ":stateMachine:" in arn:
        state_machine_name = arn.split(":stateMachine:")[-1]
        if "-DocumentProcessingWorkflow" in state_machine_name:
            return state_machine_name.replace("-DocumentProcessingWorkflow", "")
        parts = state_machine_name.split("-")
        if len(parts) > 1:
            return "-".join(parts[:-1])
    return ""


def _get_log_groups_from_stack_prefix(stack_name: str) -> Dict[str, Any]:
    """
    Get all CloudWatch log groups that start with the stack prefix.
    """
    if not stack_name:
        return {"log_groups_found": 0, "log_groups": []}

    log_group_prefix = f"/{stack_name}/lambda"

    try:
        client = boto3.client("logs")
        response = client.describe_log_groups(logGroupNamePrefix=log_group_prefix)

        log_groups = []
        for group in response.get("logGroups", []):
            log_groups.append(
                {
                    "name": group["logGroupName"],
                    "creation_time": datetime.fromtimestamp(
                        group["creationTime"] / 1000
                    ).isoformat(),
                    "retention_days": group.get("retentionInDays", "Never expire"),
                    "size_bytes": group.get("storedBytes", 0),
                }
            )

        return {"log_groups_found": len(log_groups), "log_groups": log_groups}

    except Exception:
        return {"log_groups_found": 0, "log_groups": []}


def _get_log_group_prefix(stack_name: str) -> Dict[str, Any]:
    """
    Determines CloudWatch log group prefix from CloudFormation stack.
    """
    try:
        cf_client = boto3.client("cloudformation")
        stack_response = cf_client.describe_stacks(StackName=stack_name)
        stacks = stack_response.get("Stacks", [])

        if stacks:
            outputs = stacks[0].get("Outputs", [])
            for output in outputs:
                if output.get("OutputKey") == "StateMachineArn":
                    extracted_prefix = _extract_prefix_from_state_machine_arn(
                        output.get("OutputValue", "")
                    )
                    if extracted_prefix:
                        return {
                            "stack_name": stack_name,
                            "prefix_type": "pattern",
                            "log_group_prefix": f"/{extracted_prefix}/lambda",
                        }

        return {
            "stack_name": stack_name,
            "prefix_type": "main",
            "log_group_prefix": f"/aws/lambda/{stack_name}",
        }

    except Exception as e:
        return create_error_response(str(e), stack_name=stack_name)


def _extract_function_type(lambda_function_name: str) -> str:
    """
    Extract function type from Lambda function name using pattern matching.

    Examples:
    - DEV-P2-EA8-PATTERN2STACK-1H-ClassificationFunction-dSp68ELdR85C -> ClassificationFunction
    - DEV-P2-EA8-PATTERN2STACK-1HHT2VDXH7MW0-OCRFunction-EQ6aqmcsC4XO -> OCRFunction
    - DEV-P2-EA8-QueueProcessor-JweFNlBa4vkV -> QueueProcessor
    """
    if not lambda_function_name:
        return ""

    # Split by hyphens and look for parts ending with "Function" or "Processor"
    parts = lambda_function_name.split("-")

    for part in parts:
        # Look for parts ending with common Lambda function suffixes
        if part.endswith(("Function", "Processor")) and len(part) > 8:
            return part

    return ""


def _is_error_event(message: str) -> bool:
    """
    Check if a log message is an error event.
    """
    message_upper = message.upper()
    error_indicators = [
        "[ERROR]",
        "ERROR:",
        "EXCEPTION",
        "FAILED",
        "FAILURE",
        "TIMEOUT",
        "FATAL",
        "CRITICAL",
    ]
    return any(indicator in message_upper for indicator in error_indicators)


def _should_exclude_log_event(message: str, filter_pattern: str = "") -> bool:
    """
    Filter out noise from log events while preserving relevant error information.
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
        if message.strip().startswith(
            ("[INFO]", "INIT_START", "START", "END", "REPORT")
        ):
            return True

    # Exclude content patterns that add no value for error analysis
    exclude_patterns = [
        "Config:",
        '"sample_json"',
        "Processing event:",
        "Initialized",
        "Starting",
        "Debug:",
        "Trace:",
    ]
    if any(pattern in message for pattern in exclude_patterns) or len(message) > 1000:
        return True

    return False
