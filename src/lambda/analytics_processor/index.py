# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Lambda function to process analytics queries using Strands agents.
"""

import json
import logging
import os
import time
from datetime import datetime

import boto3
import requests
from aws_requests_auth.aws_auth import AWSRequestsAuth
from botocore.exceptions import ClientError

# Import the analytics agent and configuration utilities from idp_common
from idp_common.agents.analytics import create_analytics_agent, get_analytics_config, parse_agent_response
from idp_common.agents.common.config import configure_logging

# Configure logging for both application and Strands framework
# This will respect both LOG_LEVEL and STRANDS_LOG_LEVEL environment variables
configure_logging()

# Get logger for this module
logger = logging.getLogger(__name__)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
session = boto3.Session()
credentials = session.get_credentials()

# Get environment variables
ANALYTICS_TABLE = os.environ.get("ANALYTICS_TABLE")
APPSYNC_API_URL = os.environ.get("APPSYNC_API_URL")


def validate_job_ownership(table, user_id, job_id):
    """
    Validate that the job belongs to the specified user.
    
    Args:
        table: DynamoDB table resource
        user_id: The user ID to validate against
        job_id: The job ID to validate
        
    Returns:
        The job record if valid
        
    Raises:
        ValueError: If the job doesn't exist or doesn't belong to the user
    """
    try:
        response = table.get_item(
            Key={
                "PK": f"analytics#{user_id}",
                "SK": job_id
            }
        )
        
        job_record = response.get("Item")
        if not job_record:
            error_msg = f"Job not found: {job_id} for user: {user_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"Job ownership validated for job: {job_id}, user: {user_id}")
        return job_record
        
    except ClientError as e:
        error_msg = f"Error validating job ownership: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)


def process_analytics_query(query: str) -> dict:
    """
    Process an analytics query using the Strands agent.
    
    Args:
        query: The natural language query to process
        
    Returns:
        Dict containing the analytics result
    """
    try:
        # Get analytics configuration
        config = get_analytics_config()
        logger.info("Analytics configuration loaded successfully")
        
        # Create the analytics agent
        agent = create_analytics_agent(config, session)
        logger.info("Analytics agent created successfully")
        
        # Process the query
        logger.info(f"Processing query: {query}")
        response = agent(query)
        logger.info("Query processed successfully")
        
        # Parse the response using the new parsing function
        try:
            result = parse_agent_response(response)
            logger.info(f"Parsed response with type: {result.get('responseType', 'unknown')}")
            return result
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse agent response: {e}")
            logger.error(f"Raw response: {response}")
            # Return a text response with the raw output
            return {
                "responseType": "text",
                "content": f"Error parsing response: {response}"
            }
            
    except Exception as e:
        logger.exception(f"Error processing analytics query: {str(e)}")
        return {
            "responseType": "text",
            "content": f"Error processing query: {str(e)}"
        }


def update_job_status_in_appsync(job_id, status, result=None, error=None):
    """
    Update the job status in AppSync via GraphQL mutation.
    
    Args:
        job_id: The ID of the job to update
        status: The new status of the job
        result: The result data (optional)
        error: The error message (optional)
    """
    try:
        # Prepare the mutation with userId parameter and all required fields
        mutation = """
        mutation UpdateAnalyticsJobStatus($jobId: ID!, $status: String!, $userId: String!, $query: String!, $createdAt: AWSDateTime!, $result: AWSJSON) {
            updateAnalyticsJobStatus(jobId: $jobId, status: $status, userId: $userId, query: $query, createdAt: $createdAt, result: $result) {
                jobId
                status
                query
                createdAt
            }
        }
        """
        
        # Extract user_id from the job_id's PK in DynamoDB
        table = dynamodb.Table(ANALYTICS_TABLE)
        # We need to query the table to find the job and get the user_id
        # Scan with a filter since we don't know the PK
        response = table.scan(
            FilterExpression="SK = :jobId",
            ExpressionAttributeValues={
                ":jobId": job_id
            }
        )
        
        items = response.get("Items", [])
        if not items:
            logger.error(f"Job not found in DynamoDB: {job_id}")
            return
            
        # Extract the user_id from the PK and get other required fields
        job_record = items[0]
        pk = job_record.get("PK", "")
        user_id = pk.replace("analytics#", "") if pk.startswith("analytics#") else "anonymous"
        query = job_record.get("query", "")
        created_at = job_record.get("createdAt", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
        
        logger.info(f"Found job {job_id} for user {user_id}")
        
        # Prepare the variables with all required fields
        variables = {
            "jobId": job_id,
            "status": status,  # Simple string, not a DynamoDB object
            "userId": user_id,
            "query": query,
            "createdAt": created_at
        }
        
        # Serialize result to JSON string if it's provided
        if result:
            if isinstance(result, str):
                variables["result"] = result
            else:
                variables["result"] = json.dumps(result)
        
        # Set up AWS authentication
        region = session.region_name or os.environ.get('AWS_REGION', 'us-east-1')
        auth = AWSRequestsAuth(
            aws_access_key=credentials.access_key,
            aws_secret_access_key=credentials.secret_key,
            aws_token=credentials.token,
            aws_host=APPSYNC_API_URL.replace('https://', '').replace('/graphql', ''),
            aws_region=region,
            aws_service='appsync'
        )
        
        # Prepare the request
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        payload = {
            'query': mutation,
            'variables': variables
        }
        
        logger.info(f"Publishing analytics job update to AppSync for job: {job_id}")
        logger.debug(f"Mutation payload: {json.dumps(payload)}")
        
        # Make the request
        response = requests.post(
            APPSYNC_API_URL,
            json=payload,
            headers=headers,
            auth=auth,
            timeout=30
        )
        
        # Check for successful response
        if response.status_code == 200:
            response_json = response.json()
            if "errors" not in response_json:
                logger.info(f"Successfully published analytics job update for: {job_id}, user: {user_id}")
                logger.debug(f"Response: {response.text}")
            else:
                logger.error(f"GraphQL errors in response: {json.dumps(response_json.get('errors'))}")
                # Log the full payload for debugging
                logger.error(f"Full mutation payload: {json.dumps(payload)}")
        else:
            logger.error(f"Failed to publish analytics job update. Status: {response.status_code}, Response: {response.text}")
        
    except Exception as e:
        logger.error(f"Error updating job status in AppSync: {str(e)}")
        import traceback
        logger.error(f"Error traceback: {traceback.format_exc()}")


def handler(event, context):
    """
    Process analytics queries.
    
    Args:
        event: The event dict with userId and jobId
        context: The Lambda context
        
    Returns:
        The updated job record
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Extract user ID and job ID from the event
        user_id = event.get("userId")
        job_id = event.get("jobId")
        
        if not user_id or not job_id:
            error_msg = "userId and jobId are required"
            logger.error(error_msg)
            return {
                "statusCode": 400,
                "body": error_msg
            }
        
        # Get the DynamoDB table
        table = dynamodb.Table(ANALYTICS_TABLE)
        
        # Validate job ownership
        try:
            job_record = validate_job_ownership(table, user_id, job_id)
        except ValueError as e:
            return {
                "statusCode": 403,
                "body": str(e)
            }
        
        # Update the job status to PROCESSING
        table.update_item(
            Key={
                "PK": f"analytics#{user_id}",
                "SK": job_id
            },
            UpdateExpression="SET #status = :status",
            ExpressionAttributeNames={
                "#status": "status"
            },
            ExpressionAttributeValues={
                ":status": "PROCESSING"
            }
        )
        logger.info(f"Updated job status to PROCESSING: {job_id}")
        
        # Process the analytics query using the agent
        try:
            # Simulate processing time for now (can be removed later)
            time.sleep(2)
            
            # Process the query using the analytics agent
            result = process_analytics_query(job_record.get("query"))
            
            # Prepare the result with metadata
            analytics_result = {
                "responseType": result.get("responseType", "text"),
                "metadata": {
                    "generatedAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "query": job_record.get("query")
                }
            }
            
            # Add the appropriate data field based on response type
            if result.get("responseType") == "plotData":
                analytics_result["plotData"] = [result]  # Wrap in array for consistency
            elif result.get("responseType") == "table":
                analytics_result["tableData"] = result
            else:  # text or fallback
                analytics_result["content"] = result.get("content", "No content available")
            
            # Update the job record with the result
            completed_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            
            # Serialize the analytics_result to a JSON string to avoid DynamoDB type issues
            analytics_result_json = json.dumps(analytics_result)
            
            # Define the status explicitly
            job_status = "COMPLETED"
            
            table.update_item(
                Key={
                    "PK": f"analytics#{user_id}",
                    "SK": job_id
                },
                UpdateExpression="SET #status = :status, #result = :result, #completedAt = :completedAt",
                ExpressionAttributeNames={
                    "#status": "status",
                    "#result": "result",
                    "#completedAt": "completedAt"
                },
                ExpressionAttributeValues={
                    ":status": job_status,  # Use the explicitly defined status
                    ":result": analytics_result_json,  # Store as JSON string
                    ":completedAt": completed_at
                }
            )
            logger.info(f"Updated job status to {job_status} with result: {job_id}")
            
            # Update the job status in AppSync to trigger the subscription
            # Pass the analytics_result directly (not the JSON string)
            update_job_status_in_appsync(job_id, job_status, analytics_result)
            
            # Return the updated job record (without exposing userId)
            # If the result is stored as a JSON string, deserialize it for the response
            result_to_return = analytics_result
            
            return {
                "jobId": job_id,
                "status": "COMPLETED",
                "query": job_record.get("query"),
                "createdAt": job_record.get("createdAt"),
                "completedAt": completed_at,
                "result": result_to_return
            }
            
        except Exception as e:
            # Handle processing error
            error_msg = f"Error processing analytics query: {str(e)}"
            logger.error(error_msg)
            
            # Update the job record with the error
            completed_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            job_status = "FAILED"
            
            table.update_item(
                Key={
                    "PK": f"analytics#{user_id}",
                    "SK": job_id
                },
                UpdateExpression="SET #status = :status, #error = :error, #completedAt = :completedAt",
                ExpressionAttributeNames={
                    "#status": "status",
                    "#error": "error",
                    "#completedAt": "completedAt"
                },
                ExpressionAttributeValues={
                    ":status": job_status,  # Use the explicitly defined status
                    ":error": str(error_msg),  # Ensure error is stored as a string
                    ":completedAt": completed_at
                }
            )
            logger.info(f"Updated job status to {job_status} with error: {job_id}")
            
            # Update the job status in AppSync to trigger the subscription
            update_job_status_in_appsync(job_id, job_status, error=str(error_msg))
            
            return {
                "statusCode": 500,
                "body": error_msg
            }
        
    except ClientError as e:
        logger.error(f"DynamoDB error: {str(e)}")
        return {
            "statusCode": 500,
            "body": f"Database error: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return {
            "statusCode": 500,
            "body": f"Error processing request: {str(e)}"
        }
