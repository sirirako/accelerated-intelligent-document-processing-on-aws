# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)

stepfunctions = boto3.client('stepfunctions')

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get Step Functions execution details
    
    Args:
        event: AppSync event containing executionArn
        context: Lambda context
        
    Returns:
        Step Functions execution details with step history
    """
    try:
        execution_arn = event['arguments']['executionArn']
        logger.info(f"Getting execution details for: {execution_arn}")
        
        # Get execution details
        execution_response = stepfunctions.describe_execution(executionArn=execution_arn)
        
        # Get execution history
        history_response = stepfunctions.get_execution_history(
            executionArn=execution_arn,
            maxResults=100,
            reverseOrder=False
        )
        
        # Process execution details
        execution_details = {
            'executionArn': execution_response['executionArn'],
            'status': execution_response['status'],
            'startDate': execution_response['startDate'].isoformat() if execution_response.get('startDate') else None,
            'stopDate': execution_response.get('stopDate').isoformat() if execution_response.get('stopDate') else None,
            'input': execution_response.get('input'),
            'output': execution_response.get('output'),
            'steps': parse_execution_history(history_response['events'])
        }
        
        logger.info(f"Successfully retrieved execution details for {execution_arn}")
        return execution_details
        
    except Exception as e:
        logger.error(f"Error getting Step Functions execution: {str(e)}")
        raise e

def parse_execution_history(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parse Step Functions execution history events into step details
    
    Args:
        events: List of execution history events
        
    Returns:
        List of step details
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
                
        elif event_type == 'ChoiceStateEntered':
            step_name = event['stateEnteredEventDetails']['name']
            step_map[step_name] = {
                'name': step_name,
                'type': 'Choice',
                'status': 'SUCCEEDED',
                'startDate': timestamp,
                'stopDate': timestamp,
                'input': event['stateEnteredEventDetails'].get('input'),
                'output': None,
                'error': None
            }
            
        elif event_type == 'PassStateEntered':
            step_name = event['stateEnteredEventDetails']['name']
            step_map[step_name] = {
                'name': step_name,
                'type': 'Pass',
                'status': 'SUCCEEDED',
                'startDate': timestamp,
                'stopDate': timestamp,
                'input': event['stateEnteredEventDetails'].get('input'),
                'output': event['stateEnteredEventDetails'].get('output'),
                'error': None
            }
    
    # Convert to list and sort by start time
    steps = list(step_map.values())
    steps.sort(key=lambda x: x['startDate'] if x['startDate'] else '')
    
    return steps
