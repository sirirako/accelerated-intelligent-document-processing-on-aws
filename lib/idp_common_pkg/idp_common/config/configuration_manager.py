# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import json
import os
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError
import logging
from copy import deepcopy
from .migration import migrate_legacy_to_schema, is_legacy_format
import json
import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)

class ConfigurationManager:
    def __init__(self, table_name=None):
        """
        Initialize the configuration reader using the table name from environment variable or parameter
        
        Args:
            table_name: Optional override for configuration table name
        """
        table_name = table_name or os.environ.get('CONFIGURATION_TABLE_NAME')
        if not table_name:
            raise ValueError("Configuration table name not provided. Either set CONFIGURATION_TABLE_NAME environment variable or provide table_name parameter.")
            
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)
        logger.info(f"Initialized ConfigurationReader with table: {table_name}")


    def get_configuration(self, config_type: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a configuration item from DynamoDB with automatic migration to JSON Schema

        Args:
            config_type: The configuration type to retrieve ('Schema', 'Default', or 'Custom')

        Returns:
            Configuration dictionary if found (auto-migrated if needed), None otherwise
        """
        try:
            response = self.table.get_item(
                Key={
                    'Configuration': config_type
                }
            )
            config = response.get('Item')

            # Auto-migrate legacy format to JSON Schema if needed
            if config and config.get('classes') and is_legacy_format(config['classes']):
                logger.info(f"Migrating {config_type} configuration to JSON Schema format")
                config['classes'] = migrate_legacy_to_schema(config['classes'])

                # Persist migrated configuration back to DynamoDB
                try:
                    config_copy = config.copy()
                    config_copy.pop('Configuration', None)
                    # For persistence, stringify only the values in the config
                    stringified = self._stringify_values(config_copy)
                    item_to_save = {
                        'Configuration': config_type
                    }
                    if isinstance(stringified, dict):
                        item_to_save.update(stringified)
                    self.table.put_item(Item=item_to_save)
                    logger.info(f"Persisted migrated {config_type} configuration")
                except Exception as e:
                    logger.warning(f"Failed to persist migrated {config_type} config: {e}")

            return config
        except ClientError as e:
            logger.error(f"Error retrieving configuration {config_type}: {str(e)}")
            raise

    """
    Recursively convert all values to strings
    """
    def _stringify_values(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._stringify_values(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._stringify_values(item) for item in obj]
        else:
            # Convert everything to string, except None values
            return str(obj) if obj is not None else None

    def _convert_floats_to_decimal(self, obj:  Any) -> Any:
        """
        Recursively convert float values to Decimal for DynamoDB compatibility
        """
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: self._convert_floats_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_floats_to_decimal(item) for item in obj]
        return obj

    def update_configuration(self, configuration_type: str, data: Dict[str, Any]) -> None:
        """
        Updates or creates a configuration item in DynamoDB with automatic migration to JSON Schema
        """
        try:
            # Auto-migrate legacy format to JSON Schema if needed
            if data.get('classes') and is_legacy_format(data['classes']):
                logger.info(f"Migrating {configuration_type} configuration to JSON Schema before saving")
                data['classes'] = migrate_legacy_to_schema(data['classes'])

            # Convert any float values to Decimal for DynamoDB compatibility
            converted_data = self._convert_floats_to_decimal(data)

            self.table.put_item(
                Item={
                    'Configuration': configuration_type,
                    **converted_data
                }
            )
        except ClientError as e:
            logger.error(f"Error updating configuration {configuration_type}: {str(e)}")
            raise

    def delete_configuration(self, configuration_type: str) -> None:
        """
        Deletes a configuration item from DynamoDB
        """
        try:
            self.table.delete_item(
                Key={
                    'Configuration': configuration_type
                }
            )
        except ClientError as e:
            logger.error(f"Error deleting configuration {configuration_type}: {str(e)}")
            raise


    def handle_update_custom_configuration(self, custom_config):
        """
        Handle the updateConfiguration GraphQL mutation with migration and saveAsDefault support
        Updates the Custom or Default configuration item in DynamoDB
        """
        try:
            # Handle empty configuration case
            if not custom_config:
                # For empty config, just store the Configuration key with no other attributes
                response = self.table.put_item(
                    Item={
                        'Configuration': 'Custom'
                    }
                )
                logger.info("Stored empty Custom configuration")
                return True

            # Parse the customConfig JSON string if it's a string
            if isinstance(custom_config, str):
                custom_config_obj = json.loads(custom_config)
            else:
                custom_config_obj = custom_config

            # Check if this should be saved as default
            save_as_default = custom_config_obj.pop('saveAsDefault', False)

            # Auto-migrate legacy format to JSON Schema if needed
            if custom_config_obj.get('classes') and is_legacy_format(custom_config_obj['classes']):
                logger.info("Migrating configuration to JSON Schema before saving")
                custom_config_obj['classes'] = migrate_legacy_to_schema(custom_config_obj['classes'])

            if save_as_default:
                # Get current default configuration
                default_item = self.get_configuration('Default')
                current_default = self.remove_configuration_key(default_item) if default_item else {}

                # Deep merge custom changes with current default
                new_default_config = self.deep_merge(current_default, custom_config_obj)

                # Convert to strings for DynamoDB
                stringified_default = self._stringify_values(new_default_config)

                # Save new default configuration
                self.table.put_item(
                    Item={
                        'Configuration': 'Default',
                        **stringified_default
                    }
                )

                # Clear custom configuration
                self.table.put_item(Item={'Configuration': 'Custom'})

                logger.info("Updated Default configuration and cleared Custom")
            else:
                # Normal custom config update
                stringified_config = self._stringify_values(custom_config_obj)

                self.table.put_item(
                    Item={
                        'Configuration': 'Custom',
                        **stringified_config
                    }
                )

                logger.info(f"Updated Custom configuration")

                # Send configuration update message if available
                self.send_configuration_update_message('Custom', custom_config_obj)

            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in customConfig: {str(e)}")
            raise Exception(f"Invalid configuration format: {str(e)}")
        except ClientError as e:
            logger.error(f"DynamoDB error in updateConfiguration: {str(e)}")
            raise Exception(f"Failed to update configuration: {str(e)}")
        except Exception as e:
            logger.error(f"Error in updateConfiguration: {str(e)}")
            raise e

    def remove_configuration_key(self, item):
        """
        Remove the 'Configuration' key from a DynamoDB item
        """
        if not item:
            return {}

        result = item.copy()
        result.pop('Configuration', None)
        return result

    def deep_merge(self, target, source):
        """
        Deep merge two dictionaries
        """
        result = target.copy()

        if not source:
            return result

        for key, value in source.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def send_configuration_update_message(self, configuration_key: str, configuration_data: dict):
        """
        Send a message to the ConfigurationQueue to notify pattern-specific processors
        about configuration updates.

        Args:
            configuration_key (str): The configuration key that was updated ('Custom' or 'Default')
            configuration_data (dict): The updated configuration data
        """
        try:
            configuration_queue_url = os.environ.get("CONFIGURATION_QUEUE_URL")
            if not configuration_queue_url:
                logger.debug("CONFIGURATION_QUEUE_URL environment variable not set, skipping notification")
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
            logger.warning(f"Failed to send configuration update message: {str(e)}")
            # Don't fail the entire operation if queue message fails

