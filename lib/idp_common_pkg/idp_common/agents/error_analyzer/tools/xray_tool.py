# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
X-Ray tools for tracing analysis and performance monitoring.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

import boto3
from strands import tool

from ..config import (
    create_error_response,
    create_response,
    get_config_with_fallback,
    safe_int_conversion,
)

logger = logging.getLogger(__name__)


def _extract_trace_summary(trace: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract key information from X-Ray trace summary.

    Args:
        trace: X-Ray trace summary dictionary

    Returns:
        Dict containing extracted trace information
    """
    return {
        "trace_id": trace.get("Id"),
        "duration": trace.get("Duration", 0),
        "response_time": trace.get("ResponseTime", 0),
        "has_error": trace.get("HasError", False),
        "has_fault": trace.get("HasFault", False),
        "has_throttle": trace.get("HasThrottle", False),
        "service_ids": [service.get("Name") for service in trace.get("ServiceIds", [])],
    }


def _parse_segment_document(segment_doc: Any) -> Dict[str, Any]:
    """
    Parse segment document from string or dict format.

    Args:
        segment_doc: Segment document (string or dict)

    Returns:
        Parsed segment document as dict
    """
    if isinstance(segment_doc, str):
        import json

        try:
            return json.loads(segment_doc)
        except json.JSONDecodeError:
            return {}
    return segment_doc or {}


def _analyze_trace_segments(segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze X-Ray trace segments to identify performance bottlenecks.

    Args:
        segments: List of X-Ray trace segments

    Returns:
        Dict containing segment analysis
    """
    if not segments:
        return {"error": "No trace segments available"}

    total_duration = 0
    error_segments = []
    slow_segments = []

    config = get_config_with_fallback()
    slow_threshold = config.get("xray_slow_segment_threshold_ms", 5000)

    for segment in segments:
        segment_doc = _parse_segment_document(segment.get("Document", {}))
        if not segment_doc:
            continue

        duration = segment_doc.get("end_time", 0) - segment_doc.get("start_time", 0)
        total_duration += duration

        # Check for errors
        if segment_doc.get("error") or segment_doc.get("fault"):
            error_segments.append(
                {
                    "id": segment_doc.get("id"),
                    "name": segment_doc.get("name"),
                    "error": segment_doc.get("error"),
                    "fault": segment_doc.get("fault"),
                    "cause": segment_doc.get("cause", {}).get("exceptions", []),
                }
            )

        # Check for slow segments
        if duration * 1000 > slow_threshold:  # Convert to ms
            slow_segments.append(
                {
                    "id": segment_doc.get("id"),
                    "name": segment_doc.get("name"),
                    "duration_ms": duration * 1000,
                    "service": segment_doc.get("service", {}).get("name"),
                }
            )

    return {
        "total_segments": len(segments),
        "total_duration_ms": total_duration * 1000,
        "error_segments": error_segments,
        "slow_segments": slow_segments,
        "has_performance_issues": len(slow_segments) > 0 or len(error_segments) > 0,
    }


def _parse_segment_for_lambda(segment: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Recursively parse segment for Lambda executions.

    Args:
        segment: X-Ray segment document

    Returns:
        List of Lambda execution details
    """
    lambda_executions = []

    if segment.get("origin") == "AWS::Lambda":
        aws_info = segment.get("aws", {})
        function_name = segment.get("name", "Unknown")

        if "resource_arn" in segment:
            function_name = segment["resource_arn"].split(":")[-1]

        lambda_executions.append(
            {
                "function_name": function_name,
                "request_id": aws_info.get("request_id"),
            }
        )

    for subsegment in segment.get("subsegments", []):
        lambda_executions.extend(_parse_segment_for_lambda(subsegment))

    return lambda_executions


def extract_lambda_request_ids(trace_id: str) -> Dict[str, str]:
    """
    Extract Lambda request IDs from X-Ray trace.

    Args:
        trace_id: X-Ray trace ID

    Returns:
        Dict mapping Lambda function names to their CloudWatch request IDs
    """
    xray_client = boto3.client("xray")

    try:
        response = xray_client.batch_get_traces(TraceIds=[trace_id])
        traces = response.get("Traces", [])

        if not traces:
            return {}

        lambda_executions = []
        for trace in traces:
            for segment in trace.get("Segments", []):
                try:
                    segment_doc = json.loads(segment["Document"])
                    lambda_executions.extend(_parse_segment_for_lambda(segment_doc))
                except json.JSONDecodeError:
                    continue

        # Convert to function_name -> request_id mapping
        result = {}
        for execution in lambda_executions:
            if execution["request_id"]:
                result[execution["function_name"]] = execution["request_id"]

        return result

    except Exception as e:
        logger.error(f"Error extracting Lambda request IDs: {e}")
        return {}


@tool
def xray_performance_analysis(
    stack_name: str = None, hours_back: int = None
) -> Dict[str, Any]:
    """
    Analyze X-Ray performance issues focusing on stack-specific traces first, then general infrastructure.

    Intelligently identifies performance bottlenecks by prioritizing stack-specific analysis
    when stack information is available, otherwise performs general infrastructure analysis.

    Use this tool to:
    - Identify recent performance issues in the system
    - Find stack-specific errors and bottlenecks
    - Analyze service dependencies and error patterns
    - Troubleshoot system-wide performance degradation

    Args:
        stack_name: CloudFormation stack name to focus analysis (optional)
        hours_back: Hours to look back for analysis (default: 1)

    Returns:
        Dict with keys:
        - analysis_type (str): "stack_focused" or "infrastructure_wide"
        - stack_name (str): Stack analyzed (if provided)
        - traces_found (int): Number of traces analyzed
        - services_found (int): Number of services analyzed
        - performance_issues (dict): Detailed performance analysis
        - recommendations (list): Actionable recommendations
    """
    try:
        hours_back = safe_int_conversion(hours_back, 1)
        xray_client = boto3.client("xray")

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)

        # Try stack-specific analysis first if stack_name provided
        if stack_name:
            stack_analysis = _analyze_stack_traces(
                xray_client, stack_name, start_time, end_time
            )
            if stack_analysis.get("traces_found", 0) > 0:
                # Get service map for additional context
                service_analysis = _analyze_service_performance(
                    xray_client, start_time, end_time
                )

                return create_response(
                    {
                        "analysis_type": "stack_focused",
                        "stack_name": stack_name,
                        "traces_found": stack_analysis["traces_found"],
                        "services_found": service_analysis.get("services_found", 0),
                        "performance_issues": {
                            "stack_traces": stack_analysis,
                            "service_map": service_analysis,
                        },
                        "recommendations": _generate_recommendations(
                            stack_analysis, service_analysis
                        ),
                    }
                )

        # Fallback to general infrastructure analysis
        service_analysis = _analyze_service_performance(
            xray_client, start_time, end_time
        )

        return create_response(
            {
                "analysis_type": "infrastructure_wide",
                "stack_name": stack_name or "not_provided",
                "traces_found": 0,
                "services_found": service_analysis.get("services_found", 0),
                "performance_issues": {"service_map": service_analysis},
                "recommendations": _generate_recommendations(None, service_analysis),
            }
        )

    except Exception as e:
        logger.error(f"Error in X-Ray performance analysis: {e}")
        return create_error_response(str(e))


def _analyze_stack_traces(
    xray_client, stack_name: str, start_time: datetime, end_time: datetime
) -> Dict[str, Any]:
    """
    Analyze X-Ray traces for a specific stack.
    """
    try:
        response = xray_client.get_trace_summaries(
            TimeRangeType="TimeRangeByStartTime",
            StartTime=start_time,
            EndTime=end_time,
            FilterExpression=f'annotation.stack_name = "{stack_name}"',
            MaxResults=50,
        )

        traces = response.get("TraceSummaries", [])

        if not traces:
            return {"traces_found": 0, "message": "No traces found for stack"}

        # Analyze trace summaries
        total_errors = sum(1 for trace in traces if trace.get("HasError"))
        total_faults = sum(1 for trace in traces if trace.get("HasFault"))
        total_throttles = sum(1 for trace in traces if trace.get("HasThrottle"))

        service_names = set()
        for trace in traces:
            for service in trace.get("ServiceIds", []):
                service_names.add(service.get("Name"))

        return {
            "traces_found": len(traces),
            "total_errors": total_errors,
            "total_faults": total_faults,
            "total_throttles": total_throttles,
            "services_involved": list(service_names),
            "error_rate": total_errors / len(traces) if traces else 0,
        }

    except Exception as e:
        logger.error(f"Error analyzing stack traces: {e}")
        return {"traces_found": 0, "error": str(e)}


def _analyze_service_performance(
    xray_client, start_time: datetime, end_time: datetime
) -> Dict[str, Any]:
    """
    Analyze X-Ray service map for performance issues.
    """
    try:
        response = xray_client.get_service_graph(StartTime=start_time, EndTime=end_time)
        services = response.get("Services", [])

        if not services:
            return {"services_found": 0, "message": "No service map data available"}

        config = get_config_with_fallback()
        error_rate_threshold = config.get("xray_error_rate_threshold", 0.05)
        response_time_threshold = config.get("xray_response_time_threshold_ms", 10000)

        service_analysis = []
        high_error_services = []
        slow_services = []

        for service in services:
            service_stats = service.get("SummaryStatistics", {})
            error_rate = service_stats.get("ErrorStatistics", {}).get("ErrorRate", 0)
            response_time = service_stats.get("ResponseTimeHistogram", {}).get(
                "TotalTime", 0
            )
            request_count = service_stats.get("RequestCount", 0)

            analysis = {
                "name": service.get("Name"),
                "type": service.get("Type"),
                "request_count": request_count,
                "error_rate": error_rate,
                "response_time_ms": response_time * 1000,
                "edges": len(service.get("Edges", [])),
            }

            service_analysis.append(analysis)

            if error_rate > error_rate_threshold:
                high_error_services.append(analysis["name"])
            if response_time * 1000 > response_time_threshold:
                slow_services.append(analysis["name"])

        return {
            "services_found": len(services),
            "service_analysis": service_analysis,
            "high_error_services": high_error_services,
            "slow_services": slow_services,
        }

    except Exception as e:
        logger.error(f"Error analyzing service performance: {e}")
        return {"services_found": 0, "error": str(e)}


def _generate_recommendations(
    stack_analysis: Dict[str, Any], service_analysis: Dict[str, Any]
) -> List[str]:
    """
    Generate actionable recommendations based on analysis results.
    """
    recommendations = []

    if stack_analysis and stack_analysis.get("traces_found", 0) > 0:
        if stack_analysis.get("total_errors", 0) > 0:
            recommendations.append(
                "Review stack-specific error traces for failure patterns"
            )
        if stack_analysis.get("total_throttles", 0) > 0:
            recommendations.append(
                "Check stack services for throttling and capacity issues"
            )

    if service_analysis and service_analysis.get("services_found", 0) > 0:
        if service_analysis.get("high_error_services"):
            recommendations.append(
                f"Investigate high-error services: {', '.join(service_analysis['high_error_services'][:3])}"
            )
        if service_analysis.get("slow_services"):
            recommendations.append(
                f"Optimize slow services: {', '.join(service_analysis['slow_services'][:3])}"
            )

    if not recommendations:
        recommendations = [
            "Ensure X-Ray tracing is enabled for all services",
            "Check if services have been active in the time window",
            "Verify X-Ray daemon configuration",
        ]

    return recommendations


@tool
def xray_trace(document_id: str, tracking_table_name: str = None) -> Dict[str, Any]:
    """
    Analyze X-Ray traces for a specific document to identify performance issues and errors.

    Args:
        document_id: The document ID to analyze
        tracking_table_name: DynamoDB table name containing document records

    Returns:
        Dict containing comprehensive trace analysis for the document
    """
    try:
        if not document_id:
            return create_error_response("No document ID provided")

        xray_client = boto3.client("xray")
        trace_id = None

        # Try to get trace_id from DynamoDB first
        if tracking_table_name:
            try:
                dynamodb = boto3.resource("dynamodb")
                table = dynamodb.Table(tracking_table_name)

                response = table.get_item(
                    Key={"PK": f"doc#{document_id}", "SK": "none"}
                )

                if "Item" in response:
                    trace_id = response["Item"].get("TraceId")
                    logger.info(f"TraceId: {trace_id} for document {document_id}")

            except Exception as e:
                logger.warning(f"Could not retrieve trace_id from DynamoDB: {e}")

        # Fallback to X-Ray annotation query if no trace_id found
        if not trace_id:
            logger.info(
                f"Searching X-Ray traces by annotation for document {document_id}"
            )

            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=24)  # Search last 24 hours

            response = xray_client.get_trace_summaries(
                TimeRangeType="TimeRangeByStartTime",
                StartTime=start_time,
                EndTime=end_time,
                FilterExpression=f'annotation.document_id = "{document_id}"',
                MaxResults=10,
            )

            traces = response.get("TraceSummaries", [])
            if not traces:
                return create_response(
                    {
                        "document_id": document_id,
                        "trace_found": False,
                        "traces_found": 0,
                        "message": "No X-Ray traces found for this document",
                        "recommendations": [
                            "Verify document was processed recently (within 24 hours)",
                            "Check if X-Ray tracing is enabled for all Lambda functions",
                            "Ensure document ID is correct",
                        ],
                    }
                )

            # Use the most recent trace
            trace_id = traces[0].get("Id")
            logger.info(f"Found trace_id {trace_id} via annotation query")

        # Get detailed trace analysis
        if trace_id:
            logger.info(f"Attempting to get trace details for trace_id: {trace_id}")
            segments_response = xray_client.batch_get_traces(TraceIds=[trace_id])
            logger.info(f"X-Ray batch_get_traces response: {segments_response}")

            if not segments_response.get("Traces"):
                return create_error_response(
                    f"Could not retrieve trace details for {trace_id}"
                )

            trace_data = segments_response["Traces"][0]
            segments = trace_data.get("Segments", [])

            # Analyze segments for performance and errors
            detailed_analysis = _analyze_trace_segments(segments)

            # Extract service timeline
            service_timeline = []
            for segment in segments:
                segment_doc = _parse_segment_document(segment.get("Document", {}))
                if not segment_doc:
                    continue

                service_timeline.append(
                    {
                        "service_name": segment_doc.get("name"),
                        "start_time": segment_doc.get("start_time"),
                        "end_time": segment_doc.get("end_time"),
                        "duration_ms": (
                            segment_doc.get("end_time", 0)
                            - segment_doc.get("start_time", 0)
                        )
                        * 1000,
                        "has_error": bool(
                            segment_doc.get("error") or segment_doc.get("fault")
                        ),
                        "annotations": segment_doc.get("annotations", {}),
                    }
                )

            return create_response(
                {
                    "document_id": document_id,
                    "trace_id": trace_id,
                    "trace_found": True,
                    "detailed_analysis": detailed_analysis,
                    "service_timeline": sorted(
                        service_timeline, key=lambda x: x.get("start_time", 0)
                    ),
                    "recommendations": [
                        "Review error segments for specific failure causes",
                        "Check slow segments for performance optimization",
                        "Analyze service timeline for bottlenecks",
                    ],
                }
            )

        return create_response(
            {
                "document_id": document_id,
                "trace_found": False,
                "message": "Could not find or analyze trace for document",
                "recommendations": [
                    "Verify document was processed recently",
                    "Check X-Ray tracing configuration",
                    "Ensure document ID is correct",
                ],
            }
        )

    except Exception as e:
        logger.error(f"Error analyzing X-Ray traces for document {document_id}: {e}")
        return create_error_response(str(e))
