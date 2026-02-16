# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Batch run tool for processing documents"""

import logging
from typing import Any, Dict, Optional
from .base import IDPTool

logger = logging.getLogger(__name__)

# Version marker
TOOL_VERSION = "SDK-v2"
TOOL_UPDATED = "2025-01-09T19:30:00Z"


class BatchRunTool(IDPTool):
    """Process multiple documents through IDP pipeline"""

    def execute(
        self,
        stack_name: str,
        source: str,
        options: Optional[Dict[str, Any]] = None,
        region: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute batch processing using SDK core modules"""
        logger.info(f"=== Batch Run Tool ===")
        logger.info(f"Version: {TOOL_VERSION}")
        logger.info(f"Updated: {TOOL_UPDATED}")
        logger.info(f"Parameters: stack_name={stack_name}, source={source}, options={options}, region={region}")
        
        from idp_sdk.core.batch_processor import BatchProcessor
        import os

        options = options or {}

        try:
            logger.info(f"Initializing BatchProcessor with stack: {stack_name}")
            processor = BatchProcessor(stack_name=stack_name, region=region)
            logger.info("BatchProcessor initialized successfully")
            
            # Determine source type
            logger.info(f"Determining source type for: {source}")
            if source.startswith("s3://"):
                logger.info("Processing from S3 URI")
                result = processor.process_batch_from_s3_uri(
                    s3_uri=source,
                    file_pattern=options.get("file_pattern", "*.pdf"),
                    recursive=options.get("recursive", True),
                    output_prefix=options.get("batch_prefix", "mcp-batch")
                )
            elif os.path.isdir(source):
                logger.info("Processing from directory")
                result = processor.process_batch_from_directory(
                    dir_path=source,
                    file_pattern=options.get("file_pattern", "*.pdf"),
                    recursive=options.get("recursive", True),
                    output_prefix=options.get("batch_prefix", "mcp-batch")
                )
            else:
                logger.info("Processing from manifest")
                result = processor.process_batch(
                    manifest_path=source,
                    output_prefix=options.get("batch_prefix", "mcp-batch")
                )

            # Format response
            logger.info(f"Batch processing completed. Result: {result}")
            return {
                "success": True,
                "batch_id": result["batch_id"],
                "documents_queued": result.get("queued", 0),
                "summary": {
                    "queued": result.get("queued", 0),
                    "skipped": result.get("skipped", 0),
                    "failed": result.get("failed", 0)
                },
                "source": source,
                "message": f"Successfully queued {result.get('queued', 0)} documents for processing"
            }

        except Exception as e:
            logger.error(f"Batch run failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "stack_name": stack_name,
                "source": source
            }
