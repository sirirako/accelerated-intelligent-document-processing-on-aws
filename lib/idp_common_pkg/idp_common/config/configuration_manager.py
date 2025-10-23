# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from __future__ import annotations

import boto3
import json
import os
from typing import Dict, Any, Optional, Union
from botocore.exceptions import ClientError
import logging
import datetime

from .models import IDPConfig, ConfigurationRecord
from .constants import (
    CONFIG_TYPE_SCHEMA,
    CONFIG_TYPE_DEFAULT,
    CONFIG_TYPE_CUSTOM,
    VALID_CONFIG_TYPES,
)

logger = logging.getLogger(__name__)


class ConfigurationManager:
    """
    Manages IDP configurations stored in DynamoDB.

    All operations use IDPConfig (Pydantic models) - no dict manipulation!
    ConfigurationRecord handles DynamoDB serialization internally.

    Example:
        manager = ConfigurationManager()

        # Get configuration (always returns IDPConfig)
        config = manager.get_configuration(CONFIG_TYPE_DEFAULT)

        # Save configuration
        manager.save_configuration(CONFIG_TYPE_CUSTOM, config)

        # Merge configurations
        merged = manager.merge_configurations(base_config, override_config)
    """

    def __init__(self, table_name: Optional[str] = None):
        """
        Initialize the configuration manager.

        Args:
            table_name: Optional override for configuration table name.
                       If not provided, uses CONFIGURATION_TABLE_NAME env var.

        Raises:
            ValueError: If table name cannot be determined
        """
        table_name = table_name or os.environ.get("CONFIGURATION_TABLE_NAME")
        if not table_name:
            raise ValueError(
                "Configuration table name not provided. Either set CONFIGURATION_TABLE_NAME "
                "environment variable or provide table_name parameter."
            )

        self.dynamodb = boto3.resource("dynamodb")
        self.table = self.dynamodb.Table(table_name)  # pyright: ignore[reportAttributeAccessIssue]
        self.table_name = table_name
        logger.info(f"ConfigurationManager initialized with table: {table_name}")

    def get_configuration(self, config_type: str) -> Optional[IDPConfig]:
        """
        Retrieve configuration from DynamoDB.

        This method:
        1. Reads the DynamoDB item
        2. Deserializes into ConfigurationRecord (auto-migrates legacy format)
        3. Checks if migration occurred and persists if needed
        4. Returns the IDPConfig model

        Args:
            config_type: Configuration type (Schema, Default, Custom)

        Returns:
            IDPConfig model or None if not found

        Raises:
            ClientError: If DynamoDB operation fails
        """
        try:
            record = self._read_record(config_type)
            if record is None:
                logger.info(f"Configuration not found: {config_type}")
                return None

            # Note: ConfigurationRecord.from_dynamodb_item() auto-migrates legacy format
            # We don't need to check for migration separately - it's already done
            # If we want to persist the migration, we can optionally do so here

            return record.config

        except ClientError as e:
            logger.error(f"Error retrieving configuration {config_type}: {e}")
            raise

    def save_configuration(
        self, config_type: str, config: Union[IDPConfig, Dict[str, Any]]
    ) -> None:
        """
        Save configuration to DynamoDB.

        This method:
        1. Converts dict to IDPConfig if needed
        2. Creates ConfigurationRecord
        3. Serializes to DynamoDB item
        4. Writes to DynamoDB
        5. Sends notification

        Args:
            config_type: Configuration type (Schema, Default, Custom)
            config: IDPConfig model or dict (will be converted to IDPConfig)

        Raises:
            ClientError: If DynamoDB operation fails
        """
        try:
            # Convert dict to IDPConfig if needed (for backward compatibility)
            if isinstance(config, dict):
                config = IDPConfig(**config)

            # Create record
            record = ConfigurationRecord(configuration_type=config_type, config=config)

            # Write to DynamoDB
            self._write_record(record)

            # Send notification
            self._send_update_notification(config_type, config)

        except ClientError as e:
            logger.error(f"Error saving configuration {config_type}: {e}")
            raise

    def delete_configuration(self, config_type: str) -> None:
        """
        Delete configuration from DynamoDB.

        Args:
            config_type: Configuration type to delete

        Raises:
            ClientError: If DynamoDB operation fails
        """
        try:
            self.table.delete_item(Key={"Configuration": config_type})
            logger.info(f"Deleted configuration: {config_type}")
        except ClientError as e:
            logger.error(f"Error deleting configuration {config_type}: {e}")
            raise

    def merge_configurations(
        self, base_config: IDPConfig, override_config: IDPConfig
    ) -> IDPConfig:
        """
        Deep merge two configurations.

        The override_config takes precedence over base_config for any overlapping fields.
        Nested dictionaries are merged recursively.

        Args:
            base_config: Base configuration
            override_config: Configuration to merge on top

        Returns:
            New IDPConfig with merged values

        Example:
            base = IDPConfig(extraction=ExtractionConfig(temperature=0.5))
            override = IDPConfig(extraction=ExtractionConfig(top_p=0.9))
            merged = manager.merge_configurations(base, override)
            # Result has both temperature=0.5 and top_p=0.9
        """
        # Use Pydantic's model_dump to get clean dicts
        # exclude_unset=True ensures we only merge fields that were explicitly set,
        # not default values that would override meaningful base config values
        base_dict = base_config.model_dump(mode="python")
        override_dict = override_config.model_dump(mode="python", exclude_unset=True)

        # Deep merge
        merged_dict = self._deep_merge_dicts(base_dict, override_dict)

        # Convert back to IDPConfig
        return IDPConfig(**merged_dict)

    def handle_update_custom_configuration(
        self, custom_config: Union[str, Dict[str, Any], IDPConfig]
    ) -> bool:
        """
        Handle the updateConfiguration GraphQL mutation.

        This method:
        1. Parses the input (JSON string, dict, or IDPConfig)
        2. Validates that config is not empty (prevents data loss)
        3. Checks for saveAsDefault flag
        4. Either updates Custom or merges into Default
        5. Sends notifications

        Args:
            custom_config: Configuration as JSON string, dict, or IDPConfig

        Returns:
            True on success

        Raises:
            Exception: If configuration update fails or is empty
        """
        # Reject completely empty configuration to prevent accidental data deletion
        if not custom_config:
            logger.error("Rejecting empty configuration update")
            raise Exception(
                "Cannot update with empty configuration. Frontend should not send empty diffs."
            )

        # Parse input
        if isinstance(custom_config, str):
            config_dict = json.loads(custom_config)
        elif isinstance(custom_config, IDPConfig):
            config_dict = custom_config.model_dump(mode="python")
        else:
            config_dict = custom_config

        # Additional validation: reject if parsed config is empty dict
        if isinstance(config_dict, dict) and len(config_dict) == 0:
            logger.error("Rejecting empty configuration dict")
            raise Exception(
                "Cannot update with empty configuration. Frontend should not send empty diffs."
            )

        # Extract special flags
        save_as_default = config_dict.pop("saveAsDefault", False)
        reset_to_default = config_dict.pop("resetToDefault", False)

        # Handle reset to default - delete Custom entirely
        # On next getConfiguration, the auto-copy logic will repopulate Custom from Default
        if reset_to_default:
            logger.info("Resetting Custom configuration by deleting it")
            self.delete_configuration(CONFIG_TYPE_CUSTOM)
            logger.info(
                "Custom configuration deleted, will be repopulated from Default on next read"
            )
            return True

        # Convert to IDPConfig
        config = IDPConfig(**config_dict)

        if save_as_default:
            # Save as Default: Replace Default with the received config (current Custom state)
            # Frontend sends the complete merged Custom config
            # This becomes the new baseline for all users
            self.save_configuration(CONFIG_TYPE_DEFAULT, config)

            # Delete Custom since it's now the same as Default
            self.delete_configuration(CONFIG_TYPE_CUSTOM)

            logger.info("Saved current Custom as new Default and cleared Custom")
        else:
            # Normal custom config update - merge diff into existing Custom
            # Data Flow: Frontend sends diff, we merge into existing Custom
            # Note: Custom should always exist (getConfiguration copies Default on first read)
            existing_custom = self.get_configuration(CONFIG_TYPE_CUSTOM)
            if not existing_custom or not existing_custom.model_dump(
                exclude_unset=True
            ):
                # Fallback: If Custom is somehow empty, use Default as base
                # This should rarely happen due to auto-copy in getConfiguration
                logger.warning(
                    "Custom config is empty during update, using Default as base"
                )
                existing_custom = (
                    self.get_configuration(CONFIG_TYPE_DEFAULT) or IDPConfig()
                )

            # Merge the diff into existing Custom
            # This preserves all fields in Custom that aren't in the diff
            merged_custom = self.merge_configurations(existing_custom, config)

            # Save updated Custom configuration
            self.save_configuration(CONFIG_TYPE_CUSTOM, merged_custom)
            logger.info("Updated Custom configuration by merging diff")

        return True

    # ===== Private Methods =====

    def _read_record(self, config_type: str) -> Optional[ConfigurationRecord]:
        """
        Read ConfigurationRecord from DynamoDB.

        Args:
            config_type: Configuration type to read

        Returns:
            ConfigurationRecord or None if not found
        """
        response = self.table.get_item(Key={"Configuration": config_type})
        item = response.get("Item")

        if item is None:
            return None

        return ConfigurationRecord.from_dynamodb_item(item)

    def _write_record(self, record: ConfigurationRecord) -> None:
        """
        Write ConfigurationRecord to DynamoDB.

        Args:
            record: ConfigurationRecord to write
        """
        item = record.to_dynamodb_item()
        self.table.put_item(Item=item)
        logger.info(f"Saved configuration: {record.configuration_type}")

    def _deep_merge_dicts(
        self, target: Dict[str, Any], source: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Deep merge two dictionaries.

        Empty values (None, empty strings) in source are skipped to prevent
        overriding meaningful default values with empty custom values.

        Args:
            target: Base dictionary
            source: Dictionary to merge on top

        Returns:
            Merged dictionary
        """
        result = target.copy()

        if not source:
            return result

        for key, value in source.items():
            # Skip None values and empty strings to preserve defaults
            if value is None or (isinstance(value, str) and value == ""):
                continue

            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge_dicts(result[key], value)
            else:
                result[key] = value

        return result

    def _send_update_notification(
        self, configuration_key: str, configuration_data: IDPConfig
    ) -> None:
        """
        Send a message to the ConfigurationQueue to notify pattern-specific processors
        about configuration updates.

        Args:
            configuration_key: The configuration key that was updated ('Custom' or 'Default')
            configuration_data: The updated configuration (IDPConfig model)
        """
        try:
            configuration_queue_url = os.environ.get("CONFIGURATION_QUEUE_URL")
            if not configuration_queue_url:
                logger.debug(
                    "CONFIGURATION_QUEUE_URL environment variable not set, skipping notification"
                )
                return

            sqs = boto3.client("sqs")

            # Create message payload
            message_body = {
                "eventType": "CONFIGURATION_UPDATED",
                "configurationKey": configuration_key,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "data": {
                    "configurationKey": configuration_key,
                },
            }

            # Send message to SQS
            response = sqs.send_message(
                QueueUrl=configuration_queue_url,
                MessageBody=json.dumps(message_body),
                MessageAttributes={
                    "eventType": {
                        "StringValue": "CONFIGURATION_UPDATED",
                        "DataType": "String",
                    },
                    "configurationKey": {
                        "StringValue": configuration_key,
                        "DataType": "String",
                    },
                },
            )

            logger.info(
                f"Configuration update message sent to queue. MessageId: {response.get('MessageId')}"
            )

        except Exception as e:
            logger.warning(f"Failed to send configuration update message: {e}")
            # Don't fail the entire operation if queue message fails
