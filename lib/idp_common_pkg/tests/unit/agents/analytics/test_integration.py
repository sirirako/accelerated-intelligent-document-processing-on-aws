# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Integration tests for the analytics agent functionality.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock strands module before importing analytics modules
sys.modules["strands"] = MagicMock()

from idp_common.agents.analytics import (  # noqa: E402
    create_analytics_agent,
    get_analytics_config,
)


@pytest.mark.unit
class TestAnalyticsIntegration:
    """Integration tests for analytics agent functionality."""

    @patch.dict(
        "os.environ",
        {
            "ATHENA_DATABASE": "test_db",
            "ATHENA_OUTPUT_LOCATION": "s3://test-bucket/results/",
            "AWS_REGION": "us-east-1",
        },
    )
    @patch("idp_common.agents.analytics.agent.Agent")
    def test_end_to_end_agent_creation(self, mock_agent_class):
        """Test end-to-end agent creation with configuration."""
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance

        # Get configuration
        config = get_analytics_config()

        # Create agent
        agent = create_analytics_agent(config)

        # Verify configuration was loaded correctly
        assert config["athena_database"] == "test_db"
        assert config["athena_output_location"] == "s3://test-bucket/results/"
        assert config["aws_region"] == "us-east-1"

        # Verify agent was created
        assert agent == mock_agent_instance
        mock_agent_class.assert_called_once()

        # Verify the system prompt contains expected content
        call_args = mock_agent_class.call_args
        system_prompt = call_args.kwargs["system_prompt"]

        # Check that key components are in the system prompt
        assert "natural language questions into SQL queries" in system_prompt
        assert "run_athena_query" in system_prompt
        assert "execute_python" in system_prompt
        assert "responseType" in system_prompt

        # Verify tools were configured
        tools = call_args.kwargs["tools"]
        assert len(tools) == 2  # athena tool and python tool

    @patch.dict(
        "os.environ",
        {
            "ATHENA_DATABASE": "test_db",
            "ATHENA_OUTPUT_LOCATION": "s3://test-bucket/results/",
            "AWS_REGION": "us-east-1",
        },
    )
    def test_configuration_validation(self):
        """Test that configuration validation works correctly."""
        config = get_analytics_config()

        # Verify all required keys are present
        required_keys = ["athena_database", "athena_output_location", "aws_region"]
        for key in required_keys:
            assert key in config
            assert config[key] is not None

        # Verify defaults are set
        assert config["max_polling_attempts"] == 30
        assert config["query_timeout_seconds"] == 300

    def test_missing_configuration_raises_error(self):
        """Test that missing configuration raises appropriate error."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                get_analytics_config()

            error_msg = str(exc_info.value)
            assert "Missing required environment variables" in error_msg
            assert "ATHENA_DATABASE" in error_msg
            assert "ATHENA_OUTPUT_LOCATION" in error_msg
