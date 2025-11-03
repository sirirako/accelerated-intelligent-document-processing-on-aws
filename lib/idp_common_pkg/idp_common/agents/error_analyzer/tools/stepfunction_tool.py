# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Step Function tools for document-specific workflow execution analysis.
"""

import logging
from typing import Any, Dict, List, Optional

import boto3
from strands import tool

from idp_common.config import get_config

logger = logging.getLogger(__name__)


@tool
def analyze_workflow_execution(execution_arn: str) -> Dict[str, Any]:
    """
    Analyze Step Function workflow execution to identify failures and state transitions.

    Performs comprehensive analysis of document processing workflow executions by
    retrieving execution history, analyzing state transitions, identifying failure
    points, and providing actionable recommendations. Essential for troubleshooting
    document processing failures and understanding workflow behavior.

    Use this tool when:
    - Document processing failed and you have a Step Function execution ARN
    - Need to understand where in the workflow a failure occurred
    - Investigating workflow performance or timeout issues
    - Analyzing state transitions and execution timeline
    - User reports document processing stuck or failed

    Tool chaining: Get execution ARN from fetch_document_record, then use this tool
    for detailed workflow analysis. Follow up with search_cloudwatch_logs for
    specific Lambda function errors identified in the failure analysis.

    Example usage:
    - "Analyze the workflow execution for this document"
    - "What went wrong in the Step Function execution?"
    - "Show me the workflow timeline and failure point"
    - "Why did the document processing workflow fail?"
    - "Trace the execution flow and identify issues"

    Args:
        execution_arn: Step Function execution ARN (get from document record's WorkflowExecutionArn or ExecutionArn field)

    Returns:
        Dict with keys:
        - execution_status (str): Overall execution status (SUCCEEDED, FAILED, TIMED_OUT, etc.)
        - duration_seconds (float): Total execution duration if completed
        - timeline_analysis (dict): Detailed timeline with state transitions and failure point
        - analysis_summary (str): Human-readable summary of execution and failure
        - recommendations (list): Actionable next steps for investigation
    """
    try:
        if not execution_arn:
            return _build_response(
                execution_status="ERROR",
                analysis_summary="No execution ARN provided",
                recommendations=[
                    "Use search_cloudwatch_logs for detailed error information"
                ],
            )

        # Get execution data from Step Functions
        execution_data = _get_execution_data(execution_arn)

        # Analyze timeline and failures
        timeline_analysis = _analyze_execution_timeline(execution_data["events"])

        # Extract execution metadata
        execution_metadata = _extract_execution_metadata(
            execution_data["execution_response"]
        )

        # Build analysis summary
        analysis_summary = _build_analysis_summary(
            execution_metadata["status"], timeline_analysis
        )

        # Generate recommendations
        recommendations = _generate_recommendations(timeline_analysis)

        return _build_response(
            execution_status=execution_metadata["status"],
            duration_seconds=execution_metadata["duration_seconds"],
            timeline_analysis=timeline_analysis,
            analysis_summary=analysis_summary,
            recommendations=recommendations,
        )

    except Exception as e:
        logger.error(f"Error analyzing Step Function execution {execution_arn}: {e}")
        return _build_response(
            execution_status="ERROR",
            analysis_summary=f"Failed to analyze workflow execution: {str(e)}",
            recommendations=[
                "Use search_cloudwatch_logs for detailed error information"
            ],
        )


def _get_execution_data(execution_arn: str) -> Dict[str, Any]:
    """
    Retrieve execution details and history from Step Functions.
    """
    stepfunctions_client = boto3.client("stepfunctions")

    execution_response = stepfunctions_client.describe_execution(
        executionArn=execution_arn
    )

    history_response = stepfunctions_client.get_execution_history(
        executionArn=execution_arn,
        maxResults=100,
        reverseOrder=True,  # Most recent events first
    )

    return {
        "execution_response": execution_response,
        "events": history_response.get("events", []),
    }


def _extract_execution_metadata(execution_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract execution metadata including status and duration.
    """
    execution_status = execution_response.get("status", "UNKNOWN")
    start_date = execution_response.get("startDate")
    stop_date = execution_response.get("stopDate")

    duration_seconds = None
    if start_date and stop_date:
        duration_seconds = (stop_date - start_date).total_seconds()

    return {"status": execution_status, "duration_seconds": duration_seconds}


def _build_analysis_summary(
    execution_status: str, timeline_analysis: Dict[str, Any]
) -> str:
    """
    Build human-readable analysis summary.
    """
    analysis_summary = f"Step Function execution {execution_status}"

    if timeline_analysis.get("failure_point"):
        failure_point = timeline_analysis["failure_point"]
        analysis_summary += f" at state '{failure_point.get('state', 'Unknown')}'"
        if failure_point.get("details", {}).get("error"):
            analysis_summary += f": {failure_point['details']['error']}"

    return analysis_summary


def _generate_recommendations(timeline_analysis: Dict[str, Any]) -> List[str]:
    """
    Generate actionable recommendations based on analysis.
    """
    return [
        "Check the failure point state for specific error details",
        "Review Lambda function logs if failure occurred in Lambda task",
        "Verify input data format if failure occurred early in workflow",
        "Consider timeout adjustments if execution timed out",
    ]


def _build_response(
    execution_status: str,
    duration_seconds: Optional[float] = None,
    timeline_analysis: Optional[Dict[str, Any]] = None,
    analysis_summary: str = "",
    recommendations: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Build unified workflow analysis response with logging.
    """
    response = {
        "execution_status": execution_status,
        "duration_seconds": duration_seconds,
        "timeline_analysis": timeline_analysis or {},
        "analysis_summary": analysis_summary,
        "recommendations": recommendations or [],
    }

    logger.info(f"Workflow analysis response: {response}")
    return response


def _extract_failure_details(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Failure parser: Extracts detailed error information from Step Function events.

    Extract detailed failure information from Step Function execution events.

    Parses different types of failure events to extract error messages, causes,
    and resource information for comprehensive failure analysis.

    Args:
        event: Step Function execution event dictionary

    Returns:
        Dict containing failure details or None if event is not a failure
    """
    event_type = event.get("type", "")

    failure_events = [
        "ExecutionFailed",
        "TaskFailed",
        "LambdaFunctionFailed",
        "TaskTimedOut",
        "ExecutionTimedOut",
    ]

    if event_type not in failure_events:
        return None

    details = {}

    # Extract error details based on event type
    if event_type == "ExecutionFailed":
        failure_detail = event.get("executionFailedEventDetails", {})
        details = {
            "error": failure_detail.get("error", "Unknown execution error"),
            "cause": failure_detail.get("cause", "No cause provided"),
        }
    elif event_type == "TaskFailed":
        failure_detail = event.get("taskFailedEventDetails", {})
        details = {
            "error": failure_detail.get("error", "Unknown task error"),
            "cause": failure_detail.get("cause", "No cause provided"),
            "resource": failure_detail.get("resource", "Unknown resource"),
        }
    elif event_type == "LambdaFunctionFailed":
        failure_detail = event.get("lambdaFunctionFailedEventDetails", {})
        details = {
            "error": failure_detail.get("error", "Lambda function failed"),
            "cause": failure_detail.get("cause", "No cause provided"),
        }
    elif "TimedOut" in event_type:
        timeout_detail = event.get("executionTimedOutEventDetails") or event.get(
            "taskTimedOutEventDetails", {}
        )
        details = {
            "error": f"{event_type.replace('EventDetails', '')}",
            "cause": timeout_detail.get("cause", "Execution exceeded timeout limit"),
        }

    return details


def _analyze_execution_timeline(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze Step Function execution timeline to identify failure patterns and state transitions.
    Processes execution events chronologically to build a timeline of state transitions
    and identify the exact point of failure with context.

    Args:
        events: List of Step Function execution events

    Returns:
        Dict containing timeline analysis, failure point, and state information
    """
    if not events:
        return {"error": "No execution events available"}

    # Cache config values once
    config = get_config(as_model=True)

    max_timeline_events = (
        config.agents.error_analyzer.parameters.max_stepfunction_timeline_events
    )

    timeline = []
    failure_point = None
    last_successful_state = None

    for event in events:
        timestamp = event.get("timestamp")
        event_type = event.get("type", "")

        # Track state transitions
        if event_type == "StateEntered":
            state_name = event.get("stateEnteredEventDetails", {}).get(
                "name", "Unknown"
            )
            timeline.append(
                {
                    "timestamp": timestamp,
                    "event": f"Entered state: {state_name}",
                    "state": state_name,
                }
            )
            last_successful_state = state_name

        elif event_type == "StateExited":
            state_name = event.get("stateExitedEventDetails", {}).get("name", "Unknown")
            timeline.append(
                {
                    "timestamp": timestamp,
                    "event": f"Exited state: {state_name}",
                    "state": state_name,
                }
            )

        # Identify failure point
        failure_details = _extract_failure_details(event)
        if failure_details and not failure_point:
            failure_point = {
                "timestamp": timestamp,
                "event_type": event_type,
                "state": last_successful_state,
                "details": failure_details,
            }

    return {
        "timeline": timeline[-max_timeline_events:],
        "failure_point": failure_point,
        "last_successful_state": last_successful_state,
    }
