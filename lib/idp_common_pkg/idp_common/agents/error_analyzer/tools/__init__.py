# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Error Analyzer tools for Strands agents.

Provides comprehensive error analysis capabilities including:
- Document-specific failure analysis
- System-wide error pattern detection
- CloudWatch log searching and filtering
- DynamoDB tracking table queries
- Step Function execution analysis
- Lambda function context extraction
"""

from .cloudwatch_tool import cloudwatch_document_logs, cloudwatch_logs
from .dynamodb_tool import (
    dynamodb_query,
    dynamodb_record,
    dynamodb_status,
)
from .lambda_tool import lambda_lookup
from .stepfunction_tool import stepfunction_details
from .xray_tool import (
    xray_performance_analysis,
    xray_trace,
)

__all__ = [
    "cloudwatch_document_logs",
    "cloudwatch_logs",
    "lambda_lookup",
    "dynamodb_record",
    "dynamodb_status",
    "dynamodb_query",
    "stepfunction_details",
    "xray_trace",
    "xray_performance_analysis",
]
