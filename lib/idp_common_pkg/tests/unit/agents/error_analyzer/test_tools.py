# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for Error Analyzer tools.
"""

import pytest


@pytest.mark.unit
class TestErrorAnalyzerTools:
    """Test error analyzer individual tools."""

    def test_cloudwatch_tools_import(self):
        """Test CloudWatch tools can be imported."""
        from idp_common.agents.error_analyzer.tools import (
            cloudwatch_document_logs,
            cloudwatch_logs,
        )

        assert cloudwatch_document_logs is not None
        assert callable(cloudwatch_document_logs)
        assert cloudwatch_logs is not None
        assert callable(cloudwatch_logs)

    def test_dynamodb_tools_import(self):
        """Test DynamoDB tools can be imported."""
        from idp_common.agents.error_analyzer.tools import (
            dynamodb_query,
            dynamodb_record,
            dynamodb_status,
        )

        assert dynamodb_record is not None
        assert callable(dynamodb_record)
        assert dynamodb_status is not None
        assert callable(dynamodb_status)
        assert dynamodb_query is not None
        assert callable(dynamodb_query)

    def test_execution_context_tools_import(self):
        """Test execution context tools can be imported."""
        from idp_common.agents.error_analyzer.tools import (
            lambda_lookup,
            stepfunction_details,
        )

        assert lambda_lookup is not None
        assert callable(lambda_lookup)
        assert stepfunction_details is not None
        assert callable(stepfunction_details)

    def test_xray_tools_import(self):
        """Test X-Ray tools can be imported."""
        from idp_common.agents.error_analyzer.tools import (
            xray_performance_analysis,
            xray_trace,
        )

        assert xray_trace is not None
        assert callable(xray_trace)
        assert xray_performance_analysis is not None
        assert callable(xray_performance_analysis)

    def test_all_tools_available(self):
        """Test that all 11 tools are available in the tools module."""
        from idp_common.agents.error_analyzer.tools import __all__

        expected_tools = {
            "cloudwatch_document_logs",
            "cloudwatch_logs",
            "dynamodb_record",
            "dynamodb_status",
            "dynamodb_query",
            "lambda_lookup",
            "stepfunction_details",
            "xray_trace",
            "xray_performance_analysis",
        }

        assert len(__all__) == 9
        assert set(__all__) == expected_tools
