# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
OCR function that processes PDFs and extracts text using AWS Textract.
Uses the idp_common.ocr package for OCR functionality.
"""

import json
import logging
import os
import time

from idp_common import get_config, ocr
from idp_common.models import Document, Status
from idp_common.docs_service import create_document_service

# Configuration will be loaded in handler function

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logging.getLogger('idp_common.bedrock.client').setLevel(os.environ.get("BEDROCK_LOG_LEVEL", "INFO"))

# Initialize settings
region = os.environ['AWS_REGION']
METRIC_NAMESPACE = os.environ.get('METRIC_NAMESPACE')
MAX_WORKERS = int(os.environ.get('MAX_WORKERS', 20))

def handler(event, context): 
    """
    Lambda handler for OCR processing.
    """       
    logger.info(f"Event: {json.dumps(event)}")
    
    # Get document from event
    document = Document.from_dict(event["document"])
    
    # Update document status to OCR and update in AppSync
    document.status = Status.OCR
    document.workflow_execution_arn = event.get("execution_arn")
    document_service = create_document_service()
    logger.info(f"Updating document status to {document.status}")
    document_service.update_document(document)
    
    t0 = time.time()
    
    # Load configuration and initialize the OCR service
    config = get_config()
    ocr_config = config.get("ocr", {})
    features = [feature['name'] for feature in ocr_config.get("features", [])]
    image_config = ocr_config.get("image", {})
    
    # Extract resize configuration if present
    resize_config = None
    if image_config:
        target_width = image_config.get("target_width")
        target_height = image_config.get("target_height")
        if target_width is not None and target_height is not None:
            target_width = int(target_width)
            target_height = int(target_height)
            resize_config = {
                "target_width": target_width,
                "target_height": target_height
            }
            logger.info(f"Image resize configuration found: {resize_config}")
        else:
            logger.info("No image resize configuration found in ocr.image config")
    else:
        logger.info("No image configuration found in ocr config")

    # Extract preprocessing configuration if present
    preprocessing_config = None
    if image_config:
        preprocessing_value = image_config.get("preprocessing")
        # Handle both boolean and string values
        if preprocessing_value is True or (isinstance(preprocessing_value, str) and preprocessing_value.lower() == 'true'):
            preprocessing_config = {"enabled": True}
            logger.info("Image preprocessing (adaptive binarization) enabled")
        else:
            logger.info("Image preprocessing disabled")
    else:
        logger.info("Image preprocessing disabled")

    # Extract Bedrock configuration if present
    bedrock_config = None
    # Check if bedrock configuration exists directly in ocr_config
    if ocr_config.get("model_id") and ocr_config.get("system_prompt") and ocr_config.get("task_prompt"):
        bedrock_config = {
            "model_id": ocr_config.get("model_id"),
            "system_prompt": ocr_config.get("system_prompt"),
            "task_prompt": ocr_config.get("task_prompt"),
        }
        logger.info(f"Bedrock OCR configuration found: model_id={bedrock_config['model_id']}")
    else:
        logger.info("No Bedrock configuration found in ocr config (model_id, system_prompt, or task_prompt missing)")
    
    # Get OCR backend from config (default to "textract" if not specified)
    backend = ocr_config.get("backend", "textract")
    
    logger.info(f"Initializing OCR with backend: {backend}, MAX_WORKERS: {MAX_WORKERS}, enhanced_features: {features}")
    service = ocr.OcrService(
        region=region,
        max_workers=MAX_WORKERS,
        enhanced_features=features,
        resize_config=resize_config,
        bedrock_config=bedrock_config,
        backend=backend,
        preprocessing_config=preprocessing_config,
    )
    
    # Process the document - the service will read the PDF content directly
    document = service.process_document(document)
    
    # Check if document processing failed
    if document.status == Status.FAILED:
        error_message = f"OCR processing failed for document {document.id}"
        logger.error(error_message)
        # Update status in AppSync before raising exception
        document_service.update_document(document)
        raise Exception(error_message)
    
    t1 = time.time()
    logger.info(f"Total OCR processing time: {t1-t0:.2f} seconds")
    
    # Prepare output with automatic compression if needed
    working_bucket = os.environ.get('WORKING_BUCKET')
    response = {
        "document": document.serialize_document(working_bucket, "ocr", logger)
    }
    
    logger.info(f"Response: {json.dumps(response, default=str)}")
    return response
