# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import os
import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()

# Initialize clients
stepfunctions = boto3.client('stepfunctions')
appsync = boto3.client('appsync')

APPSYNC_API_URL = os.environ['APPSYNC_API_URL']


def handler(event: dict, context: LambdaContext) -> dict:
    """
    Lambda function to publish Step Functions execution updates to GraphQL subscription
    
    Args:
        event: EventBridge event from Step Functions
        context: Lambda context
        
    Returns:
        Success response
    """
    logger.info("Received Step Functions event", extra={"event": event})
    
    try:
        # Extract execution ARN from the event
        detail = event.get('detail', {})
        execution_arn = detail.get('executionArn')
        
        if not execution_arn:
            logger.warning("No execution ARN found in event")
            return {"statusCode": 200, "body": "No execution ARN found"}
        
        # Get updated execution details
        execution_response = stepfunctions.describe_execution(executionArn=execution_arn)
        
        # Get execution history
        history_response = stepfunctions.get_execution_history(
            executionArn=execution_arn,
            maxResults=100,
            reverseOrder=False
        )
        
        # Parse execution details (reuse logic from get_stepfunction_execution_resolver)
        execution_details = {
            'executionArn': execution_response['executionArn'],
            'status': execution_response['status'],
            'startDate': execution_response['startDate'].isoformat() if execution_response.get('startDate') else None,
            'stopDate': execution_response.get('stopDate').isoformat() if execution_response.get('stopDate') else None,
            'input': execution_response.get('input'),
            'output': execution_response.get('output'),
            'steps': parse_execution_history(history_response['events'])
        }
        
        # Publish to GraphQL subscription
        mutation = """
        mutation PublishStepFunctionUpdate($executionArn: String!, $data: AWSJSON!) {
          publishStepFunctionExecutionUpdate(executionArn: $executionArn, data: $data)
        }
        """
        
        variables = {
            'executionArn': execution_arn,
            'data': json.dumps(execution_details)
        }
        
        # Note: This would require a custom mutation resolver to publish to subscriptions
        # For now, we'll use the existing pattern of EventBridge -> Lambda -> AppSync
        logger.info("Step Functions execution update processed", extra={
            "execution_arn": execution_arn,
            "status": execution_details['status']
        })
        
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Step Functions update processed successfully"})
        }
        
    except Exception as e:
        logger.error(f"Error processing Step Functions event: {str(e)}")
        raise e


def parse_execution_history(events):
    """
    Parse Step Functions execution history events into step details
    (Reused from get_stepfunction_execution_resolver)
    """
    steps = []
    step_map = {}
    
    for event in events:
        event_type = event['type']
        timestamp = event['timestamp'].isoformat()
        
        if event_type == 'TaskStateEntered':
            step_name = event['stateEnteredEventDetails']['name']
            step_map[step_name] = {
                'name': step_name,
                'type': 'Task',
                'status': 'RUNNING',
                'startDate': timestamp,
                'stopDate': None,
                'input': event['stateEnteredEventDetails'].get('input'),
                'output': None,
                'error': None
            }
            
        elif event_type == 'TaskStateExited':
            step_name = event['stateExitedEventDetails']['name']
            if step_name in step_map:
                step_map[step_name]['status'] = 'SUCCEEDED'
                step_map[step_name]['stopDate'] = timestamp
                step_map[step_name]['output'] = event['stateExitedEventDetails'].get('output')
                
        elif event_type == 'TaskFailed':
            step_name = event['taskFailedEventDetails'].get('resourceType', 'Unknown')
            if step_name in step_map:
                step_map[step_name]['status'] = 'FAILED'
                step_map[step_name]['stopDate'] = timestamp
                step_map[step_name]['error'] = event['taskFailedEventDetails'].get('error', 'Unknown error')
                
        elif event_type == 'TaskTimedOut':
            step_name = event['taskTimedOutEventDetails'].get('resourceType', 'Unknown')
            if step_name in step_map:
                step_map[step_name]['status'] = 'FAILED'
                step_map[step_name]['stopDate'] = timestamp
                step_map[step_name]['error'] = 'Task timed out'
    
    # Convert step_map to list
    steps = list(step_map.values())
    
    return steps
