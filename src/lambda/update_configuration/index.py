# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
from typing import Any, Dict, Optional, Union

import boto3
import cfnresponse  # type: ignore[import-untyped]
import yaml
from botocore.exceptions import ClientError
from idp_common.config.configuration_manager import (
    ConfigurationManager,  # type: ignore[import-untyped]
)
from idp_common.config.models import (
    ConfigMetadata,
    ConfigurationRecord,
    IDPConfig,
    PricingConfig,
    SchemaConfig,
)
from pydantic import ValidationError

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logging.getLogger("idp_common.bedrock.client").setLevel(
    os.environ.get("BEDROCK_LOG_LEVEL", "INFO")
)

s3_client = boto3.client("s3")

def fetch_content_from_s3(s3_uri: str) -> Union[Dict[str, Any], str]:
    """
    Fetches content from S3 URI and parses as JSON or YAML if possible
    """
    try:
        # Parse S3 URI
        if not s3_uri.startswith("s3://"):
            raise ValueError(f"Invalid S3 URI: {s3_uri}")

        # Remove s3:// prefix and split bucket and key
        s3_path = s3_uri[5:]
        bucket, key = s3_path.split("/", 1)

        logger.info(f"Fetching content from S3: bucket={bucket}, key={key}")

        # Fetch object from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read().decode("utf-8")

        # Try to parse as JSON first, then YAML, return as string if both fail
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            try:
                return yaml.safe_load(content)
            except yaml.YAMLError:
                logger.warning(
                    f"Content from {s3_uri} is not valid JSON or YAML, returning as string"
                )
                return content

    except ClientError as e:
        logger.error(f"Error fetching content from S3 {s3_uri}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error processing S3 URI {s3_uri}: {str(e)}")
        raise


def resolve_content(content: Union[str, Dict[str, Any]]) -> Union[Dict[str, Any], str]:
    """
    Resolves content - if it's a string starting with s3://, fetch from S3
    Otherwise return as-is
    """
    if isinstance(content, str) and content.startswith("s3://"):
        return fetch_content_from_s3(content)
    return content

# Model mapping between regions
MODEL_MAPPINGS = {
    "us.amazon.nova-lite-v1:0": "eu.amazon.nova-lite-v1:0",
    "us.amazon.nova-pro-v1:0": "eu.amazon.nova-pro-v1:0",
    "us.amazon.nova-premier-v1:0": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.amazon.nova-2-lite-v1:0": "eu.amazon.nova-2-lite-v1:0",
    "us.anthropic.claude-3-haiku-20240307-v1:0": "eu.anthropic.claude-3-haiku-20240307-v1:0",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0": "eu.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0": "eu.anthropic.claude-3-7-sonnet-20250219-v1:0",
    "us.anthropic.claude-sonnet-4-20250514-v1:0": "eu.anthropic.claude-sonnet-4-20250514-v1:0",
    "us.anthropic.claude-sonnet-4-20250514-v1:0:1m": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0:1m": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0:1m",
    "us.anthropic.claude-opus-4-20250514-v1:0": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-opus-4-1-20250805-v1:0": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-opus-4-5-20251101-v1:0": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
}

def get_current_region() -> str:
    """Get the current AWS region"""
    region = boto3.Session().region_name
    if region is None:
        # Fallback to environment variable or default
        region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
    return region


def is_eu_region(region: str) -> bool:
    """Check if the region is an EU region"""
    return region.startswith("eu-")


def is_us_region(region: str) -> bool:
    """Check if the region is a US region"""
    return region.startswith("us-")


def get_model_mapping(model_id: str, target_region_type: str) -> str:
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


