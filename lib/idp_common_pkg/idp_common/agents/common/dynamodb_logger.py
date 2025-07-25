# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
DynamoDB integration for logging agent messages asynchronously.
"""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class DynamoDBMessageLogger:
    """
    Asynchronous DynamoDB logger for agent messages.

    This class handles writing agent conversation messages to DynamoDB
    in a non-blocking manner to avoid impacting agent performance.
    """

    def __init__(self, table_name: str, max_workers: int = 2):
        """
        Initialize the DynamoDB message logger.

        Args:
            table_name: Name of the DynamoDB table
            max_workers: Maximum number of worker threads for async operations
        """
        self.table_name = table_name
        self.dynamodb = boto3.resource("dynamodb")
        self.table = self.dynamodb.Table(table_name)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.sequence_counter = 0

        logger.info(f"DynamoDB message logger initialized for table: {table_name}")

    def log_message_async(
        self, job_id: str, user_id: str, message_data: Dict[str, Any]
    ) -> None:
        """
        Asynchronously log a message to DynamoDB.

        Args:
            job_id: The analytics job ID
            user_id: The user ID who owns the job
            message_data: The message data to log
        """
        # Add sequence number
        self.sequence_counter += 1
        message_data["sequence_number"] = self.sequence_counter

        # Submit the write operation to the thread pool
        future = self.executor.submit(
            self._write_message_to_dynamodb, job_id, user_id, message_data
        )

        # Add error callback
        future.add_done_callback(self._handle_write_result)

    def _write_message_to_dynamodb(
        self, job_id: str, user_id: str, message_data: Dict[str, Any]
    ) -> None:
        """
        Write a message to DynamoDB by appending to a JSON string.

        Args:
            job_id: The analytics job ID
            user_id: The user ID who owns the job
            message_data: The message data to log
        """
        try:
            pk = f"analytics#{user_id}"
            sk = job_id

            # First, try to get the existing agent_messages to append to it
            try:
                response = self.table.get_item(Key={"PK": pk, "SK": sk})
                item = response.get("Item", {})
                existing_messages_str = item.get("agent_messages", "[]")

                # Parse existing messages
                try:
                    existing_messages = json.loads(existing_messages_str)
                    if not isinstance(existing_messages, list):
                        existing_messages = []
                except json.JSONDecodeError:
                    logger.warning(
                        f"Invalid JSON in agent_messages for job {job_id}, starting fresh"
                    )
                    existing_messages = []

            except ClientError as e:
                if (
                    e.response.get("Error", {}).get("Code")
                    == "ResourceNotFoundException"
                ):
                    logger.warning(
                        f"Job record not found for job {job_id}, user {user_id}"
                    )
                    return
                else:
                    logger.error(
                        f"Error getting existing messages for job {job_id}: {e}"
                    )
                    existing_messages = []

            # Append the new message
            existing_messages.append(message_data)

            # Serialize back to JSON string
            updated_messages_str = json.dumps(existing_messages)

            # Update the record with the new JSON string
            self.table.update_item(
                Key={"PK": pk, "SK": sk},
                UpdateExpression="SET agent_messages = :messages",
                ExpressionAttributeValues={":messages": updated_messages_str},
                ReturnValues="NONE",
            )

            logger.debug(
                f"Successfully logged message for job {job_id}, sequence {message_data.get('sequence_number')}"
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "ResourceNotFoundException":
                logger.warning(
                    f"DynamoDB table {self.table_name} not found for job {job_id}"
                )
            elif error_code == "ConditionalCheckFailedException":
                logger.warning(f"Job record not found for job {job_id}, user {user_id}")
            else:
                logger.error(f"DynamoDB error logging message for job {job_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error logging message for job {job_id}: {e}")

    def _handle_write_result(self, future) -> None:
        """
        Handle the result of an async write operation.

        Args:
            future: The completed Future object
        """
        try:
            future.result()  # This will raise any exception that occurred
        except Exception as e:
            logger.error(f"Async DynamoDB write failed: {e}")

    def shutdown(self) -> None:
        """
        Shutdown the thread pool executor.
        """
        logger.info("Shutting down DynamoDB message logger")
        self.executor.shutdown(wait=True)


class DynamoDBMessageTracker:
    """
    Message tracker that integrates with DynamoDB logging.

    This class combines the MessageTracker functionality with
    DynamoDB logging capabilities.
    """

    def __init__(
        self,
        job_id: str,
        user_id: str,
        table_name: Optional[str] = None,
        enabled: bool = True,
    ):
        """
        Initialize the DynamoDB message tracker.

        Args:
            job_id: The analytics job ID
            user_id: The user ID who owns the job
            table_name: DynamoDB table name (defaults to ANALYTICS_TABLE env var)
            enabled: Whether monitoring is enabled
        """
        self.job_id = job_id
        self.user_id = user_id
        self.enabled = enabled
        self.messages = []
        self.logger = logging.getLogger(f"{__name__}.DynamoDBMessageTracker")

        if not enabled:
            self.logger.info("Agent monitoring disabled")
            self.db_logger = None
            return

        # Get table name from environment if not provided
        if table_name is None:
            table_name = os.environ.get("ANALYTICS_TABLE")

        if not table_name:
            self.logger.error(
                "No DynamoDB table name provided and ANALYTICS_TABLE env var not set"
            )
            self.enabled = False
            self.db_logger = None
            return

        try:
            self.db_logger = DynamoDBMessageLogger(table_name)
            self.logger.info(f"DynamoDB message tracker initialized for job {job_id}")
        except Exception as e:
            self.logger.error(f"Failed to initialize DynamoDB logger: {e}")
            self.enabled = False
            self.db_logger = None

    def register_hooks(self, registry, **kwargs: Any) -> None:
        """Register the message tracking callback."""
        if not self.enabled:
            return

        from strands.hooks.events import MessageAddedEvent

        registry.add_callback(MessageAddedEvent, self.on_message_added)

    def on_message_added(self, event) -> None:
        """Handle message added events."""
        if not self.enabled or not self.db_logger:
            return

        try:
            from .monitoring import AgentMonitor

            # Create a temporary monitor instance to use its message parsing logic
            temp_monitor = AgentMonitor()
            message_data = {
                "timestamp": datetime.now().isoformat(),
                **temp_monitor._get_message_preview(event.message),
            }

            # Store locally
            self.messages.append(message_data)

            # Log to DynamoDB asynchronously
            self.db_logger.log_message_async(self.job_id, self.user_id, message_data)

            # Log the message
            role = message_data["role"]
            content_preview = (
                message_data["content"][:100] + "..."
                if len(message_data["content"]) > 100
                else message_data["content"]
            )
            self.logger.info(
                f"📝 Message tracked: [{role}] {content_preview} (Total: {len(self.messages)})"
            )

        except Exception as e:
            self.logger.error(f"Error tracking message: {e}")

    def get_messages(self) -> list:
        """Get all tracked messages."""
        return self.messages.copy()

    def clear_messages(self) -> None:
        """Clear all tracked messages."""
        self.messages.clear()

    def shutdown(self) -> None:
        """Shutdown the tracker and its resources."""
        if self.db_logger:
            self.db_logger.shutdown()
