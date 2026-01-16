# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
from typing import Dict, Any

from idp_common.bda.bda_blueprint_service import BdaBlueprintService  # type: ignore[import-untyped]

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logging.getLogger('idp_common.bedrock.client').setLevel(os.environ.get("BEDROCK_LOG_LEVEL", "INFO"))



def handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Synchronous BDA/IDP sync resolver.
    Directly calls BdaBlueprintService to sync BDA blueprints with IDP classes.
    """
    try:
        logger.info("Starting synchronous BDA/IDP sync")
        logger.info(f"Event: {json.dumps(event, default=str)}")
        
        # Get BDA project ARN from environment
        bda_project_arn = os.environ.get('BDA_PROJECT_ARN')
        if not bda_project_arn:
            logger.error("BDA project ARN not configured")
            return {
                "success": False,
                "error": {
                    "type": "CONFIGURATION_ERROR",
                    "message": "BDA project ARN not configured"
                },
                "processedClasses": []
            }
        
        logger.info(f"Using BDA project ARN: {bda_project_arn}")
        
        # Initialize BDA service
        bda_service = BdaBlueprintService(dataAutomationProjectArn=bda_project_arn)
        
        # Execute the sync operation (reuses existing logic)
        result = bda_service.create_blueprints_from_custom_configuration()

        logger.info(f"BDA Service results: {result}")
        
        # Extract processed class names for response
        sync_failed_classes = []
        sync_succeeded_classes = []
        
        if isinstance(result, list):
            for item in result: 
                if item.get('status') == 'success':
                    sync_succeeded_classes.append(item.get('class'))
                else:
                    class_name = item.get('class', 'Unknown')
                    error_msg = item.get('error_message', 'Unknown error')
                    sync_failed_classes.append(class_name)
        
        logger.info(f"BDA/IDP sync completed. Succeeded: {len(sync_succeeded_classes)}, Failed: {len(sync_failed_classes)}")
        
        # Handle different scenarios
        if len(sync_succeeded_classes) == 0 and len(sync_failed_classes) > 0:
            # Complete failure
            return {
                "success": False,
                "message": f"Synchronization failed for all {len(sync_failed_classes)} document classes.",
                "processedClasses": [],
                "error": {
                    "type": "SYNC_ERROR", 
                    "message": f"Failed to sync classes: {', '.join(sync_failed_classes)}"
                }
            }
        elif len(sync_failed_classes) > 0:
            # Partial failure
            return {
                "success": True,  # Partial success
                "message": f"Successfully synchronized {len(sync_succeeded_classes)} document classes. Failed to sync {len(sync_failed_classes)} classes: {', '.join(sync_failed_classes)}",
                "processedClasses": sync_succeeded_classes,
                "error": {
                    "type": "PARTIAL_SYNC_ERROR",
                    "message": f"Failed to sync classes: {', '.join(sync_failed_classes)}"
                }
            }
        else:
            # Complete success
            return {
                "success": True,
                "message": f"Successfully synchronized {len(sync_succeeded_classes)} document classes with BDA blueprints",
                "processedClasses": sync_succeeded_classes
            }
        
    except Exception as e:
        logger.error(f"BDA/IDP sync failed: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": {
                "type": "SYNC_ERROR", 
                "message": f"Sync operation failed: {str(e)}"
            },
            "processedClasses": []
        }