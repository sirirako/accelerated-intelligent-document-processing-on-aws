# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from idp_common.config.configuration_manager import ConfigurationManager
import os
import json
import logging

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logging.getLogger("idp_common.bedrock.client").setLevel(
    os.environ.get("BEDROCK_LOG_LEVEL", "INFO")
)


def handler(event, context):
    """
    AWS Lambda handler for GraphQL operations related to configuration
    """
    logger.info(f"Event received: {json.dumps(event)}")

    # Extract the GraphQL operation type
    operation = event["info"]["fieldName"]

    # Initialize ConfigurationManager
    manager = ConfigurationManager()

    if operation == "getConfiguration":
        return handle_get_configuration(manager)
    elif operation == "updateConfiguration":
        args = event["arguments"]
        custom_config = args.get("customConfig")
        return manager.handle_update_custom_configuration(custom_config)
    else:
        raise Exception(f"Unsupported operation: {operation}")


def handle_get_configuration(manager):
    """
    Handle the getConfiguration GraphQL query
    Returns Schema, Default, and Custom configuration items with auto-migration support
    """
    try:
        # Get all configurations - migration happens automatically in get_configuration
        schema_item = manager.get_configuration("Schema")
        schema_config = manager.remove_configuration_key(schema_item) if schema_item else {}

        default_item = manager.get_configuration("Default")
        default_config = manager.remove_configuration_key(default_item) if default_item else {}

        custom_item = manager.get_configuration("Custom")
        custom_config = manager.remove_configuration_key(custom_item) if custom_item else {}

        # Return all configurations
        result = {
            "Schema": schema_config,
            "Default": default_config,
            "Custom": custom_config,
        }

        logger.info(f"Returning configuration")
        return result

    except Exception as e:
        logger.error(f"Error in getConfiguration: {str(e)}")
        raise e