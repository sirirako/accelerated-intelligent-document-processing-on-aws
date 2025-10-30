# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for main Error Analyzer Agent.
"""

# ruff: noqa: E402, I001
# The above line disables E402 (module level import not at top of file) and I001 (import block sorting) for this file

from unittest.mock import MagicMock, patch

import pytest
from idp_common.config.models import IDPConfig


@pytest.mark.unit
class TestErrorAnalyzerAgent:
    """Test main error analyzer agent."""

    @patch("idp_common.agents.error_analyzer.agent.strands.Agent")
    @patch("boto3.Session")
    @patch("idp_common.agents.error_analyzer.agent.get_config")
    def test_create_error_analyzer_agent(
        self, mock_get_config, mock_session, mock_agent_class
    ):
        """Test main error analyzer agent creation."""
        from idp_common.agents.error_analyzer.agent import create_error_analyzer_agent

        # Mock get_config to return an IDPConfig object
        mock_config = IDPConfig()
        mock_get_config.return_value = mock_config

        mock_session.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.tools = [MagicMock() for _ in range(9)]  # 9 specific tools now
        mock_agent_class.return_value = mock_agent

        agent = create_error_analyzer_agent(session=mock_session.return_value)

        assert agent is not None
        assert hasattr(agent, "tools")
        assert len(agent.tools) == 9  # All specific tools

    @patch("idp_common.agents.error_analyzer.agent.strands.Agent")
    @patch("boto3.Session")
    @patch("idp_common.agents.error_analyzer.agent.get_config")
    def test_create_error_analyzer_agent_with_defaults(
        self, mock_get_config, mock_session, mock_agent_class
    ):
        """Test agent creation with default config and session."""
        from idp_common.agents.error_analyzer.agent import create_error_analyzer_agent

        # Mock get_config to return an IDPConfig object
        mock_config = IDPConfig()
        mock_get_config.return_value = mock_config

        mock_session.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.tools = [MagicMock() for _ in range(9)]  # 9 specific tools
        mock_agent_class.return_value = mock_agent

        agent = create_error_analyzer_agent()

        assert agent is not None
        assert hasattr(agent, "tools")
        assert len(agent.tools) == 9

    @patch("idp_common.agents.error_analyzer.agent.strands.Agent")
    @patch("boto3.Session")
    @patch("idp_common.agents.error_analyzer.agent.get_config")
    def test_agent_system_prompt_format(
        self, mock_get_config, mock_session, mock_agent_class
    ):
        """Test that agent is created with correct system prompt format."""
        from idp_common.agents.error_analyzer.agent import create_error_analyzer_agent

        # Mock get_config to return an IDPConfig object
        mock_config = IDPConfig()
        mock_get_config.return_value = mock_config

        mock_session.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent

        create_error_analyzer_agent()

        # Verify strands.Agent was called with correct parameters
        mock_agent_class.assert_called_once()
        call_args = mock_agent_class.call_args

        assert "tools" in call_args.kwargs
        assert "system_prompt" in call_args.kwargs
        assert "model" in call_args.kwargs

        # Check system prompt contains required sections
        system_prompt = call_args.kwargs["system_prompt"]
        assert "Root Cause" in system_prompt
        assert "Recommendations" in system_prompt
        assert "Do not include" in system_prompt

    def test_specific_tools_import(self):
        """Test that specific tools can be imported correctly."""
        from idp_common.agents.error_analyzer.tools import (
            cloudwatch_document_logs,
            dynamodb_status,
            xray_trace,
        )

        assert cloudwatch_document_logs is not None
        assert callable(cloudwatch_document_logs)
        assert dynamodb_status is not None
        assert callable(dynamodb_status)
        assert xray_trace is not None
        assert callable(xray_trace)
