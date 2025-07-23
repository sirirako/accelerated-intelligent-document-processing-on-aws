# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for the analytics agent module.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock strands module before importing analytics modules
sys.modules["strands"] = MagicMock()


@pytest.mark.unit
class TestCreateAnalyticsAgent:
    """Tests for the create_analytics_agent function."""

    @patch("idp_common.agents.analytics.agent.load_db_description")
    @patch("idp_common.agents.analytics.agent.load_result_format_description")
    @patch("idp_common.agents.analytics.agent.Agent")
    def test_create_analytics_agent_success(
        self, mock_agent_class, mock_load_result, mock_load_db
    ):
        """Test successful creation of analytics agent."""
        # Import here to avoid issues with mocking
        from idp_common.agents.analytics.agent import create_analytics_agent

        # Setup mocks
        mock_load_db.return_value = "Test database description"
        mock_load_result.return_value = "Test result format"
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance

        config = {
            "aws_region": "us-east-1",
            "athena_database": "test_db",
            "athena_output_location": "s3://test-bucket/results/",
        }

        # Call the function
        result = create_analytics_agent(config)

        # Verify the agent was created
        assert result == mock_agent_instance
        mock_agent_class.assert_called_once()

        # Verify the system prompt contains expected content
        call_args = mock_agent_class.call_args
        assert "tools" in call_args.kwargs
        assert "system_prompt" in call_args.kwargs

        system_prompt = call_args.kwargs["system_prompt"]
        assert "Test database description" in system_prompt
        assert "Test result format" in system_prompt
        assert "run_athena_query" in system_prompt
        assert "execute_python" in system_prompt

    @patch("idp_common.agents.analytics.agent.load_db_description")
    @patch("idp_common.agents.analytics.agent.load_result_format_description")
    @patch("idp_common.agents.analytics.agent.Agent")
    def test_create_analytics_agent_tools_configured(
        self, mock_agent_class, mock_load_result, mock_load_db
    ):
        """Test that analytics agent tools are properly configured."""
        from idp_common.agents.analytics.agent import create_analytics_agent

        mock_load_db.return_value = "Test database description"
        mock_load_result.return_value = "Test result format"
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance

        config = {
            "aws_region": "us-east-1",
            "athena_database": "test_db",
            "athena_output_location": "s3://test-bucket/results/",
        }

        create_analytics_agent(config)

        # Verify tools were passed to the agent
        call_args = mock_agent_class.call_args
        tools = call_args.kwargs["tools"]
        assert len(tools) == 2  # configured_athena_tool and execute_python

    @patch(
        "idp_common.agents.analytics.agent.load_db_description",
        side_effect=Exception("File error"),
    )
    @patch("idp_common.agents.analytics.agent.load_result_format_description")
    def test_create_analytics_agent_handles_asset_loading_error(
        self, mock_load_result, mock_load_db
    ):
        """Test that agent creation handles asset loading errors gracefully."""
        from idp_common.agents.analytics.agent import create_analytics_agent

        config = {
            "aws_region": "us-east-1",
            "athena_database": "test_db",
            "athena_output_location": "s3://test-bucket/results/",
        }

        # Should raise the exception since we don't handle it in the function
        with pytest.raises(Exception, match="File error"):
            create_analytics_agent(config)
