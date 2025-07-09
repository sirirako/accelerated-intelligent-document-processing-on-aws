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
        
        # Get execution history with pagination to capture all events
        all_events = []
        next_token = None
        
        while True:
            history_params = {
                'executionArn': execution_arn,
                'maxResults': 1000,  # Increased to capture more events
                'reverseOrder': False
            }
            
            if next_token:
                history_params['nextToken'] = next_token
                
            history_response = stepfunctions.get_execution_history(**history_params)
            all_events.extend(history_response['events'])
            
            next_token = history_response.get('nextToken')
            if not next_token:
                break
        
        logger.info(f"Retrieved {len(all_events)} events for execution {execution_arn}")
        
        # Log event types for debugging
        event_types = [event['type'] for event in all_events]
        logger.debug(f"Event types found: {set(event_types)}")
        
        # Process execution details
        execution_details = {
            'executionArn': execution_response['executionArn'],
            'status': execution_response['status'],
            'startDate': execution_response['startDate'].isoformat() if execution_response.get('startDate') else None,
            'stopDate': execution_response.get('stopDate').isoformat() if execution_response.get('stopDate') else None,
            'input': execution_response.get('input'),
            'output': execution_response.get('output'),
            'steps': parse_execution_history(all_events)
        }
        
        logger.info(f"Successfully retrieved execution details for {execution_arn}")
        return execution_details
        
    except Exception as e:
        logger.error(f"Error getting Step Functions execution: {str(e)}")
        raise e

def parse_execution_history(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parse Step Functions execution history events into step details with enhanced Map state support
    
    Args:
        events: List of execution history events
        
    Returns:
        List of step details including Map state iterations
    """
    steps = []
    step_map = {}
    event_id_to_step = {}  # Map event IDs to step names for correlation
    map_iterations = {}  # Track Map state iterations
    
    # First pass: identify all states and their basic information
    for event in events:
        event_type = event['type']
        event_id = event['id']
        timestamp = event['timestamp'].isoformat()
        
        # Handle state entered events
        if event_type in ['TaskStateEntered', 'ChoiceStateEntered', 'PassStateEntered', 'WaitStateEntered', 'ParallelStateEntered', 'MapStateEntered']:
            step_name = event['stateEnteredEventDetails']['name']
            step_type = event_type.replace('StateEntered', '')
            
            # Create unique key for this step instance
            step_key = f"{step_name}_{event_id}"
            
            step_map[step_key] = {
                'name': step_name,
                'type': step_type,
                'status': 'RUNNING',
                'startDate': timestamp,
                'stopDate': None,
                'input': event['stateEnteredEventDetails'].get('input'),
                'output': None,
                'error': None,
                'eventId': event_id,
                'isMapState': step_type == 'Map'
            }
            event_id_to_step[event_id] = step_key
            
        # Handle state exited events (successful completion)
        elif event_type in ['TaskStateExited', 'ChoiceStateExited', 'PassStateExited', 'WaitStateExited', 'ParallelStateExited', 'MapStateExited']:
            step_name = event['stateExitedEventDetails']['name']
            
            # Find the corresponding step by name and update it
            for step_key, step_data in step_map.items():
                if step_data['name'] == step_name and step_data['status'] == 'RUNNING':
                    step_data['status'] = 'SUCCEEDED'
                    step_data['stopDate'] = timestamp
                    step_data['output'] = event['stateExitedEventDetails'].get('output')
                    break
                    
        # Handle Map iteration events
        elif event_type == 'MapIterationStarted':
            iteration_details = event.get('mapIterationStartedEventDetails', {})
            map_name = iteration_details.get('name', 'Unknown')
            iteration_index = iteration_details.get('index', 0)
            
            # Create a unique key for this iteration
            iteration_key = f"{map_name}_iteration_{iteration_index}_{event_id}"
            
            step_map[iteration_key] = {
                'name': f"{map_name} (Iteration {iteration_index + 1})",
                'type': 'MapIteration',
                'status': 'RUNNING',
                'startDate': timestamp,
                'stopDate': None,
                'input': iteration_details.get('input'),
                'output': None,
                'error': None,
                'eventId': event_id,
                'isMapIteration': True,
                'iterationIndex': iteration_index,
                'parentMapName': map_name
            }
            
            # Track iterations for the parent Map state
            if map_name not in map_iterations:
                map_iterations[map_name] = []
            map_iterations[map_name].append(iteration_key)
            
        elif event_type == 'MapIterationSucceeded':
            iteration_details = event.get('mapIterationSucceededEventDetails', {})
            map_name = iteration_details.get('name', 'Unknown')
            iteration_index = iteration_details.get('index', 0)
            
            # Find and update the corresponding iteration
            for step_key, step_data in step_map.items():
                if (step_data.get('parentMapName') == map_name and 
                    step_data.get('iterationIndex') == iteration_index and 
                    step_data['status'] == 'RUNNING'):
                    step_data['status'] = 'SUCCEEDED'
                    step_data['stopDate'] = timestamp
                    step_data['output'] = iteration_details.get('output')
                    break
                    
        elif event_type == 'MapIterationFailed':
            iteration_details = event.get('mapIterationFailedEventDetails', {})
            map_name = iteration_details.get('name', 'Unknown')
            iteration_index = iteration_details.get('index', 0)
            
            # Find and update the corresponding iteration
            for step_key, step_data in step_map.items():
                if (step_data.get('parentMapName') == map_name and 
                    step_data.get('iterationIndex') == iteration_index and 
                    step_data['status'] == 'RUNNING'):
                    step_data['status'] = 'FAILED'
                    step_data['stopDate'] = timestamp
                    step_data['error'] = iteration_details.get('error', 'Map iteration failed')
                    break
                    
        # Handle task failure events
        elif event_type == 'TaskFailed':
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
    
    # Second pass: enhance Map states with iteration information
    for step_key, step_data in step_map.items():
        if step_data.get('isMapState') and step_data['name'] in map_iterations:
            iterations = map_iterations[step_data['name']]
            step_data['mapIterations'] = len(iterations)
            step_data['mapIterationDetails'] = [step_map[iter_key] for iter_key in iterations if iter_key in step_map]
    
    # Convert to list and sort by start time
    steps = list(step_map.values())
    steps.sort(key=lambda x: x['startDate'] if x['startDate'] else '')
    
    # Clean up internal fields that shouldn't be exposed
    for step in steps:
        step.pop('eventId', None)
        step.pop('isMapState', None)
        step.pop('isMapIteration', None)
        step.pop('iterationIndex', None)
        step.pop('parentMapName', None)
    
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
