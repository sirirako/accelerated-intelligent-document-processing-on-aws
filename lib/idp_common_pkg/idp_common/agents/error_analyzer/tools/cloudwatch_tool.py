# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
CloudWatch tools for error analysis.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import boto3
from strands import tool

from ..config import create_error_response
from .dynamodb_tool import fetch_document_record
from .xray_tool import extract_lambda_request_ids

logger = logging.getLogger(__name__)


# =============================================================================
# PUBLIC TOOL FUNCTIONS
# =============================================================================


@tool
def search_cloudwatch_logs(
    document_id: str = "",
    filter_pattern: str = "ERROR",
    hours_back: int = 24,
    max_log_events: int = 10,
    max_log_groups: int = 20,
) -> Dict[str, Any]:
    """
    Search CloudWatch logs for errors and failures in the IDP system.

    Use this tool when:
    - User reports document processing failures or errors
    - Need to investigate why a specific document failed to process
    - Looking for system-wide errors or patterns across the stack
    - Troubleshooting Lambda function failures or timeouts
    - Analyzing error trends or recurring issues

    Args:
        document_id: Document filename (e.g., "report.pdf"). When provided, performs targeted
                    search for that specific document using processing timestamps and Lambda
                    request IDs. When omitted, searches across all recent system logs.
        filter_pattern: Error pattern to search for - "ERROR", "Exception", "Failed", "TIMEOUT" (default: "ERROR")
        hours_back: Hours to look back from now (default: 24, max: 168). Only used for system-wide
                   searches when document_id is not provided.
        max_log_events: Maximum error events to return per log group (default: 10, max: 50)
        max_log_groups: Maximum log groups to search (default: 20, max: 50)

    Returns:
        Dict containing error events, search metadata, and processing context
    """
    try:
        # Parameters already have proper defaults, no conversion needed

        if document_id:
            # Document-specific search mode
            return _search_document_logs(
                document_id, filter_pattern, max_log_events, max_log_groups
            )
        else:
            # System-wide search mode
            return _search_stack_logs(
                filter_pattern, hours_back, max_log_events, max_log_groups
            )

    except Exception as e:
        logger.error(f"CloudWatch log search failed: {e}")
        return create_error_response(str(e), document_id=document_id, events_found=0)


# =============================================================================
# CONSOLIDATED SEARCH HELPER FUNCTIONS
# =============================================================================


def _get_stack_name(document_record: Optional[Dict[str, Any]] = None) -> str:
    """
    Get stack name with priority: document ARN > environment variable.
    """
    # First priority: Extract from document execution ARN
    if document_record:
        try:
            extracted_name = _extract_stack_name(document_record)
            if extracted_name:
                return extracted_name
        except Exception as e:
            logger.warning(f"Failed to extract stack name from document ARN: {e}")

    # Second priority: Environment variable
    env_stack_name = os.environ.get("AWS_STACK_NAME", "")
    if env_stack_name:
        return env_stack_name

    raise ValueError("No stack name available from document context or environment")


def _get_stack_log_groups() -> List[Dict[str, str]]:
    """
    Get prioritized log groups from environment variable.
    """
    env_log_groups = os.environ.get("CLOUDWATCH_LOG_GROUPS", "")
    if env_log_groups:
        log_groups = [
            {"name": lg.strip()} for lg in env_log_groups.split(",") if lg.strip()
        ]
        logger.info(
            f"Log groups: [{len(log_groups)}]{[lg['name'] for lg in log_groups]}"
        )
        prioritized_groups = _prioritize_log_groups(log_groups)
        logger.info(
            f"Prioritized log groups: {[lg['name'] for lg in prioritized_groups]}"
        )
        return prioritized_groups

    logger.warning("CLOUDWATCH_LOG_GROUPS environment variable not set")
    return []