def filter_models_by_region(data: Any, region_type: str) -> Any:
    """Filter out models that don't match the region type"""
    if isinstance(data, dict):
        filtered_data = {}
        for key, value in data.items():
            if isinstance(value, list) and any(
                isinstance(item, str) and ("us." in item or "eu." in item)
                for item in value
            ):
                # This is a model list - filter it
                filtered_list = []
                for item in value:
                    if isinstance(item, str):
                        # Include models that match the region type or are region-agnostic
                        if region_type == "us":
                            # Include US models and non-region-specific models, exclude EU models
                            if item.startswith("us.") or (not item.startswith("eu.") and not item.startswith("us.")):
                                filtered_list.append(item)
                        elif region_type == "eu":
                            # Include EU models and non-region-specific models, exclude US models
                            if item.startswith("eu.") or (not item.startswith("eu.") and not item.startswith("us.")):
                                filtered_list.append(item)
                        else:
                            # For other regions, include all models
                            filtered_list.append(item)
                    else:
                        filtered_list.append(item)
                filtered_data[key] = filtered_list
            else:
                filtered_data[key] = filter_models_by_region(value, region_type)
        return filtered_data
    elif isinstance(data, list):
        return [filter_models_by_region(item, region_type) for item in data]
    return data


def swap_model_ids(data: Any, region_type: str) -> Any:
    """Swap model IDs to match the region type"""
    if isinstance(data, dict):
        swapped_data = {}
        for key, value in data.items():
            if isinstance(value, str) and ("us." in value or "eu." in value):
                # This is a model ID - check if it needs swapping
                if region_type == "us" and value.startswith("eu."):
                    new_model = get_model_mapping(value, "us")
                    if new_model != value:
                        logger.info(f"Swapped EU model {value} to US model {new_model}")
                    swapped_data[key] = new_model
                elif region_type == "eu" and value.startswith("us."):
                    new_model = get_model_mapping(value, "eu")
                    if new_model != value:
                        logger.info(f"Swapped US model {value} to EU model {new_model}")
                    swapped_data[key] = new_model
                else:
                    swapped_data[key] = value
            else:
                swapped_data[key] = swap_model_ids(value, region_type)
        return swapped_data
    elif isinstance(data, list):
        return [swap_model_ids(item, region_type) for item in data]
    return data



def backup_existing_records(config_bucket: str, table_name: str) -> Optional[str]:
    """Backup existing configuration records to S3 before table recreation."""
    import json
    from datetime import datetime

    import boto3
    
    try:
        logger.info(f"Starting backup of existing records from table: {table_name}")
        dynamodb = boto3.resource("dynamodb")
        s3_client = boto3.client("s3")
        table = dynamodb.Table(table_name)
        
        # Scan existing records
        logger.info("Scanning DynamoDB table for existing records...")
        response = table.scan()
        items = response.get("Items", [])
        
        if not items:
            logger.info("No existing records found to backup")
            return None
            
        logger.info(f"Found {len(items)} records to backup")
        for item in items:
            config_type = item.get("Configuration", "Unknown")
            logger.debug(f"Backing up record: {config_type}")
            
        # Create backup with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_key = f"config_backup/backup_{timestamp}.json"
        
        # Save to S3
        backup_data = {
            "timestamp": timestamp,
            "table_name": table_name,
            "record_count": len(items),
            "records": items
        }
        
        logger.info(f"Uploading backup to S3: s3://{config_bucket}/{backup_key}")
        s3_client.put_object(
            Bucket=config_bucket,
            Key=backup_key,
            Body=json.dumps(backup_data, default=str),
            ContentType="application/json"
        )
        
        logger.info(f"Successfully backed up {len(items)} records to s3://{config_bucket}/{backup_key}")
        return backup_key
        
    except Exception as e:
        logger.error(f"Failed to backup existing records from {table_name}: {e}")
        return None


