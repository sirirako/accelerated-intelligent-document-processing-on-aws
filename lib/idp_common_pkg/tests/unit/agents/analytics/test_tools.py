# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for the analytics tools module.
"""

from unittest.mock import MagicMock, patch

import pytest
from idp_common.agents.analytics.tools.athena_tool import run_athena_query
from idp_common.agents.analytics.tools.python_tool import execute_python


@pytest.mark.unit
class TestRunAthenaQuery:
    """Tests for the run_athena_query tool."""

    def test_successful_query_execution(self):
        """Test successful Athena query execution."""
        # Mock the boto3 client and responses
        mock_athena_client = MagicMock()
        mock_athena_client.start_query_execution.return_value = {
            "QueryExecutionId": "test-execution-id"
        }
        mock_athena_client.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "SUCCEEDED"}}
        }
        mock_athena_client.get_query_results.return_value = {
            "ResultSet": {
                "ResultSetMetadata": {
                    "ColumnInfo": [{"Label": "column1"}, {"Label": "column2"}]
                },
                "Rows": [
                    {
                        "Data": [
                            {"VarCharValue": "header1"},
                            {"VarCharValue": "header2"},
                        ]
                    },  # Header row
                    {"Data": [{"VarCharValue": "value1"}, {"VarCharValue": "value2"}]},
                    {"Data": [{"VarCharValue": "value3"}, {}]},  # Test null value
                ],
            }
        }

        config = {
            "aws_region": "us-east-1",
            "athena_database": "test_db",
            "athena_output_location": "s3://test-bucket/results/",
            "max_polling_attempts": 3,
        }

        with patch("boto3.client", return_value=mock_athena_client):
            result = run_athena_query("SELECT * FROM test_table", config)

        assert result["success"] is True
        assert len(result["data"]) == 2
        assert result["data"][0] == {"column1": "value1", "column2": "value2"}
        assert result["data"][1] == {"column1": "value3", "column2": None}

    def test_failed_query_execution(self):
        """Test failed Athena query execution."""
        mock_athena_client = MagicMock()
        mock_athena_client.start_query_execution.return_value = {
            "QueryExecutionId": "test-execution-id"
        }
        mock_athena_client.get_query_execution.return_value = {
            "QueryExecution": {
                "Status": {
                    "State": "FAILED",
                    "StateChangeReason": "Syntax error in query",
                    "AthenaError": "SYNTAX_ERROR",
                }
            }
        }

        config = {
            "aws_region": "us-east-1",
            "athena_database": "test_db",
            "athena_output_location": "s3://test-bucket/results/",
            "max_polling_attempts": 3,
        }

        with patch("boto3.client", return_value=mock_athena_client):
            result = run_athena_query("SELECT * FROM invalid_table", config)

        assert result["success"] is False
        assert "Syntax error in query" in result["error"]
        assert result["athena_error_details"] == "SYNTAX_ERROR"

    def test_query_execution_exception(self):
        """Test exception during query execution."""
        config = {
            "aws_region": "us-east-1",
            "athena_database": "test_db",
            "athena_output_location": "s3://test-bucket/results/",
        }

        with patch("boto3.client", side_effect=Exception("Connection error")):
            result = run_athena_query("SELECT * FROM test_table", config)

        assert result["success"] is False
        assert "Connection error" in result["error"]


@pytest.mark.unit
class TestExecutePython:
    """Tests for the execute_python tool."""

    def test_successful_python_execution(self):
        """Test successful Python code execution."""
        code = """
import json
result = {"test": "value"}
print(json.dumps(result))
"""
        result = execute_python(code)

        assert result["success"] is True
        assert '{"test": "value"}' in result["stdout"]
        assert result["stderr"] == ""

    def test_python_execution_with_error(self):
        """Test Python code execution with error."""
        code = """
# This will cause a NameError
print(undefined_variable)
"""
        result = execute_python(code)

        assert result["success"] is False
        assert result["stdout"] == ""
        assert "undefined_variable" in result["stderr"]

    def test_python_execution_with_pandas(self):
        """Test Python code execution with pandas (if available)."""
        code = """
try:
    import pandas as pd
    df = pd.DataFrame({"col1": [1, 2], "col2": [3, 4]})
    print("pandas available")
    print(len(df))
except ImportError:
    print("pandas not available")
"""
        result = execute_python(code)

        assert result["success"] is True
        # Should work regardless of whether pandas is installed
        assert "available" in result["stdout"]

    def test_python_execution_output_capture(self):
        """Test that Python execution properly captures output."""
        code = """
print("Line 1")
print("Line 2")
import sys
print("Error line", file=sys.stderr)
"""
        result = execute_python(code)

        # Should capture stderr but still be successful since no exception
        assert result["success"] is False  # Because stderr has content
        assert "Line 1" in result["stdout"]
        assert "Line 2" in result["stdout"]
        assert "Error line" in result["stderr"]
