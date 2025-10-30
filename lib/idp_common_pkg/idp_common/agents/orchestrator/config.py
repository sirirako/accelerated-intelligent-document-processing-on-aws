# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Configuration management for orchestrator agents.
"""

import logging
import os
from typing import Any, Dict

from ..common.config import configure_logging, get_environment_config

logger = logging.getLogger(__name__)


def get_orchestrator_config() -> Dict[str, Any]:
    """
    Get orchestrator-specific configuration from environment variables and configuration table.

    Returns:
        Dict containing orchestrator configuration values

    Raises:
        ValueError: If required environment variables are missing
    """
    # Get base configuration
    config = get_environment_config()

    # Add orchestrator-specific defaults
    config.setdefault(
        "default_model_id", "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    )

    # Configure logging based on the configuration
    configure_logging(
        log_level=config.get("log_level"),
        strands_log_level=config.get("strands_log_level"),
    )

    logger.info("Orchestrator configuration loaded successfully")
    return config


def get_chat_companion_model_id(config_manager=None) -> str:
    """
    Get the chat companion model ID from configuration.

    Priority order:
    1. Environment variable CHAT_COMPANION_MODEL_ID
    2. Configuration table agents.chat_companion.model_id
    3. Default fallback

    Args:
        config_manager: Optional ConfigurationManager instance

    Returns:
        Model ID string
    """
    # First check environment variable (for backward compatibility)
    model_id = os.environ.get("CHAT_COMPANION_MODEL_ID")
    if model_id:
        logger.info(f"Using chat companion model ID from environment: {model_id}")
        return model_id

    # Try to get from configuration table
    if config_manager:
        try:
            from ...config import get_merged_configuration

            merged_config = get_merged_configuration(config_manager)

            # Navigate to agents.chat_companion.model_id
            agents_config = merged_config.get("agents", {})
            chat_companion_config = agents_config.get("chat_companion", {})
            config_model_id = chat_companion_config.get("model_id")

            if config_model_id:
                logger.info(
                    f"Using chat companion model ID from configuration: {config_model_id}"
                )
                return config_model_id

        except Exception as e:
            logger.warning(f"Failed to load model ID from configuration: {e}")

    # Fallback to default
    default_model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    logger.info(f"Using default chat companion model ID: {default_model_id}")
    return default_model_id