def restore_from_backup(config_bucket: str, manager: ConfigurationManager) -> bool:
    """Restore configuration records from S3 backup with new composite key format."""
    import json
    from datetime import datetime

    import boto3
    
    try:
        logger.info(f"Starting restore from backup in bucket: {config_bucket}")
        s3_client = boto3.client("s3")
        
        # Find latest backup
        logger.info("Searching for latest backup file...")
        response = s3_client.list_objects_v2(
            Bucket=config_bucket,
            Prefix="config_backup/backup_"
        )
        
        if "Contents" not in response:
            logger.info("No backup found to restore")
            return False
            
        # Get latest backup
        latest_backup = max(response["Contents"], key=lambda x: x["LastModified"])
        backup_key = latest_backup["Key"]
        logger.info(f"Found latest backup: s3://{config_bucket}/{backup_key}")
        
        # Read backup data
        logger.info("Reading backup data from S3...")
        response = s3_client.get_object(Bucket=config_bucket, Key=backup_key)
        backup_data = json.loads(response["Body"].read().decode("utf-8"))
        
        records = backup_data.get("records", [])
        if not records:
            logger.info("No records in backup to restore")
            return False
            
        logger.info(f"Backup contains {len(records)} records from {backup_data.get('timestamp', 'unknown time')}")
        
        # Restore records with new composite key format
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Collect Default and Custom records for comparison
        default_record = None
        custom_record = None
        other_records = []
        
        logger.info("Analyzing backup records...")
        for record in records:
            config_type = record.get("Configuration")
            logger.debug(f"Processing record type: {config_type}")
            if config_type == "Default":
                default_record = record
                logger.info("Found Default configuration in backup")
            elif config_type == "Custom":
                custom_record = record
                logger.info("Found Custom configuration in backup")
            else:
                other_records.append(record)
                logger.debug(f"Found other record type: {config_type}")
        
        # Handle Default and Custom with deduplication logic
        if default_record and custom_record:
            logger.info("Both Default and Custom found - comparing configurations...")
            # Compare configurations using the same logic as sync_custom_with_new_default
            from idp_common.config.merge_utils import get_diff_dict
            
            default_config = {k: v for k, v in default_record.items() 
                             if k not in ("Configuration", "IsActive", "CreatedAt", "UpdatedAt", "Description")}
            custom_config = {k: v for k, v in custom_record.items() 
                            if k not in ("Configuration", "IsActive", "CreatedAt", "UpdatedAt", "Description")}
            
            # Check if there are any differences between Default and Custom
            differences = get_diff_dict(default_config, custom_config)
            
            if not differences:
                # Identical - only create v0 (active)
                logger.info("Default and Custom are identical - creating single v0 version")
                config_data = {k: v for k, v in default_record.items() if k != "Configuration"}
                config_data["config_type"] = "Config"
                config = IDPConfig(**config_data)
                
                manager.save_configuration("Config", config, version="v0", description="System default configuration (v0)")
                manager.activate_version("v0")
                logger.info("Successfully restored as Config/v0 (active)")
            else:
                # Different - create both v0 (inactive) and v1 (active)
                logger.info("Default and Custom are different - creating v0 and v1 versions")
                
                # v0 (Default)
                config_data = {k: v for k, v in default_record.items() if k != "Configuration"}
                config_data["config_type"] = "Config"
                config = IDPConfig(**config_data)
                manager.save_configuration("Config", config, version="v0", description="System default configuration (v0)")
                logger.info("Created Config/v0 from Default")
                
                # v1 (Custom) - active
                config_data = {k: v for k, v in custom_record.items() if k != "Configuration"}
                config_data["config_type"] = "Config"
                config = IDPConfig(**config_data)
                manager.save_configuration("Config", config, version="v1", description="User customized configuration (v1)")
                manager.activate_version("v1")
                logger.info("Created Config/v1 from Custom (active)")
                
        elif default_record:
            # Only Default exists - create v0 (active)
            logger.info("Only Default found - creating v0 version")
            config_data = {k: v for k, v in default_record.items() if k != "Configuration"}
            config_data["config_type"] = "Config"
            config = IDPConfig(**config_data)
            
            manager.save_configuration("Config", config, version="v0", description="System default configuration (v0)")
            manager.activate_version("v0")
            logger.info("Successfully restored Default as Config/v0 (active)")
            
        elif custom_record:
            # Only Custom exists - create v1 (active)
            logger.info("Only Custom found - creating v1 version")
            config_data = {k: v for k, v in custom_record.items() if k != "Configuration"}
            config_data["config_type"] = "Config"
            config = IDPConfig(**config_data)
            
            manager.save_configuration("Config", config, version="v1", description="User customized configuration (v1)")
            manager.activate_version("v1")
            logger.info("Successfully restored Custom as Config/v1 (active)")
        
        # Handle other record types (Schema, Pricing)
        logger.info(f"Processing {len(other_records)} other record types...")
        for record in other_records:
            config_type = record.get("Configuration")
            logger.debug(f"Restoring {config_type} configuration")
            
            if config_type == "Schema":
                # Schema → Schema/"" 
                config_data = {k: v for k, v in record.items() if k != "Configuration"}
                config_data["config_type"] = "Schema"
                config = SchemaConfig(**config_data)
                
                manager.save_configuration("Schema", config)
                logger.info("Restored Schema configuration")
                
            elif config_type in ("DefaultPricing", "CustomPricing"):
                # Pricing → Pricing/""
                config_data = {k: v for k, v in record.items() if k != "Configuration"}
                config_data["config_type"] = config_type
                config = PricingConfig(**config_data)
                
                manager.save_configuration("Pricing", config)
                logger.info(f"Restored {config_type} as Pricing configuration")
        
        logger.info(f"Successfully restored {len(records)} records from backup with migration to versioned format")
        return True
        
    except Exception as e:
        logger.error(f"Failed to restore from backup: {e}")
        return False


