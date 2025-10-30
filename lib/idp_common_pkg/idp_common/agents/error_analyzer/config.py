# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Configuration management for error analyzer agents.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def get_aws_service_capabilities() -> Dict[str, Any]:
    """Returns AWS service integration metadata and descriptions."""
    return {
        "cloudwatch_logs": {
            "description": "CloudWatch Logs integration for error analysis",
            "capabilities": [
                "search_log_events",
                "get_log_groups",
                "filter_log_events",
            ],
            "implementation": "Native AWS SDK integration",
        },
        "dynamodb": {
            "description": "DynamoDB integration for document tracking",
            "capabilities": ["scan_table", "query_table", "get_item"],
            "implementation": "Native AWS SDK integration",
        },
        "benefits": [
            "No external dependencies",
            "Native Lambda integration",
            "Optimal performance",
        ],
    }


# Utility functions
def decimal_to_float(obj: Any) -> Any:
    """Recursively converts DynamoDB Decimal objects to JSON-compatible floats."""
    if hasattr(obj, "__class__") and obj.__class__.__name__ == "Decimal":
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(v) for v in obj]
    return obj


def create_error_response(error: str, **kwargs) -> Dict[str, Any]:
    """Creates standardized error response with consistent format."""
    response = {"error": str(error), "success": False}
    response.update(kwargs)
    return response


def create_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Creates standardized response with consistent format."""
    return data


def safe_int_conversion(value: Any, default: int = 0) -> int:
    """Safely converts values to integers with fallback handling."""
    try:
        return int(float(value)) if value is not None else default
    except (ValueError, TypeError):
        return default


def truncate_message(message: str, max_length: int = 200) -> str:
    """Truncates messages to specified length with ellipsis indicator."""
    if len(message) <= max_length:
        return message
    return message[:max_length] + "... [truncated]"
