# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from idp_common.config.configuration_manager import ConfigurationManager
from idp_common.config.models import SchemaConfig, IDPConfig
from idp_common.config.constants import (
    CONFIG_TYPE_SCHEMA,
    CONFIG_TYPE_DEFAULT,
    CONFIG_TYPE_CUSTOM,
)
from pydantic import ValidationError
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
    AWS Lambda handler for GraphQL operations related to configuration.

    Returns structured responses with success/error information:

    Success response:
    {
        "success": true,
        "Schema": {...},
        "Default": {...},
        "Custom": {...}
    }

    Error response:
    {
        "success": false,
        "error": {
            "type": "ValidationError" | "JSONDecodeError",
            "message": "...",
            "validationErrors": [...]  // if ValidationError
        }
    }
    """
    logger.info(f"Event received: {json.dumps(event)}")

    # Extract the GraphQL operation type
    operation = event["info"]["fieldName"]

    # Initialize ConfigurationManager
    manager = ConfigurationManager()

    try:
        if operation == "getConfiguration":
            return handle_get_configuration(manager)
        elif operation == "updateConfiguration":
            args = event["arguments"]
            custom_config = args.get("customConfig")
            success = manager.handle_update_custom_configuration(custom_config)
            return {
                "success": success,
                "message": "Configuration updated successfully"
                if success
                else "Configuration update failed",
            }
        else:
            raise Exception(f"Unsupported operation: {operation}")
    except ValidationError as e:
        # Pydantic validation error - return structured error for UI
        logger.error(f"Configuration validation error: {e}")

        # Build structured error response that UI can parse
        validation_errors = []
        for error in e.errors():
            field_path = " -> ".join(str(loc) for loc in error["loc"])
            validation_errors.append(
                {"field": field_path, "message": error["msg"], "type": error["type"]}
            )

        # Return error as data (not exception) so UI can handle it
        return {
            "success": False,
            "error": {
                "type": "ValidationError",
                "message": "Configuration validation failed",
                "validationErrors": validation_errors,
            },
        }

    except json.JSONDecodeError as e:
        # JSON parsing error - return structured error
        logger.error(f"JSON decode error: {e}")
        return {
            "success": False,
            "error": {
                "type": "JSONDecodeError",
                "message": f"Invalid JSON format: {str(e)}",
                "position": {
                    "line": e.lineno if hasattr(e, "lineno") else None,
                    "column": e.colno if hasattr(e, "colno") else None,
                },
            },
        }


def handle_get_configuration(manager):
    """
    Handle the getConfiguration GraphQL query
    Returns Schema, Default, and Custom configuration items with auto-migration support

    Data Flow:
    1. If Custom is empty on first read, copy Default → Custom
    2. Frontend only uses Custom for display and diffing
    3. Default is only used for "Reset to Default" operation

    New ConfigurationManager API returns IDPConfig directly - convert to dict for GraphQL
    """
    try:
        # Get all configurations - migration happens automatically in get_configuration
        # API returns SchemaConfig for Schema, IDPConfig for Default/Custom
        schema_config = manager.get_configuration(CONFIG_TYPE_SCHEMA)
        if schema_config:
            # Remove config_type discriminator before sending to frontend
            schema_dict = schema_config.model_dump(
                mode="python", exclude={"config_type"}
            )
        else:
            schema_dict = {}

        default_config = manager.get_configuration(CONFIG_TYPE_DEFAULT)
        if default_config and isinstance(default_config, IDPConfig):
            default_dict = default_config.model_dump(
                mode="python", exclude={"config_type"}
            )
        else:
            default_dict = {}

        custom_config = manager.get_configuration(CONFIG_TYPE_CUSTOM)

        # IMPORTANT: If Custom is empty on first read, copy Default → Custom
        # This ensures frontend always has a complete config to diff against
        if not custom_config or (
            isinstance(custom_config, IDPConfig)
            and not custom_config.model_dump(exclude_unset=True)
        ):
            logger.info("Custom config is empty, copying Default → Custom")
            if default_config and isinstance(default_config, IDPConfig):
                manager.save_configuration(CONFIG_TYPE_CUSTOM, default_config)
                custom_config = default_config
                logger.info("Copied Default to Custom on first read")
            else:
                logger.warning("Default config is also empty, using empty Custom")

        if custom_config and isinstance(custom_config, IDPConfig):
            custom_dict = custom_config.model_dump(
                mode="python", exclude={"config_type"}
            )
        else:
            custom_dict = {}

        # Return all configurations as dicts (GraphQL requires JSON-serializable)
        result = {
            "success": True,
            "Schema": schema_dict,
            "Default": default_dict,
            "Custom": custom_dict,
        }

        logger.info(f"Returning configuration")
        return result

    except Exception as e:
        logger.error(f"Error in getConfiguration: {str(e)}")
        raise e
