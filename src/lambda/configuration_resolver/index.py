# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import boto3
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logging.getLogger('idp_common.bedrock.client').setLevel(os.environ.get("BEDROCK_LOG_LEVEL", "INFO"))
# Get LOG_LEVEL from environment variable with INFO as default

# Get the DynamoDB table name from the environment variable
CONFIGURATION_TABLE_NAME = os.environ['CONFIGURATION_TABLE_NAME']
STACK_NAME = os.environ.get('STACK_NAME', '')

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(CONFIGURATION_TABLE_NAME)
ssm_client = boto3.client('ssm')

def get_hitl_confidence_score_from_ssm():
    """
    Get the HITL confidence score from SSM Parameter Store.
    Returns the value as a string to match configuration format.
    """
    try:
        parameter_name = f"/{STACK_NAME}/hitl_confidence_threshold"
        response = ssm_client.get_parameter(Name=parameter_name)
        threshold_value = response['Parameter']['Value']
        logger.info(f"Retrieved HITL confidence score from SSM: {threshold_value}")
        return threshold_value
    except ClientError as e:
        logger.warning(f"Failed to retrieve HITL confidence score from SSM parameter {parameter_name}: {e}")
        # Return default value of 0.8 if SSM parameter is not found
        logger.info("Using default HITL confidence score: 0.8")
        return "0.8"
    except Exception as e:
        logger.warning(f"Error retrieving HITL confidence score from SSM: {e}")
        # Return default value if any other error occurs
        logger.info("Using default HITL confidence score: 0.8")
        return "0.8"

def update_hitl_confidence_score_in_ssm(value):
    """
    Update the HITL confidence score in SSM Parameter Store.
    """
    try:
        parameter_name = f"/{STACK_NAME}/hitl_confidence_threshold"
        ssm_client.put_parameter(
            Name=parameter_name,
            Value=str(value),
            Type='String',
            Overwrite=True,
            Description="HITL confidence threshold for Pattern-1 BDA processing"
        )
        logger.info(f"Updated HITL confidence score in SSM: {value}")
        return True
    except ClientError as e:
        logger.error(f"Failed to update HITL confidence score in SSM parameter {parameter_name}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error updating HITL confidence score in SSM: {e}")
        return False

def inject_ssm_values(config):
    """
    Inject SSM parameter values into the configuration.
    Currently handles hitl_confidence_score from assessment section.
    """
    if not config:
        return config
    
    # Make a deep copy to avoid modifying the original
    result = json.loads(json.dumps(config))
    
    # Inject HITL confidence score from SSM if assessment section exists
    if 'assessment' in result:
        hitl_score = get_hitl_confidence_score_from_ssm()
        result['assessment']['hitl_confidence_score'] = hitl_score
        logger.info(f"Injected HITL confidence score from SSM: {hitl_score}")
    
    return result

def extract_and_update_ssm_values(config):
    """
    Extract SSM-managed values from configuration and update SSM parameters.
    Returns the configuration with SSM values removed (they'll be injected on read).
    """
    if not config:
        return config
    
    # Make a deep copy to avoid modifying the original
    result = json.loads(json.dumps(config))
    
    # Handle HITL confidence score
    if 'assessment' in result and 'hitl_confidence_score' in result['assessment']:
        hitl_score = result['assessment']['hitl_confidence_score']
        # Update SSM parameter
        if update_hitl_confidence_score_in_ssm(hitl_score):
            logger.info(f"Successfully updated HITL confidence score in SSM: {hitl_score}")
        else:
            logger.error(f"Failed to update HITL confidence score in SSM: {hitl_score}")
        
        # Keep the value in configuration for consistency
        # (it will be overridden by SSM value on next read)
    
    return result

def get_configuration_item(config_type):
    """
    Retrieve a configuration item from DynamoDB
    """
    try:
        response = table.get_item(
            Key={
                'Configuration': config_type
            }
        )
        return response.get('Item')
    except ClientError as e:
        logger.error(f"Error retrieving {config_type} configuration: {str(e)}")
        raise Exception(f"Failed to retrieve {config_type} configuration")