def _prioritize_log_groups(log_groups: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Prioritize log groups by business logic importance.
    """
    priority_patterns = [
        "Function",  # Pattern functions (BDA, OCR, Classification, Extraction)
        "workflow",  # Step Functions
        "QueueProcessor",  # Document ingestion
        "WorkflowTracker",  # Status tracking
        "QueueSender",  # Supporting functions
    ]

    prioritized = []
    remaining = log_groups.copy()

    for pattern in priority_patterns:
        matching = [lg for lg in remaining if pattern.lower() in lg["name"].lower()]
        prioritized.extend(matching)
        remaining = [lg for lg in remaining if lg not in matching]

    # Add any remaining log groups
    prioritized.extend(remaining)
    return prioritized


def _search_document_logs(
    document_id: str, filter_pattern: str, max_log_events: int, max_log_groups: int
) -> Dict[str, Any]:
    """
    Document-specific search with DynamoDB context and X-Ray tracing.
    """
    # Get document context and validate
    context = _get_document_context(document_id)
    if "error" in context:
        return context

    # Get stack name from document context
    actual_stack_name = _get_stack_name(context.get("document_record"))
    logger.info(f"Document search for '{document_id}' using stack: {actual_stack_name}")

    # Get log groups for the stack
    log_groups = _get_stack_log_groups()
    if len(log_groups) == 0:
        return {
            "document_id": document_id,
            "events_found": 0,
            "message": f"No log groups found for stack {actual_stack_name}",
        }

    # Log which groups will be searched
    groups_to_search = log_groups[:max_log_groups]
    logger.info(
        f"Searching {len(groups_to_search)} log groups (max: {max_log_groups}): {[lg['name'] for lg in groups_to_search]}"
    )

    # Calculate processing time window with buffer
    time_window = _get_processing_time_window(context["document_record"])

    # Get prioritized request IDs for search
    request_ids_info = _prioritize_request_ids(
        context["document_record"], context["lambda_function_to_request_id_map"]
    )

    # Primary search using Lambda request IDs
    search_results = _search_by_request_ids(
        request_ids_info,
        context["lambda_function_to_request_id_map"],
        log_groups[:max_log_groups],
        time_window,
        max_log_events,
    )

    # Fallback search if no results from request ID search
    if search_results["total_events"] == 0:
        search_results = _search_by_document_fallback(
            document_id,
            log_groups[:5],
            time_window,
            max_log_events,
        )

    # Build final response
    return _build_response(
        document_id,
        context["document_record"],
        context["xray_trace_id"],
        actual_stack_name,
        context["lambda_function_to_request_id_map"],
        search_results,
    )


def _search_stack_logs(
    filter_pattern: str, hours_back: int, max_log_events: int, max_log_groups: int
) -> Dict[str, Any]:
    """
    Stack-wide search across all stack log groups.
    """
    # Get stack name from environment
    stack_name = _get_stack_name()
    logger.info(f"System-wide search using stack: {stack_name}")

    # Get log groups for the stack
    log_groups = _get_stack_log_groups()
    if len(log_groups) == 0:
        return {
            "stack_name": stack_name,
            "events_found": 0,
            "message": "No log groups found",
        }

    # Search each log group
    groups_to_search = log_groups[:max_log_groups]
    logger.info(
        f"Searching {len(groups_to_search)} log groups (max: {max_log_groups}): {[lg['name'] for lg in groups_to_search]}"
    )
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
        else:
            logger.info(f"No events found in log group: {log_group['name']}")

    return {
        "analysis_type": "system_wide",
        "stack_name": stack_name,
        "filter_pattern": filter_pattern,
        "total_events_found": total_events,
        "log_groups_searched": len(groups_to_search),
        "results": all_results,
    }


# =============================================================================
# DOCUMENT LOG SEARCH HELPER FUNCTIONS
# =============================================================================


def _get_document_context(document_id: str) -> Dict[str, Any]:
    """
    Get document context from DynamoDB and extract X-Ray information.
    """
    dynamodb_response = fetch_document_record(document_id)
    if not dynamodb_response.get("document_found"):
        return {
            "analysis_type": "document_not_found",
            "document_id": document_id,
            "error": dynamodb_response.get("reason", "Document not found"),
            "events_found": 0,
        }

    document_record = dynamodb_response.get("document", {})
    xray_trace_id = document_record.get("TraceId")
    lambda_function_to_request_id_map = {}

    if xray_trace_id:
        try:
            lambda_function_to_request_id_map = extract_lambda_request_ids(
                xray_trace_id
            )
        except Exception as e:
            logger.warning(
                f"Failed to extract Lambda request IDs from X-Ray trace {xray_trace_id}: {e}"
            )

    return {
        "document_record": document_record,
        "xray_trace_id": xray_trace_id,
        "lambda_function_to_request_id_map": lambda_function_to_request_id_map,
    }


def _extract_stack_name(document_record: Dict[str, Any]) -> str:
    """
    Extract actual stack name from Step Functions execution ARN.
    """
    step_function_execution_arn = document_record.get(
        "WorkflowExecutionArn"
    ) or document_record.get("ExecutionArn")

    if step_function_execution_arn:
        arn_parts = step_function_execution_arn.split(":")
        if len(arn_parts) >= 6:
            state_machine_name = arn_parts[6].split("-DocumentProcessingWorkflow")[0]
            if state_machine_name:
                return state_machine_name

    return ""


def _get_processing_time_window(document_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract processing time window with buffer for isolation.
    """
    start_time = None
    end_time = None

    if document_record.get("InitialEventTime"):
        start_time = datetime.fromisoformat(
            document_record["InitialEventTime"].replace("Z", "+00:00")
        )
    if document_record.get("CompletionTime"):
        end_time = datetime.fromisoformat(
            document_record["CompletionTime"].replace("Z", "+00:00")
        )

    # Add time buffer for isolation
    if start_time and end_time:
        processing_duration = end_time - start_time
        time_buffer = min(timedelta(minutes=2), processing_duration * 0.1)
        start_time = start_time - time_buffer
        end_time = end_time + time_buffer

    return {"start_time": start_time, "end_time": end_time}


def _prioritize_request_ids(
    document_record: Dict[str, Any], lambda_function_to_request_id_map: Dict[str, str]
) -> Dict[str, Any]:
    """
    Prioritize request IDs based on document failure status.
    """
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

    return {
        "document_status": document_status,
        "request_ids_to_search": request_ids_to_search,
    }


def _search_by_request_ids(
    request_ids_info: Dict[str, Any],
    lambda_function_to_request_id_map: Dict[str, str],
    groups_to_search: List[Dict[str, Any]],
    time_window: Dict[str, Any],
    max_log_events: int,
) -> Dict[str, Any]:
    """
    Search logs using Lambda request IDs with function-specific targeting.
    """
    all_results = []
    total_events = 0
    search_method_used = "none"

    for request_id in request_ids_info["request_ids_to_search"]:
        function_name = next(
            (
                func
                for func, rid in lambda_function_to_request_id_map.items()
                if rid == request_id
            ),
            "Unknown",
        )

        function_type = _extract_function_type(function_name)
        matching_log_groups = (
            [
                lg
                for lg in groups_to_search
                if function_type and function_type in lg["name"]
            ]
            if function_type
            else []
        )

        if matching_log_groups:
            for log_group in matching_log_groups:
                search_result = _search_cloudwatch_logs(
                    log_group_name=log_group["name"],
                    filter_pattern="ERROR",
                    max_events=max_log_events * 3,
                    start_time=time_window.get("start_time"),
                    end_time=time_window.get("end_time"),
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

    return {
        "all_results": all_results,
        "total_events": total_events,
        "search_method_used": search_method_used,
    }


def _search_by_document_fallback(
    document_id: str,
    groups_to_search: List[Dict[str, Any]],
    time_window: Dict[str, Any],
    max_log_events: int,
) -> Dict[str, Any]:
    """
    Fallback search using document-specific identifier.
    """
    all_results = []
    total_events = 0
    search_method_used = "none"

    doc_identifier = document_id.replace(".pdf", "").replace(".", "-")

    for log_group in groups_to_search:
        search_result = _search_cloudwatch_logs(
            log_group_name=log_group["name"],
            filter_pattern=doc_identifier,
            max_events=max_log_events,
            start_time=time_window.get("start_time"),
            end_time=time_window.get("end_time"),
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

    return {
        "all_results": all_results,
        "total_events": total_events,
        "search_method_used": search_method_used,
    }


def _build_response(
    document_id: str,
    document_record: Dict[str, Any],
    xray_trace_id: str,
    actual_stack_name: str,
    lambda_function_to_request_id_map: Dict[str, str],
    search_results: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build final response with all search results and metadata.
    """
    document_status = document_record.get("ObjectStatus") or document_record.get(
        "WorkflowStatus"
    )

    # Get execution ARN for additional context
    execution_arn = document_record.get("WorkflowExecutionArn") or document_record.get(
        "ExecutionArn"
    )

    # Calculate log groups searched count
    log_groups_searched = len(
        set(result.get("log_group", "") for result in search_results["all_results"])
    )

    response = {
        "document_id": document_id,
        "document_status": document_status,
        "execution_arn": execution_arn,
        "xray_trace_id": xray_trace_id,
        "stack_name_used": actual_stack_name,
        "search_method_used": search_results["search_method_used"],
        "lambda_functions_found": list(lambda_function_to_request_id_map.keys()),
        "log_groups_searched": log_groups_searched,
        "total_events_found": search_results["total_events"],
        "results": search_results["all_results"],
    }

    # Log complete response for troubleshooting
    logger.info(f"CloudWatch document logs response: {response}")
    return response


# =============================================================================
# PRIVATE HELPER FUNCTIONS
# =============================================================================


def _search_cloudwatch_logs(
    log_group_name: str,
    filter_pattern: str = "",
    hours_back: int = 24,
    max_events: int = 10,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    request_id: str = "",
) -> Dict[str, Any]:
    """
    Search CloudWatch logs within a specific log group for matching patterns.
    """
    try:
        client = boto3.client("logs")

        # Use provided time window or default to hours_back from now
        if start_time is not None and end_time is not None:
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

        try:
            response = client.filter_log_events(**params)
            logger.debug(
                f"CloudWatch API returned {len(response.get('events', []))} raw events for {log_group_name}"
            )
        except client.exceptions.ResourceNotFoundException:
            logger.warning(f"Log group {log_group_name} not found")
            return {
                "log_group": log_group_name,
                "events_found": 0,
                "events": [],
                "filter_pattern": final_filter_pattern,
            }
        except Exception as e:
            logger.error(f"CloudWatch API error for {log_group_name}: {e}")
            return create_error_response(str(e), events_found=0, events=[])

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


def _build_filter_pattern(base_pattern: str, request_id: str = "") -> str:
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
    return any(
        indicator in message.upper()
        for indicator in [
            "[ERROR]",
            "ERROR:",
            "EXCEPTION",
            "FAILED",
            "TIMEOUT",
            "FATAL",
            "CRITICAL",
        ]
    )


def _should_exclude_log_event(message: str, filter_pattern: str = "") -> bool:
    """
    Filter out noise from log events while preserving relevant error information.
    """
    message_stripped = message.strip()

    # Skip INFO/debug logs when searching for errors
    if filter_pattern and message_stripped.startswith(
        (
            "[INFO]",
            "INIT_START",
            "START",
            "END",
            "REPORT",
            "Config:",
            "Debug:",
            "Trace:",
        )
    ):
        return True

    # Exclude noise patterns or oversized messages
    return len(message) > 1000 or any(
        pattern in message
        for pattern in ['"sample_json"', "Processing event:", "Initialized", "Starting"]
    )
