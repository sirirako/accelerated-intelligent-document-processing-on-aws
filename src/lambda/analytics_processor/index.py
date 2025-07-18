# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Lambda function to process analytics queries.
For Phase 1, this function generates a dummy plot and updates the job status.
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

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

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


def generate_dummy_plot():
    """
    Generate a dummy plot for Phase 1.
    
    Returns:
        A dictionary with plot data
    """
    # Sample bar chart data
    return {
        "type": "bar",
        "data": {
            "labels": ["Document Type A", "Document Type B", "Document Type C", "Document Type D"],
            "datasets": [
                {
                    "label": "Document Count",
                    "data": [65, 59, 80, 81],
                    "backgroundColor": [
                        "rgba(255, 99, 132, 0.2)",
                        "rgba(54, 162, 235, 0.2)",
                        "rgba(255, 206, 86, 0.2)",
                        "rgba(75, 192, 192, 0.2)"
                    ],
                    "borderColor": [
                        "rgba(255, 99, 132, 1)",
                        "rgba(54, 162, 235, 1)",
                        "rgba(255, 206, 86, 1)",
                        "rgba(75, 192, 192, 1)"
                    ],
                    "borderWidth": 1
                }
            ]
        },
        "options": {
            "scales": {
                "y": {
                    "beginAtZero": True
                }
            },
            "responsive": True,
            "maintainAspectRatio": False,
            "title": {
                "display": True,
                "text": "Document Distribution by Type"
            }
        }
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
            "status": status,
            "userId": user_id,
            "query": query,
            "createdAt": created_at
        }
        
        if result:
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
                logger.info(f"Response: {response.text}")
            else:
                logger.error(f"GraphQL errors in response: {json.dumps(response_json.get('errors'))}")
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
        
        # Generate a dummy plot for Phase 1
        try:
            # Simulate processing time
            time.sleep(10)
            
            # Generate the dummy plot
            plot_data = generate_dummy_plot()
            
            # Prepare the result
            result = {
                "responseType": "plotData",
                "plotData": [plot_data],
                "metadata": {
                    "generatedAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "query": job_record.get("query")
                }
            }
            
            # Update the job record with the result
            completed_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
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
                    ":status": "COMPLETED",
                    ":result": result,
                    ":completedAt": completed_at
                }
            )
            logger.info(f"Updated job status to COMPLETED with result: {job_id}")
            
            # Update the job status in AppSync to trigger the subscription
            update_job_status_in_appsync(job_id, "COMPLETED", result)
            
            # Return the updated job record (without exposing userId)
            return {
                "jobId": job_id,
                "status": "COMPLETED",
                "query": job_record.get("query"),
                "createdAt": job_record.get("createdAt"),
                "completedAt": completed_at,
                "result": result
            }
            
        except Exception as e:
            # Handle processing error
            error_msg = f"Error processing analytics query: {str(e)}"
            logger.error(error_msg)
            
            # Update the job record with the error
            completed_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
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
                    ":status": "FAILED",
                    ":error": error_msg,
                    ":completedAt": completed_at
                }
            )
            logger.info(f"Updated job status to FAILED with error: {job_id}")
            
            # Update the job status in AppSync to trigger the subscription
            update_job_status_in_appsync(job_id, "FAILED", error=error_msg)
            
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
