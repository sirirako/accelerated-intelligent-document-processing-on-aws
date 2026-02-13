# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Batch status tool for checking processing status"""

import logging
from typing import Any, Dict, Optional
from .base import IDPTool

logger = logging.getLogger(__name__)

# Version marker
TOOL_VERSION = "SDK-v2"
TOOL_UPDATED = "2025-01-09T19:30:00Z"


class BatchStatusTool(IDPTool):
    """Get processing status for a batch"""

    def execute(
        self,
        stack_name: str,
        batch_id: str,
        options: Optional[Dict[str, Any]] = None,
        region: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Get batch status using IDP SDK"""
        logger.info(f"=== Batch Status Tool ===")
        logger.info(f"Version: {TOOL_VERSION}")
        logger.info(f"Updated: {TOOL_UPDATED}")
        logger.info(f"Parameters: stack_name={stack_name}, batch_id={batch_id}, region={region}")
        
        from idp_sdk.client import IDPClient

        options = options or {}

        try:
            # Initialize SDK client
            client = IDPClient(stack_name=stack_name, region=region)

            # Call SDK batch.get_status() method
            status = client.batch.get_status(batch_id=batch_id)

            # Format response
            response = {
                "success": True,
                "batch_id": batch_id,
                "status": {
                    "total": status.total,
                    "completed": status.completed,
                    "in_progress": status.in_progress,
                    "failed": status.failed,
                    "queued": status.queued
                },
                "progress": {
                    "percentage": round((status.completed / status.total * 100) if status.total > 0 else 0, 2)
                },
                "all_complete": status.all_complete
            }

            # Add detailed info if requested
            if options.get("detailed") and hasattr(status, 'documents'):
                response["documents"] = [
                    {
                        "document_id": doc.document_id,
                        "status": doc.status.value,
                        "duration_seconds": doc.duration_seconds
                    }
                    for doc in status.documents
                ]

            return response

        except Exception as e:
            logger.error(f"Batch status failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "stack_name": stack_name,
                "batch_id": batch_id
            }
