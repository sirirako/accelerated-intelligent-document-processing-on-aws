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
        
        logger.info(f"Retrieved {len(history_response['events'])} events for execution {execution_arn}")
        
        # Log event types for debugging
        event_types = [event['type'] for event in history_response['events']]
        logger.debug(f"Event types found: {set(event_types)}")
        
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
    event_id_to_step = {}  # Map event IDs to step names for correlation
    
    for event in events:
        event_type = event['type']
        event_id = event['id']
        timestamp = event['timestamp'].isoformat()
        
        # Handle state entered events
        if event_type in ['TaskStateEntered', 'ChoiceStateEntered', 'PassStateEntered', 'WaitStateEntered', 'ParallelStateEntered']:
            step_name = event['stateEnteredEventDetails']['name']
            step_type = event_type.replace('StateEntered', '').replace('Task', 'Task').replace('Choice', 'Choice').replace('Pass', 'Pass').replace('Wait', 'Wait').replace('Parallel', 'Parallel')
            
            step_map[step_name] = {
                'name': step_name,
                'type': step_type,
                'status': 'RUNNING',
                'startDate': timestamp,
                'stopDate': None,
                'input': event['stateEnteredEventDetails'].get('input'),
                'output': None,
                'error': None
            }
            event_id_to_step[event_id] = step_name
            
        # Handle state exited events (successful completion)
        elif event_type in ['TaskStateExited', 'ChoiceStateExited', 'PassStateExited', 'WaitStateExited', 'ParallelStateExited']:
            step_name = event['stateExitedEventDetails']['name']
            if step_name in step_map:
                step_map[step_name]['status'] = 'SUCCEEDED'
                step_map[step_name]['stopDate'] = timestamp
                step_map[step_name]['output'] = event['stateExitedEventDetails'].get('output')
                
        # Handle task failure events
        elif event_type == 'TaskFailed':
            # Find the corresponding step by looking at previous events
            step_name = find_step_name_for_failure_event(event, events, event_id_to_step)
            if step_name and step_name in step_map:
                step_map[step_name]['status'] = 'FAILED'
                step_map[step_name]['stopDate'] = timestamp
                
                # Extract error details
                task_failed_details = event.get('taskFailedEventDetails', {})
                error_message = task_failed_details.get('error', 'Unknown error')
                cause = task_failed_details.get('cause', '')
                
                # Combine error and cause for more detailed error message
                if cause:
                    try:
                        # Try to parse cause as JSON for better formatting
                        cause_json = json.loads(cause)
                        if isinstance(cause_json, dict):
                            error_type = cause_json.get('errorType', '')
                            error_msg = cause_json.get('errorMessage', '')
                            if error_type and error_msg:
                                error_message = f"{error_type}: {error_msg}"
                            elif error_msg:
                                error_message = error_msg
                    except (json.JSONDecodeError, TypeError):
                        # If cause is not JSON, append it as-is
                        error_message = f"{error_message}: {cause}"
                
                step_map[step_name]['error'] = error_message
                
        # Handle other failure events
        elif event_type in ['TaskTimedOut', 'TaskAborted']:
            step_name = find_step_name_for_failure_event(event, events, event_id_to_step)
            if step_name and step_name in step_map:
                step_map[step_name]['status'] = 'FAILED'
                step_map[step_name]['stopDate'] = timestamp
                
                if event_type == 'TaskTimedOut':
                    timeout_details = event.get('taskTimedOutEventDetails', {})
                    error_message = f"Task timed out: {timeout_details.get('error', 'Timeout occurred')}"
                    cause = timeout_details.get('cause', '')
                    if cause:
                        error_message = f"{error_message} - {cause}"
                elif event_type == 'TaskAborted':
                    error_message = "Task was aborted"
                    
                step_map[step_name]['error'] = error_message
                
        # Handle Lambda function failure events
        elif event_type == 'LambdaFunctionFailed':
            step_name = find_step_name_for_failure_event(event, events, event_id_to_step)
            if step_name and step_name in step_map:
                step_map[step_name]['status'] = 'FAILED'
                step_map[step_name]['stopDate'] = timestamp
                
                lambda_failed_details = event.get('lambdaFunctionFailedEventDetails', {})
                error_message = lambda_failed_details.get('error', 'Lambda function failed')
                cause = lambda_failed_details.get('cause', '')
                if cause:
                    error_message = f"{error_message}: {cause}"
                    
                step_map[step_name]['error'] = error_message
    
    # Convert to list and sort by start time
    steps = list(step_map.values())
    steps.sort(key=lambda x: x['startDate'] if x['startDate'] else '')
    
    return steps

def find_step_name_for_failure_event(failure_event: Dict[str, Any], all_events: List[Dict[str, Any]], event_id_to_step: Dict[int, str]) -> Optional[str]:
    """
    Find the step name associated with a failure event by correlating with previous events
    
    Args:
        failure_event: The failure event
        all_events: All execution history events
        event_id_to_step: Mapping of event IDs to step names
        
    Returns:
        Step name if found, None otherwise
    """
    try:
        # Try to get the step name from previousEventId correlation
        previous_event_id = failure_event.get('previousEventId')
        if previous_event_id and previous_event_id in event_id_to_step:
            return event_id_to_step[previous_event_id]
            
        # Alternative approach: look for the most recent TaskStateEntered event before this failure
        failure_event_id = failure_event['id']
        for event in reversed(all_events):
            if event['id'] >= failure_event_id:
                continue
            if event['type'] == 'TaskStateEntered':
                return event['stateEnteredEventDetails']['name']
                
        # Fallback: try to extract from task details if available
        if 'taskFailedEventDetails' in failure_event:
            resource = failure_event['taskFailedEventDetails'].get('resource', '')
            if resource:
                # Extract step name from resource ARN if possible
                # This is a best-effort approach
                parts = resource.split(':')
                if len(parts) > 1:
                    return parts[-1].split('/')[-1]
                    
    except Exception as e:
        logger.warning(f"Error finding step name for failure event: {str(e)}")
        
    return None
