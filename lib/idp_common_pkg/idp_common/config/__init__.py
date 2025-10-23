# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import os
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError
import logging
from copy import deepcopy
from .configuration_manager import ConfigurationManager
from .models import (
    IDPConfig,
    ConfigurationRecord,
    ExtractionConfig,
    ClassificationConfig,
    AssessmentConfig,
    SummarizationConfig,
    OCRConfig,
    AgenticConfig,
    ImageConfig,
)
from .constants import (
    CONFIG_TYPE_SCHEMA,
    CONFIG_TYPE_DEFAULT,
    CONFIG_TYPE_CUSTOM,
    VALID_CONFIG_TYPES,
)

logger = logging.getLogger(__name__)


class ConfigurationReader:
    def __init__(self, table_name=None):
        """
        Initialize the configuration reader using the table name from environment variable or parameter

        Args:
            table_name: Optional override for configuration table name
        """
        # Use ConfigurationManager for all operations (with built-in migration)
        self.manager = ConfigurationManager(table_name)
        logger.info(f"Initialized ConfigurationReader with ConfigurationManager")

    def get_configuration(
        self, config_type: str, as_dict: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a configuration item from DynamoDB with automatic migration

        Args:
            config_type: The configuration type to retrieve ('Default' or 'Custom')
            as_dict: If True (default), return raw dictionary for backward compatibility

        Returns:
            Configuration dictionary if found (auto-migrated if needed), None otherwise
        """
        # ConfigurationManager now returns IDPConfig by default
        idp_config = self.manager.get_configuration(config_type)

        if idp_config is None:
            return None

        # Convert to dict if requested (for backward compatibility)
        if as_dict:
            config_dict = idp_config.model_dump(mode="python")
            # Add Configuration key back for backward compatibility
            config_dict["Configuration"] = config_type
            return config_dict

        return idp_config

    def deep_merge(
        self, default: Dict[str, Any], custom: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Recursively merge two dictionaries, with custom values taking precedence

        Args:
            default: The default configuration dictionary
            custom: The custom configuration dictionary

        Returns:
            Merged configuration dictionary
        """
        # Convert dicts to IDPConfig, merge, then convert back
        default_config = IDPConfig(**default)
        custom_config = IDPConfig(**custom)
        merged = self.manager.merge_configurations(default_config, custom_config)
        return merged.model_dump(mode="python")

    def get_merged_configuration(self, as_model: bool = False):
        """
        Get and merge Default and Custom configurations with automatic migration

        Args:
            as_model: If True, return IDPConfig Pydantic model. If False (default), return dict.

        Returns:
            Merged configuration as IDPConfig or dictionary (auto-migrated if needed)
        """
        try:
            # Get Default configuration (auto-migrated by ConfigurationManager)
            default_config = self.get_configuration("Default", as_dict=True)
            if not default_config:
                raise ValueError("Default configuration not found")

            # Get Custom configuration (auto-migrated by ConfigurationManager)
            custom_config = self.get_configuration("Custom", as_dict=True)

            # If no custom config exists, use default
            if not custom_config:
                logger.info("No Custom configuration found, using Default only")
                # Remove the 'Configuration' key as it's not part of the actual config
                default_config.pop("Configuration", None)
                merged_config = default_config
            else:
                # Remove the 'Configuration' key as it's not part of the actual config
                default_config.pop("Configuration", None)
                custom_config.pop("Configuration", None)

                # Merge configurations
                merged_config = self.deep_merge(default_config, custom_config)

            logger.info("Successfully merged configurations")

            # Return Pydantic model if requested
            if as_model:
                try:
                    return IDPConfig(**merged_config)
                except Exception as e:
                    logger.error(f"Failed to parse merged config as IDPConfig: {e}")
                    logger.info("Returning raw dictionary as fallback")
                    return merged_config

            return merged_config

        except Exception as e:
            logger.error(f"Error getting merged configuration: {str(e)}")
            raise


def get_config(table_name=None, as_model: bool = False):
    """
    Get the merged configuration using the environment variable for table name

    Args:
        table_name: Optional override for configuration table name
        as_model: If True, return IDPConfig Pydantic model. If False (default), return dict.

    Returns:
        Merged configuration as IDPConfig or dictionary
    """
    reader = ConfigurationReader(table_name)
    return reader.get_merged_configuration(as_model=as_model)
