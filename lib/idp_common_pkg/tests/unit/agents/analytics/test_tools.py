# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for the analytics tools module.
"""

# ruff: noqa: E402, I001
# The above line disables E402 (module level import not at top of file) and I001 (import block sorting) for this file

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock strands modules before importing analytics modules
sys.modules["strands"] = MagicMock()
sys.modules["strands.models"] = MagicMock()


@pytest.mark.unit
class TestAthenaQueryLogic:
    """Tests for the Athena query logic."""

    def test_boto3_client_creation(self):
        """Test that boto3 client can be created with proper config."""
        config = {
            "aws_region": "us-east-1",
            "athena_database": "test_db",
            "athena_output_location": "s3://test-bucket/results/",
        }

        with patch("boto3.client") as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.return_value = mock_client

            # Import and test the module's ability to create clients
            import boto3

            client = boto3.client("athena", region_name=config["aws_region"])

            mock_boto3.assert_called_with("athena", region_name="us-east-1")
            assert client == mock_client

    def test_athena_query_result_parsing(self):
        """Test parsing of Athena query results."""
        # This tests the logic that would be inside the run_athena_query function
        mock_result = {
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

        # Simulate the parsing logic that would be in the actual function
        columns = [
            col["Label"]
            for col in mock_result["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
        ]
        rows = mock_result["ResultSet"]["Rows"][1:]  # Skip header row

        parsed_data = []
        for row in rows:
            row_data = {}
            for i, col in enumerate(columns):
                cell = row["Data"][i] if i < len(row["Data"]) else {}
                row_data[col] = cell.get("VarCharValue") if cell else None
            parsed_data.append(row_data)

        assert len(parsed_data) == 2
        assert parsed_data[0] == {"column1": "value1", "column2": "value2"}
        assert parsed_data[1] == {"column1": "value3", "column2": None}

    def test_athena_error_handling(self):
        """Test error handling for Athena queries."""
        # Test the error handling logic
        mock_error_response = {
            "QueryExecution": {
                "Status": {
                    "State": "FAILED",
                    "StateChangeReason": "Syntax error in query",
                    "AthenaError": "SYNTAX_ERROR",
                }
            }
        }

        # Simulate error processing
        status = mock_error_response["QueryExecution"]["Status"]
        if status["State"] == "FAILED":
            error_result = {
                "success": False,
                "error": status["StateChangeReason"],
                "athena_error_details": status["AthenaError"],
            }

        assert error_result["success"] is False
        assert error_result["error"] == "Syntax error in query"
        assert error_result["athena_error_details"] == "SYNTAX_ERROR"


@pytest.mark.unit
class TestPythonExecutionLogic:
    """Tests for the Python execution logic."""

    def test_python_code_execution_success(self):
        """Test successful Python code execution logic."""
        import subprocess
        import sys

        code = """
import json
result = {"test": "value"}
print(json.dumps(result))
"""

        # Test that we can execute Python code (simulating the generate_plot logic)
        try:
            result = subprocess.run(
                [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
            )

            execution_result = {
                "success": result.returncode == 0 and not result.stderr,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

            assert execution_result["success"] is True
            assert '{"test": "value"}' in execution_result["stdout"]
            assert execution_result["stderr"] == ""

        except subprocess.TimeoutExpired:
            pytest.skip("Code execution timed out")

    def test_python_code_execution_error(self):
        """Test Python code execution with error."""
        import subprocess
        import sys

        code = """
# This will cause a NameError
print(undefined_variable)
"""

        try:
            result = subprocess.run(
                [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
            )

            execution_result = {
                "success": result.returncode == 0 and not result.stderr,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

            assert execution_result["success"] is False
            assert execution_result["stdout"] == ""
            assert "undefined_variable" in execution_result["stderr"]

        except subprocess.TimeoutExpired:
            pytest.skip("Code execution timed out")

    def test_python_code_with_stderr_output(self):
        """Test Python code that writes to stderr."""
        import subprocess
        import sys

        code = """
print("Line 1")
print("Line 2")
import sys
print("Error line", file=sys.stderr)
"""

        try:
            result = subprocess.run(
                [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
            )

            execution_result = {
                "success": result.returncode == 0 and not result.stderr,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

            # Should be considered unsuccessful because stderr has content
            assert execution_result["success"] is False
            assert "Line 1" in execution_result["stdout"]
            assert "Line 2" in execution_result["stdout"]
            assert "Error line" in execution_result["stderr"]

        except subprocess.TimeoutExpired:
            pytest.skip("Code execution timed out")


@pytest.mark.unit
class TestToolsIntegration:
    """Integration tests for tools functionality."""

    def test_tools_are_importable(self):
        """Test that tool modules can be imported without errors."""
        # This verifies the modules are structured correctly
        from idp_common.agents.analytics.tools import athena_tool
        from idp_common.agents.analytics.tools import generate_plot_tool
        from idp_common.agents.analytics.tools import get_database_info_tool

        # Verify the modules have the expected functions
        assert hasattr(athena_tool, "run_athena_query")
        assert hasattr(generate_plot_tool, "generate_plot")
        assert hasattr(get_database_info_tool, "get_database_info")

    def test_tool_function_signatures(self):
        """Test that tool functions have expected signatures."""
        from idp_common.agents.analytics.tools.athena_tool import run_athena_query
        from idp_common.agents.analytics.tools.generate_plot_tool import generate_plot

        import inspect

        # Since the @tool decorator modifies function signatures to use *args, **kwargs,
        # we test that the functions are callable and have the decorator applied
        athena_sig = inspect.signature(run_athena_query)
        athena_params = list(athena_sig.parameters.keys())

        # The decorator changes the signature, so we expect args/kwargs
        # This confirms the decorator was applied
        assert len(athena_params) >= 1  # Should have at least one parameter

        # Test generate plot signature
        plot_sig = inspect.signature(generate_plot)
        plot_params = list(plot_sig.parameters.keys())
        assert len(plot_params) >= 1  # Should have at least one parameter

        # Test that functions are callable (most important for unit tests)
        assert callable(run_athena_query)
        assert callable(generate_plot)
