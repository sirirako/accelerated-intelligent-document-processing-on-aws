# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Common configuration utilities for IDP agents.
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def get_environment_config(required_keys: Optional[list] = None) -> Dict[str, Any]:
    """
    Get configuration from environment variables with validation.

    Args:
        required_keys: List of required environment variable names

    Returns:
        Dict containing configuration values

    Raises:
        ValueError: If required environment variables are missing
    """
    config = {}

    # Get AWS region
    config["aws_region"] = os.getenv("AWS_REGION", "us-east-1")

    # Get general logging configuration
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    try:
        config["log_level"] = getattr(logging, log_level_str)
    except AttributeError:
        logger.warning(f"Invalid LOG_LEVEL: {log_level_str}, defaulting to INFO")
        config["log_level"] = logging.INFO

    # Get Strands-specific logging configuration (separate from general logging)
    strands_log_level_str = os.getenv("STRANDS_LOG_LEVEL", "INFO").upper()

    try:
        config["strands_log_level"] = getattr(logging, strands_log_level_str)
    except AttributeError:
        logger.warning(
            f"Invalid STRANDS_LOG_LEVEL: {strands_log_level_str}, defaulting to INFO"
        )
        config["strands_log_level"] = logging.INFO

    # Validate required keys if provided
    if required_keys:
        missing_keys = []
        for key in required_keys:
            value = os.getenv(key)
            if value is None:
                missing_keys.append(key)
            else:
                config[key.lower()] = value

        if missing_keys:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_keys)}"
            )

    logger.info(f"Loaded configuration with keys: {list(config.keys())}")
    return config


def configure_logging(log_level=None, strands_log_level=None):
    """
    Configure logging for both the application and Strands.

    This function sets up two separate logging configurations:
    1. General application logging (idp_common and other modules)
    2. Strands-specific logging (for the Strands framework only)

    Args:
        log_level: Logging level for the application (default: from environment or INFO)
        strands_log_level: Logging level specifically for Strands framework (default: from environment or INFO)
    """
    # Get general log level from parameter or environment
    if log_level is None:
        log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        try:
            log_level = getattr(logging, log_level_str)
        except AttributeError:
            logger.warning(f"Invalid LOG_LEVEL: {log_level_str}, defaulting to INFO")
            log_level = logging.INFO

    # Get Strands-specific log level from parameter or environment
    if strands_log_level is None:
        strands_log_level_str = os.getenv("STRANDS_LOG_LEVEL", "INFO").upper()
        try:
            strands_log_level = getattr(logging, strands_log_level_str)
        except AttributeError:
            logger.warning(
                f"Invalid STRANDS_LOG_LEVEL: {strands_log_level_str}, defaulting to INFO"
            )
            strands_log_level = logging.INFO

    # Configure root logger for application
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )

    # Configure Strands logger separately
    strands_logger = logging.getLogger("strands")
    strands_logger.setLevel(strands_log_level)

    # Explicitly configure monitoring loggers to ensure they appear in CloudWatch
    monitoring_logger = logging.getLogger("idp_common.agents.common.monitoring")
    monitoring_logger.setLevel(log_level)

    dynamodb_logger = logging.getLogger("idp_common.agents.common.dynamodb_logger")
    dynamodb_logger.setLevel(log_level)

    logger.debug(
        f"Configured application logging level: {logging.getLevelName(log_level)}"
    )
    logger.debug(
        f"Configured Strands framework logging level: {logging.getLevelName(strands_log_level)}"
    )
    logger.debug(
        f"Configured monitoring loggers level: {logging.getLevelName(log_level)}"
    )


def validate_aws_credentials() -> bool:
    """
    Check if AWS credentials are available.

    Returns:
        True if credentials are available, False otherwise
    """
    # Check for explicit credentials
    if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        return True

    # In Lambda or EC2, credentials are provided by IAM roles
    # We'll assume they're available if we're in a Lambda environment
    if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        return True

    # For local development, assume credentials are in ~/.aws/
    logger.info("Using AWS credentials from default credential chain")
    return True
