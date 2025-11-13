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
import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logging.getLogger("idp_common.bedrock.client").setLevel(
    os.environ.get("BEDROCK_LOG_LEVEL", "INFO")
)

# Model mapping between regions
MODEL_MAPPINGS = {
    "us.amazon.nova-lite-v1:0": "eu.amazon.nova-lite-v1:0",
    "us.amazon.nova-pro-v1:0": "eu.amazon.nova-pro-v1:0",
    "us.amazon.nova-premier-v1:0": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-3-haiku-20240307-v1:0": "eu.anthropic.claude-3-haiku-20240307-v1:0",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0": "eu.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0": "eu.anthropic.claude-3-7-sonnet-20250219-v1:0",
    "us.anthropic.claude-sonnet-4-20250514-v1:0": "eu.anthropic.claude-sonnet-4-20250514-v1:0",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-opus-4-20250514-v1:0": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-opus-4-1-20250805-v1:0": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
}


def get_current_region():
    """Get the current AWS region"""
    return boto3.Session().region_name


def is_eu_region(region):
    """Check if the region is an EU region"""
    return region.startswith("eu-")


def is_us_region(region):
    """Check if the region is a US region"""
    return region.startswith("us-")


def get_model_mapping(model_id, target_region_type):
    """Get the equivalent model for the target region type"""
    if target_region_type == "eu":
        return MODEL_MAPPINGS.get(model_id, model_id)
    elif target_region_type == "us":
        # Reverse mapping for US
        for us_model, eu_model in MODEL_MAPPINGS.items():
            if model_id == eu_model:
                return us_model
        return model_id
    return model_id


def swap_model_ids(data, region_type):
    """Swap model IDs to match the region type"""
    if isinstance(data, dict):
        swapped_data = {}
        for key, value in data.items():
            if (key == "model_id" or key == "model") and isinstance(value, str) and ("us." in value or "eu." in value):
                # This is a model_id field - check if it needs swapping
                if region_type == "eu" and value.startswith("us."):
                    new_model = get_model_mapping(value, "eu")
                    if new_model != value:
                        logger.info(f"Swapped US model {value} to EU model {new_model}")
                    swapped_data[key] = new_model
                elif region_type == "us" and value.startswith("eu."):
                    new_model = get_model_mapping(value, "us")
                    if new_model != value:
                        logger.info(f"Swapped EU model {value} to US model {new_model}")
                    swapped_data[key] = new_model
                else:
                    swapped_data[key] = value
            elif key == "model" and isinstance(value, str) and ("us." in value or "eu." in value):
                # Handle legacy 'model' field as well
                if region_type == "eu" and value.startswith("us."):
                    new_model = get_model_mapping(value, "eu")
                    if new_model != value:
                        logger.info(f"Swapped US model {value} to EU model {new_model}")
                    swapped_data[key] = new_model
                elif region_type == "us" and value.startswith("eu."):
                    new_model = get_model_mapping(value, "us")
                    if new_model != value:
                        logger.info(f"Swapped EU model {value} to US model {new_model}")
                    swapped_data[key] = new_model
                else:
                    swapped_data[key] = value
            else:
                swapped_data[key] = swap_model_ids(value, region_type)
        return swapped_data
    elif isinstance(data, list):
        return [swap_model_ids(item, region_type) for item in data]
    return data


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
        # Detect region type for model swapping
        current_region = get_current_region()
        region_type = (
            "eu"
            if is_eu_region(current_region)
            else "us"
            if is_us_region(current_region)
            else "other"
        )
        logger.info(f"Detected region: {current_region}, region type: {region_type}")

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
            # Apply model swapping to default config
            if region_type in ["us", "eu"]:
                default_dict = swap_model_ids(default_dict, region_type)
                logger.info(f"Applied model swapping for {region_type} region to Default config")
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
            # Apply model swapping to custom config
            if region_type in ["us", "eu"]:
                custom_dict = swap_model_ids(custom_dict, region_type)
                logger.info(f"Applied model swapping for {region_type} region to Custom config")
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
