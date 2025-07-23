# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for the analytics configuration module.
"""

import os
from unittest.mock import mock_open, patch

import pytest
from idp_common.agents.analytics.config import (
    get_analytics_config,
    load_db_description,
    load_result_format_description,
)


@pytest.mark.unit
class TestGetAnalyticsConfig:
    """Tests for the get_analytics_config function."""

    def test_get_analytics_config_success(self):
        """Test successful analytics configuration loading."""
        env_vars = {
            "AWS_REGION": "us-west-2",
            "ATHENA_DATABASE": "test_database",
            "ATHENA_OUTPUT_LOCATION": "s3://test-bucket/results/"
        }
        with patch.dict(os.environ, env_vars, clear=True):
            config = get_analytics_config()
            
            assert config["aws_region"] == "us-west-2"
            assert config["athena_database"] == "test_database"
            assert config["athena_output_location"] == "s3://test-bucket/results/"
            assert config["max_polling_attempts"] == 30
            assert config["query_timeout_seconds"] == 300

    def test_missing_required_config_raises_error(self):
        """Test that missing required configuration raises ValueError."""
        env_vars = {
            "AWS_REGION": "us-west-2",
            "ATHENA_DATABASE": "test_database"
            # Missing ATHENA_OUTPUT_LOCATION
        }
        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError) as exc_info:
                get_analytics_config()
            
            assert "Missing required environment variables" in str(exc_info.value)
            assert "ATHENA_OUTPUT_LOCATION" in str(exc_info.value)

    def test_all_missing_required_config(self):
        """Test that all missing required configuration raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                get_analytics_config()
            
            error_msg = str(exc_info.value)
            assert "Missing required environment variables" in error_msg
            assert "ATHENA_DATABASE" in error_msg
            assert "ATHENA_OUTPUT_LOCATION" in error_msg


@pytest.mark.unit
class TestLoadDbDescription:
    """Tests for the load_db_description function."""

    @patch("builtins.open", new_callable=mock_open, read_data="Test database description")
    def test_load_db_description_success(self, mock_file):
        """Test successful loading of database description."""
        result = load_db_description()
        assert result == "Test database description"
        mock_file.assert_called_once()

    @patch("builtins.open", side_effect=FileNotFoundError())
    def test_load_db_description_file_not_found(self, mock_file):
        """Test handling of missing database description file."""
        result = load_db_description()
        assert result == "No database description available."
        mock_file.assert_called_once()


@pytest.mark.unit
class TestLoadResultFormatDescription:
    """Tests for the load_result_format_description function."""

    @patch("builtins.open", new_callable=mock_open, read_data="Test result format description")
    def test_load_result_format_description_success(self, mock_file):
        """Test successful loading of result format description."""
        result = load_result_format_description()
        assert result == "Test result format description"
        mock_file.assert_called_once()

    @patch("builtins.open", side_effect=FileNotFoundError())
    def test_load_result_format_description_file_not_found(self, mock_file):
        """Test handling of missing result format description file."""
        result = load_result_format_description()
        assert result == "No result format description available."
        mock_file.assert_called_once()
