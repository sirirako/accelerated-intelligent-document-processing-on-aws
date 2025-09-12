# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import time
import logging

from idp_common import get_config, assessment
from idp_common.models import Document, Status
from idp_common.docs_service import create_document_service
from idp_common import s3
from assessment_validator import AssessmentValidator

# Configuration will be loaded in handler function

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logging.getLogger('idp_common.bedrock.client').setLevel(os.environ.get("BEDROCK_LOG_LEVEL", "INFO"))

def handler(event, context):
    """
    Lambda handler for document assessment.
    This function assesses the confidence of extraction results for a document section
    using the Assessment service from the idp_common library.
    """
    logger.info(f"Starting assessment processing for event: {json.dumps(event, default=str)}")

    # Load configuration
    config = get_config()
    # Use default=str to handle Decimal and other non-serializable types
    logger.info(f"Config: {json.dumps(config, default=str)}")
    
    # Extract input from event - handle both compressed and uncompressed
    document_data = event.get('document', {})
    section_id = event.get('section_id')
    
    # Validate inputs
    if not document_data:
        raise ValueError("No document provided in event")
        
    if not section_id:
        raise ValueError("No section_id provided in event")
        
    # Convert document data to Document object - handle compression
    working_bucket = os.environ.get('WORKING_BUCKET')
    document = Document.load_document(document_data, working_bucket, logger)
    document.status = Status.ASSESSING
    logger.info(f"Processing assessment for document {document.id}, section {section_id}")

    # Update document status to ASSESSING for UI only
    # Create new 'shell' document since our input document has only 1 section. 
    docStatus = Document(
        id=document.id,
        input_key=document.input_key,
        status=Status.ASSESSING,
    )
    document_service = create_document_service()
    logger.info(f"Updating document status to {docStatus.status}")
    document_service.update_document(docStatus)

    # Initialize assessment service with cache table for enhanced retry handling
    cache_table = os.environ.get('TRACKING_TABLE')
    
    # Check if granular assessment is enabled
    granular_config = config.get('assessment', {}).get('granular', {})
    granular_enabled = granular_config.get('enabled', False)
    
    if granular_enabled:
        # Use enhanced granular assessment service with caching and retry support
        from idp_common.assessment.granular_service import GranularAssessmentService
        assessment_service = GranularAssessmentService(config=config, cache_table=cache_table)
        logger.info("Using granular assessment service with enhanced error handling and caching")
    else:
        # Use regular assessment service
        assessment_service = assessment.AssessmentService(config=config)
        logger.info("Using regular assessment service")

    # Process the document section for assessment
    t0 = time.time()
    logger.info(f"Starting assessment for section {section_id}")
    
    try:
        updated_document = assessment_service.process_document_section(document, section_id)
        t1 = time.time()
        logger.info(f"Total assessment time: {t1-t0:.2f} seconds")
        
        # Check for failed assessment tasks that might require retry
        if (hasattr(updated_document, 'metadata') and 
            updated_document.metadata and 
            'failed_assessment_tasks' in updated_document.metadata):
            
            failed_tasks = updated_document.metadata['failed_assessment_tasks']
            throttling_tasks = {
                task_id: task_info for task_id, task_info in failed_tasks.items()
                if task_info.get('is_throttling', False)
            }
            
            logger.warning(
                f"Assessment completed with {len(failed_tasks)} failed tasks, "
                f"{len(throttling_tasks)} due to throttling"
            )
            
            if throttling_tasks:
                logger.info(
                    f"Throttling detected in {len(throttling_tasks)} tasks. "
                    f"Successful tasks have been cached for retry."
                )
        
    except Exception as e:
        t1 = time.time()
        logger.error(f"Assessment failed after {t1-t0:.2f} seconds: {str(e)}")
        
        # Check if this is a throttling exception that should trigger retry
        from botocore.exceptions import ClientError
        throttling_exceptions = [
            "ThrottlingException",
            "ProvisionedThroughputExceededException",
            "ServiceQuotaExceededException", 
            "TooManyRequestsException",
            "RequestLimitExceeded"
        ]
        
        is_throttling = False
        if isinstance(e, ClientError):
            error_code = e.response.get('Error', {}).get('Code', '')
            is_throttling = error_code in throttling_exceptions
        else:
            exception_name = type(e).__name__
            exception_message = str(e).lower()
            is_throttling = (
                exception_name in throttling_exceptions or
                any(throttle_term.lower() in exception_message for throttle_term in throttling_exceptions)
            )
        
        if is_throttling:
            logger.error(f"Throttling exception detected: {type(e).__name__}. This will trigger state machine retry.")
            # Update document status before re-raising
            document_service.update_document(docStatus)
            # Re-raise to trigger state machine retry
            raise
        else:
            logger.error(f"Non-throttling exception: {type(e).__name__}. Marking document as failed.")
            # Set document status to failed for non-throttling exceptions
            updated_document = document
            updated_document.status = Status.FAILED
            updated_document.errors.append(str(e))

    # Assessment validation
    assessment_enabled = config.get('assessment', {}).get('enabled', False)
    if not assessment_enabled:
        logger.info("Assessment is disabled.")
    else:
        for section in updated_document.sections:
            if section.section_id == section_id and section.extraction_result_uri:
                logger.info(f"Loading assessment results from: {section.extraction_result_uri}")
                # Load extraction data with assessment results
                extraction_data = s3.get_json_content(section.extraction_result_uri)
                validator = AssessmentValidator(extraction_data,
                                                assessment_config=config.get('assessment', {}),
                                                enable_missing_check=False,
                                                enable_count_check=False)
                validation_results = validator.validate_all()
                if not validation_results['is_valid']:
                    # Handle validation failure
                    updated_document.status = Status.FAILED
                    validation_errors = validation_results['validation_errors']
                    updated_document.errors.extend(validation_errors)
                    logger.error(f"Validation Error: {validation_errors}")

    # Prepare output with automatic compression if needed
    result = {
        'document': updated_document.serialize_document(working_bucket, f"assessment_{section_id}", logger),
        'section_id': section_id
    }
    
    logger.info("Assessment processing completed")
    return result
