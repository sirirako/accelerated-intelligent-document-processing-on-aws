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
                }
            }
        
        logger.info(f"Using BDA project ARN: {bda_project_arn}")
        
        # Initialize BDA service
        bda_service = BdaBlueprintService(dataAutomationProjectArn=bda_project_arn)
        
        # Execute the sync operation (reuses existing logic)
        result = bda_service.create_blueprints_from_custom_configuration()

        logger.info(f"BDA Service results: {result}")
        
        # Extract processed class names for response
        processed_classes = []
        sync_failed_classes = []
        sync_succeeded_classes = []
        success = True
        if isinstance(result, list):
            for item in result: 
                if item.get('status') == 'success':
                    sync_succeeded_classes.append(item.get('class'))
                else:
                    sync_failed_classes.append(f"Sync failed for {item.get('class')} with error: {item.get('error_message')}")
                    success = False
                
            
        
        logger.info(f"BDA/IDP sync completed successfully. Processed {len(sync_succeeded_classes)} classes")
        logger.info(f"BDA/IDP sync failed. Processed {len(sync_failed_classes)} classes")
        if len(sync_failed_classes) > 0:
            return {
                    "success": False,
                    "message": f"Synchronization failed for {len(sync_failed_classes)} document classes.",
                    "errorMessages" : sync_failed_classes
                }

        
        return {
            "success": success,
            "message": f"Successfully synchronized {len(processed_classes)} document classes with BDA blueprints"
        }
        
    except Exception as e:
        logger.error(f"BDA/IDP sync failed: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": {
                "type": "SYNC_ERROR", 
                "message": f"Sync operation failed: {str(e)}"
            }
        }