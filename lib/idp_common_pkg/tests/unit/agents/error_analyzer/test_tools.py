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
            search_cloudwatch_logs,
        )

        assert search_cloudwatch_logs is not None
        assert callable(search_cloudwatch_logs)

    def test_dynamodb_tools_import(self):
        """Test DynamoDB tools can be imported."""
        from idp_common.agents.error_analyzer.tools import (
            fetch_document_record,
            fetch_recent_records,
        )

        assert fetch_document_record is not None
        assert callable(fetch_document_record)
        assert fetch_recent_records is not None
        assert callable(fetch_recent_records)

    def test_execution_context_tools_import(self):
        """Test execution context tools can be imported."""
        from idp_common.agents.error_analyzer.tools import (
            analyze_workflow_execution,
            lambda_lookup,
        )

        assert lambda_lookup is not None
        assert callable(lambda_lookup)
        assert analyze_workflow_execution is not None
        assert callable(analyze_workflow_execution)

    def test_xray_tools_import(self):
        """Test X-Ray tools can be imported."""
        from idp_common.agents.error_analyzer.tools import (
            analyze_document_trace,
            analyze_system_performance,
        )

        assert analyze_document_trace is not None
        assert callable(analyze_document_trace)
        assert analyze_system_performance is not None
        assert callable(analyze_system_performance)

    def test_all_tools_available(self):
        """Test that all 7 tools are available in the tools module."""
        from idp_common.agents.error_analyzer.tools import __all__

        expected_tools = {
            "search_cloudwatch_logs",
            "fetch_document_record",
            "fetch_recent_records",
            "lambda_lookup",
            "analyze_workflow_execution",
            "analyze_document_trace",
            "analyze_system_performance",
        }

        assert len(__all__) == 7
        assert set(__all__) == expected_tools
