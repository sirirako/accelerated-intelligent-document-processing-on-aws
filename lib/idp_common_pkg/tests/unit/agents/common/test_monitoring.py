# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for agent monitoring functionality.
"""

from unittest.mock import Mock, patch

import pytest
from idp_common.agents.common.dynamodb_logger import DynamoDBMessageTracker
from idp_common.agents.common.monitoring import AgentMonitor, MessageTracker


@pytest.mark.unit
class TestAgentMonitor:
    """Test the AgentMonitor class."""

    def test_monitor_initialization(self):
        """Test that AgentMonitor initializes correctly."""
        monitor = AgentMonitor()

        assert monitor.execution_stats["messages_added"] == 0
        assert monitor.execution_stats["tool_invocations"] == 0
        assert monitor.execution_stats["model_invocations"] == 0
        assert monitor.execution_stats["requests_processed"] == 0
        assert monitor.message_history == []
        assert monitor.tool_history == []
        assert monitor.model_history == []

    def test_message_preview_extraction(self):
        """Test message preview extraction logic."""
        monitor = AgentMonitor()

        # Test with a mock message object
        mock_message = Mock()
        mock_message.role = "user"
        mock_message.content = "Test message content"

        preview = monitor._get_message_preview(mock_message)

        assert preview["role"] == "user"
        assert preview["content"] == "Test message content"
        assert preview["message_type"] == "Mock"

    def test_message_preview_with_tool_message(self):
        """Test message preview extraction for tool messages."""
        monitor = AgentMonitor()

        # Test with a mock tool message
        mock_message = Mock()
        mock_message.role = "tool"
        mock_message.content = "Tool execution result"

        preview = monitor._get_message_preview(mock_message)

        assert preview["role"] == "tool"
        assert "Tool" in preview["content"]
        assert "tool_name" in preview


@pytest.mark.unit
class TestMessageTracker:
    """Test the MessageTracker class."""

    def test_tracker_initialization(self):
        """Test that MessageTracker initializes correctly."""
        tracker = MessageTracker()

        assert tracker.messages == []
        assert tracker.callback_fn is None

    def test_tracker_with_callback(self):
        """Test MessageTracker with custom callback."""
        callback_called = False

        def test_callback(event, message_data):
            nonlocal callback_called
            callback_called = True

        tracker = MessageTracker(callback_fn=test_callback)
        assert tracker.callback_fn is not None


@pytest.mark.unit
class TestDynamoDBMessageTracker:
    """Test the DynamoDBMessageTracker class."""

    def test_tracker_initialization_disabled(self):
        """Test tracker initialization when disabled."""
        tracker = DynamoDBMessageTracker(
            job_id="test-job", user_id="test-user", enabled=False
        )

        assert not tracker.enabled
        assert tracker.db_logger is None

    @patch.dict("os.environ", {"ANALYTICS_TABLE": "test-table"})
    @patch("idp_common.agents.common.dynamodb_logger.DynamoDBMessageLogger")
    def test_tracker_initialization_enabled(self, mock_logger_class):
        """Test tracker initialization when enabled."""
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger

        tracker = DynamoDBMessageTracker(
            job_id="test-job", user_id="test-user", enabled=True
        )

        assert tracker.enabled
        assert tracker.job_id == "test-job"
        assert tracker.user_id == "test-user"
        mock_logger_class.assert_called_once_with("test-table")

    @patch.dict("os.environ", {})
    def test_tracker_initialization_no_table(self):
        """Test tracker initialization when no table name is provided."""
        tracker = DynamoDBMessageTracker(
            job_id="test-job", user_id="test-user", enabled=True
        )

        assert not tracker.enabled
        assert tracker.db_logger is None
