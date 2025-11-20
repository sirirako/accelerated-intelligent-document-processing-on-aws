# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Lambda function to handle agent chat message requests.
This function stores messages in DynamoDB and invokes the agent chat processor Lambda
for conversational, multi-turn interactions.
"""

import json
import logging
import os
import time
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

# Get environment variables
CHAT_MESSAGES_TABLE = os.environ.get("CHAT_MESSAGES_TABLE")
CHAT_SESSIONS_TABLE = os.environ.get("CHAT_SESSIONS_TABLE")
AGENT_CHAT_PROCESSOR_FUNCTION = os.environ.get("AGENT_CHAT_PROCESSOR_FUNCTION")
DATA_RETENTION_DAYS = int(os.environ.get("DATA_RETENTION_DAYS", "30"))


def handler(event, context):
    """
    Handle agent chat message requests from AppSync.
    
    This function stores user messages in DynamoDB and invokes the agent chat processor
    for conversational, multi-turn interactions. All registered agents are automatically
    available to the orchestrator.
    
    Args:
        event: The event dict from AppSync containing:
            - prompt: The user's message
            - sessionId: The conversation session ID
            - method: The message method (default: "chat")
        context: The Lambda context
        
    Returns:
        AgentChatMessage with role, content, timestamp, isProcessing, and sessionId
    """
    logger.info(f"Received agent chat event: {json.dumps(event)}")
    
    try:
        # Extract arguments from the event
        arguments = event.get("arguments", {})
        prompt = arguments.get("prompt")
        session_id = arguments.get("sessionId")
        method = arguments.get("method", "chat")
        enable_code_intelligence = arguments.get("enableCodeIntelligence", True)
        
        # Validate required parameters
        if not prompt:
            error_msg = "prompt parameter is required"
            logger.error(error_msg)
            raise Exception(error_msg)
            
        if not session_id:
            error_msg = "sessionId parameter is required"
            logger.error(error_msg)
            raise Exception(error_msg)
            
        # Validate prompt length
        if len(prompt) > 100000:
            error_msg = "Prompt exceeds maximum length of 100000 characters"
            logger.error(f"{error_msg}. Prompt length: {len(prompt)}")
            raise Exception(error_msg)
        
        # Calculate expiration time (TTL)
        current_time = int(time.time())
        expires_after = current_time + (DATA_RETENTION_DAYS * 24 * 60 * 60)
        
        # Create timestamp in ISO-8601 format with Z suffix for UTC
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        
        # Determine message role and processing status
        assistant_methods = [
            "assistant_response", "assistant_final_response", "assistant_processing",
            "assistant_thinking", "assistant_stream", "assistant_tool_use",
            "assistant_tool_result", "assistant_error",
            # Sub-agent event types
            "subagent_start", "subagent_stream", "subagent_end", "subagent_error",
            # Structured data event types
            "structured_data_start"
        ]
        is_assistant_response = method in assistant_methods
        role = "assistant" if is_assistant_response else "user"
        is_processing_complete = method in ["assistant_final_response", "assistant_error"]
        
        # Only store certain message types in DynamoDB
        # Skip storing streaming chunks, but store user messages and final responses
        # Sub-agent streaming events (start, stream, end) are NOT stored
        # Sub-agent errors ARE stored for debugging
        is_final_response = (
            not is_assistant_response or  # Store all user messages
            method in ["assistant_final_response", "assistant_error", "subagent_error"]  # Store final responses and errors
        )
        
        if is_final_response:
            # Store message in DynamoDB with session-based keys
            table = dynamodb.Table(CHAT_MESSAGES_TABLE)
            message = {
                "PK": session_id,  # Session-based partition key
                "SK": timestamp,   # Timestamp as sort key for chronological ordering
                "role": role,
                "content": prompt,
                "timestamp": timestamp,
                "isProcessing": not is_processing_complete,
                "ExpiresAfter": expires_after
            }
            
            table.put_item(Item=message)
            logger.info(f"Stored message in DynamoDB for session {session_id}: {method}")
            
            # Manage session metadata for user messages
            if not is_assistant_response:  # This is a user message
                # Get user identity for session metadata
                identity = event.get("identity", {})
                user_id = identity.get("username") or identity.get("sub") or "anonymous"
                
                manage_session_metadata(user_id, session_id, prompt, timestamp, expires_after)
        else:
            logger.info(f"Skipped storing streaming message in DynamoDB: {method}")
        
        # Invoke the agent chat processor for user messages
        # The processor will handle the orchestrator creation and streaming response
        if not is_assistant_response and AGENT_CHAT_PROCESSOR_FUNCTION:
            lambda_client.invoke(
                FunctionName=AGENT_CHAT_PROCESSOR_FUNCTION,
                InvocationType="Event",
                Payload=json.dumps({
                    "sessionId": session_id,
                    "prompt": prompt,
                    "method": method,
                    "timestamp": timestamp,
                    "enableCodeIntelligence": enable_code_intelligence
                })
            )
            logger.info(f"Invoked agent chat processor for session: {session_id} (Code Intelligence: {enable_code_intelligence})")
        
        # Return AgentChatMessage format
        return {
            "role": str(role),
            "content": str(prompt),
            "timestamp": str(timestamp),
            "isProcessing": not is_processing_complete,
            "sessionId": str(session_id)
        }
        
    except ClientError as e:
        error_msg = f"DynamoDB error: {str(e)}"
        logger.error(error_msg)
        # Return error as assistant message
        return {
            "role": "assistant",
            "content": f"Error: {error_msg}",
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "isProcessing": False,
            "sessionId": str(session_id) if session_id else ""
        }


def manage_session_metadata(user_id, session_id, prompt, timestamp, expires_after):
    """
    Create or update session metadata in the ChatSessionsTable.
    
    Args:
        user_id: The user ID for the session
        session_id: The session ID
        prompt: The user's message content
        timestamp: The message timestamp
        expires_after: TTL for the session
    """
    try:
        if not CHAT_SESSIONS_TABLE:
            logger.warn("CHAT_SESSIONS_TABLE not configured, skipping session metadata management")
            return
            
        sessions_table = dynamodb.Table(CHAT_SESSIONS_TABLE)
        
        # Check if session already exists
        try:
            response = sessions_table.get_item(
                Key={
                    "userId": user_id,
                    "sessionId": session_id
                }
            )
            
            if response.get("Item"):
                # Session exists, update it
                update_session_metadata(sessions_table, user_id, session_id, prompt, timestamp)
            else:
                # New session, create it
                create_session_metadata(sessions_table, user_id, session_id, prompt, timestamp, expires_after)
                
        except ClientError as e:
            logger.error(f"Error managing session metadata: {str(e)}")
            # Don't fail the main operation if session metadata fails
            
    except Exception as e:
        logger.error(f"Unexpected error managing session metadata: {str(e)}")
        # Don't fail the main operation if session metadata fails


def create_session_metadata(sessions_table, user_id, session_id, prompt, timestamp, expires_after):
    """Create a new session metadata record."""
    try:
        # Generate session title from the first message
        title = prompt.strip()
        if len(title) > 50:
            title = title[:47] + "..."
        
        # Create last message preview
        last_message = prompt[:100] + "..." if len(prompt) > 100 else prompt
        
        session_record = {
            "userId": user_id,
            "sessionId": session_id,
            "title": title,
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "messageCount": 1,  # First user message
            "lastMessage": last_message,
            "ExpiresAfter": expires_after
        }
        
        sessions_table.put_item(Item=session_record)
        logger.info(f"Created session metadata for {session_id}")
        
    except ClientError as e:
        logger.error(f"Error creating session metadata: {str(e)}")


def update_session_metadata(sessions_table, user_id, session_id, prompt, timestamp):
    """Update existing session metadata record."""
    try:
        # Create last message preview
        last_message = prompt[:100] + "..." if len(prompt) > 100 else prompt
        
        # Update the session record
        sessions_table.update_item(
            Key={
                "userId": user_id,
                "sessionId": session_id
            },
            UpdateExpression="SET updatedAt = :timestamp, messageCount = messageCount + :inc, lastMessage = :last_message",
            ExpressionAttributeValues={
                ":timestamp": timestamp,
                ":inc": 1,
                ":last_message": last_message
            }
        )
        
        logger.info(f"Updated session metadata for {session_id}")
        
    except ClientError as e:
        logger.error(f"Error updating session metadata: {str(e)}")