def generate_physical_id(stack_id: str, logical_id: str) -> str:
    """
    Generates a consistent physical ID for the custom resource
    """
    return f"{stack_id}/{logical_id}/configuration"


def handler(event: Dict[str, Any], context: Any) -> None:
    """
    Handles CloudFormation Custom Resource events for configuration management
    """
    logger.info(f"Received event: {json.dumps(event)}")

    try:
        request_type = event["RequestType"]
        properties = event["ResourceProperties"]
        stack_id = event["StackId"]
        logical_id = event["LogicalResourceId"]

        # Generate physical ID
        physical_id = generate_physical_id(stack_id, logical_id)

        # Remove ServiceToken from properties as it's not needed in DynamoDB
        properties.pop("ServiceToken", None)

        # Detect region type
        current_region = get_current_region()
        region_type = (
            "eu"
            if is_eu_region(current_region)
            else "us"
            if is_us_region(current_region)
            else "other"
        )
        logger.info(f"Detected region: {current_region}, region type: {region_type}")

        # Initialize ConfigurationManager for all database operations
        manager = ConfigurationManager()

        if request_type in ["Create", "Update"]:
            # BACKUP PHASE: Save existing data before potential table recreation
            # During CloudFormation updates, the DynamoDB table may be recreated (e.g., if table
            # properties change, encryption settings change, or resource replacement is triggered).
            # Table recreation destroys all data, so we backup to S3 first.
            config_bucket = properties.get("ConfigurationBucket")
            if config_bucket and request_type == "Update":
                backup_key = backup_existing_records(config_bucket, manager.table_name)
                if backup_key:
                    logger.info(f"Configuration backup created: {backup_key}")
            
            # CLOUDFORMATION PROCESSING PHASE: 
            # At this point, CloudFormation may recreate the DynamoDB table if needed.
            # The ConfigurationManager will connect to the table (existing or newly created).
            # If table was recreated, it will be empty and we need to restore data.
            
            # RESTORE PHASE: Reload data from backup if table was recreated
            # The restore function detects if the table is empty and restores from S3 backup.
            # During restore, old Default/Custom format is converted to new v0/v1 versioned format.
            restored_from_backup = False
            if config_bucket:
                restored_from_backup = restore_from_backup(config_bucket, manager)
                if restored_from_backup:
                    logger.info("Successfully restored configurations from backup")
            
            # Handle migration and versioning only if NOT restored from backup
            if not restored_from_backup:
                if request_type == "Create":
                    # New stack - create v0 from Default configuration
                    logger.info("New stack deployment - will create v0 from Default configuration")
                    
                elif request_type == "Update":
                    # Existing stack - migrate Default/Custom to v0/v1 versioning
                    try:
                        # Check for existing Default and Custom configurations using old format
                        # During migration, we need to read the old single-key records directly
                        old_default = None
                        old_custom = None
                        
                        try:
                            # Try to read old Default record directly
                            response = manager.table.get_item(Key={"Configuration": "Default"})
                            if "Item" in response:
                                old_default_data = {k: v for k, v in response["Item"].items() if k != "Configuration"}
                                old_default_data["config_type"] = "Config"
                                old_default = IDPConfig(**old_default_data)
                                logger.info("Found existing Default configuration")
                        except Exception as e:
                            logger.debug(f"No Default configuration found: {e}")
                        
                        try:
                            # Try to read old Custom record directly  
                            response = manager.table.get_item(Key={"Configuration": "Custom"})
                            if "Item" in response:
                                old_custom_data = {k: v for k, v in response["Item"].items() if k != "Configuration"}
                                old_custom_data["config_type"] = "Config"
                                old_custom = IDPConfig(**old_custom_data)
                                logger.info("Found existing Custom configuration")
                        except Exception as e:
                            logger.debug(f"No Custom configuration found: {e}")
                        
                        if old_default:
                            if old_custom:
                                # Both exist - compare using same logic as configuration manager
                                from idp_common.config.merge_utils import get_diff_dict
                                
                                default_data = old_default.model_dump(mode="python", exclude={"config_type"})
                                custom_data = old_custom.model_dump(mode="python", exclude={"config_type"})
                                
                                # Check if there are any differences between Default and Custom
                                differences = get_diff_dict(default_data, custom_data)
                                
                                if not differences:
                                    # Identical - create only v0 (active)
                                    manager.save_configuration("Config", old_default, version="v0", description="System default configuration (v0)")
                                    manager.activate_version("v0")
                                    logger.info("Default and Custom are identical - created v0 as active")
                                else:
                                    # Different - create both v0 and v1
                                    manager.save_configuration("Config", old_default, version="v0", description="System default configuration (v0)")
                                    manager.save_configuration("Config", old_custom, version="v1", description="User customized configuration (v1)")
                                    manager.activate_version("v1")
                                    logger.info("Default and Custom are different - created v0 and v1 (v1 active)")
                            else:
                                # Only Default exists - create v0 as active
                                manager.save_configuration("Config", old_default, version="v0", description="System default configuration (v0)")
                                manager.activate_version("v0")
                                logger.info("Only Default exists - created v0 as active")
                        
                    except Exception as e:
                        logger.warning(f"Failed to migrate existing configurations: {e}")
            else:
                logger.info("Skipping migration logic - configurations already restored from backup")
            
            # Collect all configurations to process
            configurations = {}
            
            # Process Schema configuration
            if "Schema" in properties:
                resolved_schema = resolve_content(properties["Schema"])
                # Filter models based on region
                if region_type in ["us", "eu"]:
                    resolved_schema = filter_models_by_region(resolved_schema, region_type)
                configurations["Schema"] = {"Schema": resolved_schema}

            # Process Default configuration
            if "Default" in properties:
                resolved_default = resolve_content(properties["Default"])
                # Apply custom model ARNs if provided
                if isinstance(resolved_default, dict):
                    # Replace classification model if CustomClassificationModelARN is provided and not empty
                    if (
                        "CustomClassificationModelARN" in properties
                        and properties["CustomClassificationModelARN"].strip()
                    ):
                        if "classification" in resolved_default:
                            resolved_default["classification"]["model"] = properties[
                                "CustomClassificationModelARN"
                            ]
                            logger.info(
                                f"Updated classification model to: {properties['CustomClassificationModelARN']}"
                            )

                    # Replace extraction model if CustomExtractionModelARN is provided and not empty
                    if (
                        "CustomExtractionModelARN" in properties
                        and properties["CustomExtractionModelARN"].strip()
                    ):
                        if "extraction" in resolved_default:
                            resolved_default["extraction"]["model"] = properties[
                                "CustomExtractionModelARN"
                            ]
                            logger.info(
                                f"Updated extraction model to: {properties['CustomExtractionModelARN']}"
                            )

                configurations["Default"] = resolved_default

            # Process Custom configuration if provided and not empty
            if (
                "Custom" in properties
                and properties["Custom"].get("Info") != "Custom inference settings"
            ):
                resolved_custom = resolve_content(properties["Custom"])
                # Remove legacy pricing field if present (now stored separately as DefaultPricing)
                if isinstance(resolved_custom, dict):
                    resolved_custom.pop("pricing", None)
                configurations["Custom"] = resolved_custom

            # Process DefaultPricing configuration if provided
            if "DefaultPricing" in properties:
                resolved_pricing = resolve_content(properties["DefaultPricing"])
                # Pricing doesn't need region-specific filtering or swapping
                # as it includes all regions (US, EU, Global) in one file
                configurations["DefaultPricing"] = resolved_pricing
                logger.info("Loaded DefaultPricing configuration")

            # Apply region-specific model swapping to all configurations at once
            if region_type in ["us", "eu"] and configurations:
                configurations = swap_model_ids(configurations, region_type)
                logger.info(f"Applied model swapping for {region_type} region to all configurations")

            # Save all configurations
            for config_name, config_data in configurations.items():
                if config_name == "Default" and request_type == "Create":
                    # For new stacks, save Default as v0 with versioning
                    manager.save_configuration("Config", config_data, version="v0", description="System default configuration (v0)")
                    manager.activate_version("v0")
                    logger.info("Created v0 from Default configuration for new stack")
                else:
                    # Save other configurations (Schema, DefaultPricing) normally
                    manager.save_configuration(config_name, config_data)
                    logger.info(f"Updated {config_name} configuration")

            cfnresponse.send(
                event,
                context,
                cfnresponse.SUCCESS,
                {"Message": f"Successfully {request_type.lower()}d configurations"},
                physical_id,
            )

        elif request_type == "Delete":
            # Do nothing on delete - preserve any existing configuration otherwise
            # data is lost during custom resource replacement (cleanup step), e.g.
            # if nested stack name or resource name is changed
            logger.info("Delete request received - preserving configuration (no-op)")
            cfnresponse.send(
                event,
                context,
                cfnresponse.SUCCESS,
                {"Message": "Success (delete = no-op)"},
                physical_id,
            )

    except ValidationError as e:
        # Pydantic validation error - format detailed error message
        logger.error(f"Configuration validation error: {e}")

        # Build detailed error message
        error_messages = []
        for error in e.errors():
            field_path = " -> ".join(str(loc) for loc in error["loc"])
            error_messages.append(
                f"{field_path}: {error['msg']} (type: {error['type']})"
            )

        detailed_error = "Configuration validation failed:\n" + "\n".join(
            error_messages
        )

        # Still need to send physical ID even on failure
        physical_id = generate_physical_id(event["StackId"], event["LogicalResourceId"])
        cfnresponse.send(
            event,
            context,
            cfnresponse.FAILED,
            {
                "Error": "ValidationError",
                "Message": detailed_error,
                "ValidationErrors": [
                    {
                        "field": " -> ".join(str(loc) for loc in err["loc"]),
                        "message": err["msg"],
                        "type": err["type"],
                    }
                    for err in e.errors()
                ],
            },
            physical_id,
            reason=detailed_error[:256],  # CloudFormation has 256 char limit for reason
        )

    except json.JSONDecodeError as e:
        # JSON parsing error
        logger.error(f"JSON decode error: {e}")
        error_message = (
            f"Invalid JSON format at line {e.lineno}, column {e.colno}: {str(e)}"
            if hasattr(e, "lineno")
            else f"Invalid JSON format: {str(e)}"
        )

        physical_id = generate_physical_id(event["StackId"], event["LogicalResourceId"])
        cfnresponse.send(
            event,
            context,
            cfnresponse.FAILED,
            {"Error": "JSONDecodeError", "Message": error_message},
            physical_id,
            reason=error_message[:256],
        )

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        # Still need to send physical ID even on failure
        physical_id = generate_physical_id(event["StackId"], event["LogicalResourceId"])
        cfnresponse.send(
            event,
            context,
            cfnresponse.FAILED,
            {"Error": str(e)},
            physical_id,
            reason=str(e)[:256],
        )