def handler(event, context):
    """
    AWS Lambda handler for GraphQL operations related to configuration
    """
    logger.info(f"Event received: {json.dumps(event)}")
    
    # Extract the GraphQL operation type
    operation = event['info']['fieldName']
    
    if operation == 'getConfiguration':
        return handle_get_configuration()
    elif operation == 'updateConfiguration':
        args = event['arguments']
        custom_config = args.get('customConfig')
        return handle_update_configuration(custom_config)
    else:
        raise Exception(f"Unsupported operation: {operation}")

def handle_get_configuration():
    """
    Handle the getConfiguration GraphQL query
    Returns Schema, Default, and Custom configuration items with SSM values injected
    """
    try:
        # Get the Schema configuration
        schema_item = get_configuration_item('Schema')
        schema_config = schema_item.get('Schema', {}) if schema_item else {}
        
        # Get the Default configuration
        default_item = get_configuration_item('Default')
        default_config = remove_configuration_key(default_item) if default_item else {}
        
        # Get the Custom configuration (if it exists)
        custom_item = get_configuration_item('Custom')
        custom_config = remove_configuration_key(custom_item) if custom_item else {}
        
        # Inject SSM values into both default and custom configurations
        default_config_with_ssm = inject_ssm_values(default_config)
        custom_config_with_ssm = inject_ssm_values(custom_config) if custom_config else None
        
        # Return all configurations
        result = {
            'Schema': schema_config,
            'Default': default_config_with_ssm,
            'Custom': custom_config_with_ssm
        }
        
        logger.info(f"Returning configuration with SSM values injected")
        return result
        
    except Exception as e:
        logger.error(f"Error in getConfiguration: {str(e)}")
        raise e

def stringify_values(obj):
    """
    Recursively convert all values to strings
    """
    if isinstance(obj, dict):
        return {k: stringify_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [stringify_values(item) for item in obj]
    else:
        # Convert everything to string, except None values
        return str(obj) if obj is not None else None

def deep_merge(target, source):
    """
    Deep merge two dictionaries
    """
    result = target.copy()
    
    if not source:
        return result
    
    for key, value in source.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result

def handle_update_configuration(custom_config):
    """
    Handle the updateConfiguration GraphQL mutation
    Updates the Custom or Default configuration item in DynamoDB and SSM parameters
    """
    try:
        # Handle empty configuration case
        if not custom_config:
            # For empty config, just store the Configuration key with no other attributes
            response = table.put_item(
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
        
        # Extract and update SSM values before saving to DynamoDB
        processed_config = extract_and_update_ssm_values(custom_config_obj)
        
        if save_as_default:
            # Get current default configuration
            default_item = get_configuration_item('Default')
            current_default = remove_configuration_key(default_item) if default_item else {}
            
            # Merge custom changes with current default to create new complete default
            new_default_config = deep_merge(current_default, processed_config)
            
            # Convert to strings for DynamoDB
            stringified_default = stringify_values(new_default_config)
            
            # Save new default configuration
            table.put_item(
                Item={
                    'Configuration': 'Default',
                    **stringified_default
                }
            )
            
            # Clear custom configuration
            table.put_item(
                Item={
                    'Configuration': 'Custom'
                }
            )
            
            logger.info(f"Updated Default configuration and cleared Custom with SSM values processed")
        else:
            # Normal custom config update
            stringified_config = stringify_values(processed_config)
            
            table.put_item(
                Item={
                    'Configuration': 'Custom',
                    **stringified_config
                }
            )
            
            logger.info(f"Updated Custom configuration with SSM values processed")
        
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

def remove_configuration_key(item):
    """
    Remove the 'Configuration' key from a DynamoDB item
    """
    if not item:
        return {}
    
    result = item.copy()
    result.pop('Configuration', None)
    return result