# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import json
import boto3
import os
import uuid
import urllib.request
import urllib.error
import time

sagemaker = boto3.client('sagemaker')
sts = boto3.client('sts')

def sanitize_name(name, max_length=63):
    """
    Convert a name to AWS-compliant format for HumanTaskUI
    Requirements:
    - Must be lowercase alphanumeric
    - Can contain hyphens only between alphanumeric characters
    - Maximum length of 63 characters
    """
    # Convert to lowercase
    name = name.lower()
    
    # Convert underscores to hyphens
    name = name.replace('_', '-')
    
    # Process the string character by character to ensure hyphens are only between alphanumeric
    result = []
    for i, char in enumerate(name):
        if char.isalnum():
            result.append(char)
        elif char == '-' and i > 0 and i < len(name) - 1:
            # Only add hyphen if it's between alphanumeric characters
            if name[i-1].isalnum() and name[i+1].isalnum():
                result.append(char)
    
    name = ''.join(result)
    
    # Ensure it's not empty
    if not name:
        name = 'default'
    
    # Ensure it starts with alphanumeric
    if not name[0].isalnum():
        name = 'a' + name
    
    # Truncate to max length while preserving word boundaries
    if len(name) > max_length:
        # Try to truncate at last hyphen before max_length
        last_hyphen = name.rfind('-', 0, max_length)
        if last_hyphen > 0:
            name = name[:last_hyphen]
        else:
            name = name[:max_length]
    
    return name

def generate_resource_names(stack_name):
    """
    Generate AWS-compliant names for A2I resources
    """
    base_name = sanitize_name(stack_name)
    return {
        'human_task_ui': f'{base_name}-hitl-ui',  # Keep hyphens for readability
        'flow_definition': f'{base_name}-hitl-fd'  # Keep hyphens for readability
    }

def get_account_id():
    """Get the current AWS account ID"""
    try:
        return sts.get_caller_identity()['Account']
    except Exception as e:
        print(f"Warning: Could not get account ID: {e}")
        return ""

def get_region():
    """Get the current AWS region"""
    return os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-west-2'))

def send_cfn_response(event, context, response_status, response_data, physical_resource_id=None, no_echo=False):
    """Send a response to CloudFormation to indicate success or failure"""
    response_url = event['ResponseURL']
    
    print(f"CFN response URL: {response_url}")
    
    response_body = {
        'Status': response_status,
        'Reason': f"See details in CloudWatch Log Stream: {context.log_stream_name}",
        'PhysicalResourceId': physical_resource_id or context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'NoEcho': no_echo,
        'Data': response_data
    }
    
    json_response_body = json.dumps(response_body)
    
    print(f"Response body: {json_response_body}")
    
    headers = {
        'content-type': '',
        'content-length': str(len(json_response_body))
    }
    
    try:
        response = urllib.request.Request(response_url, 
                                        data=json_response_body.encode('utf-8'),
                                        headers=headers,
                                        method='PUT')
        
        with urllib.request.urlopen(response) as response:
            print(f"Status code: {response.getcode()}")
            print(f"Status message: {response.msg}")
            
        return True
    except Exception as e:
        print(f"Error sending response to CloudFormation: {str(e)}")
        return False

def create_human_task_ui(human_task_ui_name):
    # human_task_ui_name = f'{stack_name}-bda-hitl-template'
    ui_template_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Document Review</title>
        <script src="https://assets.crowd.aws/crowd-html-elements.js"></script>
        <style>
            :root {
                --primary-color: #2E5D7D;
                --secondary-color: #F8F9FA;
                --accent-color: #FFD700;
            }

            body { 
                font-family: 'Arial', sans-serif; 
                margin: 0;
                height: 100vh;
                overflow: hidden;
            }
            .container { 
                display: flex; 
                height: 100vh;
            }
            .image-pane { 
                width: 60%; 
                padding: 20px;
                background: #f0f2f5;
                overflow: hidden;
                position: relative;
            }
            .review-pane { 
                width: 40%; 
                padding: 20px;
                display: flex;
                flex-direction: column;
                background: white;
            }
            .scroll-container {
                flex: 1;
                overflow-y: auto;
                padding-right: 10px;
            }
            .zoom-controls { 
                margin-bottom: 15px;
                display: flex;
                gap: 10px;
            }
            .document-info { 
                background: var(--secondary-color); 
                padding: 20px; 
                border-radius: 8px;
                margin-bottom: 20px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .key-value-pair { 
                margin-bottom: 20px; 
                padding: 15px; 
                border: 1px solid #e9ecef; 
                border-radius: 6px; 
                background: white;
                transition: transform 0.2s ease;
                cursor: pointer;
            }
            #documentImage { 
                max-width: 100%; 
                max-height: calc(100vh - 100px);
                cursor: crosshair; 
                border-radius: 4px; 
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            }
            .highlight-box {
                position: absolute;
                border: 2px solid var(--accent-color);
                background: rgba(255,215,0,0.15);
                pointer-events: none;
            }
            button {
                background: var(--primary-color);
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
                cursor: pointer;
                transition: opacity 0.2s;
            }
            button:hover { opacity: 0.85; }
            h3 { color: var(--primary-color); margin-top: 0; }
            .confidence-low { color: #dc3545; font-weight: 600; }
            .confidence-high { color: #28a745; font-weight: 600; }
        </style>
    </head>
    <body>
        <crowd-form>
            <div class="container">
                <!-- Image Pane -->
                <div class="image-pane">
                    <div class="zoom-controls">
                        <button type="button" onclick="zoom(1.1)">Zoom In (+)</button>
                        <button type="button" onclick="zoom(0.9)">Zoom Out (-)</button>
                    </div>
                    <img id="documentImage" 
                        src="{{ task.input.sourceDocument | grant_read_access }}" 
                        onload="initImage()">
                </div>

                <!-- Review Pane -->
                <div class="review-pane">
                    <div class="document-info">
                        <h3>Document Information</h3>
                        <p><strong>Current Blueprint:</strong> {{ task.input.blueprintName | escape }}</p>
                        <p><strong>Blueprint Confidence:</strong> {{ task.input.bp_confidence | round: 2 }}</p>
                        <p><strong>Confidence Threshold:</strong> {{ task.input.confidenceThreshold | round: 2 }}</p>
                        <p><strong>Page Number:</strong> {{ task.input.page_number }}</p>
                        <p><strong>Page Array:</strong> {{ task.input.page_array }}</p>
                        <p><strong>Execution ID:</strong> {{ task.input.execution_id }}</p>
                        <p><strong>Record ID:</strong> {{ task.input.record_id }}</p>

                        <!-- Dropdown for Blueprint Selection -->
                        <label for="blueprintSelection"><strong>Select Blueprint:</strong></label>
                        <select name="blueprintSelection" id="blueprintSelection" required disabled onchange="handleBlueprintChange()">
                            {% for option in task.input.blueprintOptions %}
                                <option value="{{ option.value | escape }}" {% if option.value == task.input.blueprintName %}selected{% endif %}>
                                    {{ option.label | escape }}
                                </option>
                            {% endfor %}
                        </select>
                    </div>

                    <!-- Scrollable Key Value Section -->
                    <div class="scroll-container">
                        <h3>Key Value Review</h3>
                        {% for pair in task.input.keyValuePairs %}
                            {% assign bbox_index = forloop.index0 %}
                            <div class="key-value-pair" 
                                data-key="{{ pair.key | escape }}" 
                                data-bbox="{{ task.input.boundingBoxes[bbox_index].bounding_box | to_json | escape }}"
                                onclick="highlightBBox(this)">
                                <label>{{ pair.key | escape }}</label>
                                <crowd-input 
                                    name="{{ pair.key | escape }}" 
                                    value="{{ pair.value | escape }}"
                                    required>
                                </crowd-input>
                                <p class="confidence-{% if pair.confidence < task.input.confidenceThreshold %}low{% else %}high{% endif %}">
                                    Confidence: {{ pair.confidence | round: 2 }}
                                </p>
                                {% if pair.value == "" %}
                                    <p style="color: #dc3545; margin: 5px 0 0 0; font-size: 0.9em;">
                                        ⚠️ Value missing - please verify
                                    </p>
                                {% endif %}
                            </div>
                        {% endfor %}
                    </div>

                    <crowd-button 
                        form-action="submit" 
                        variant="primary" 
                        style="margin-top: 20px; align-self: flex-end;">
                        Submit Review
                    </crowd-button>
                </div>
            </div>
        </crowd-form>

        <script>
            let currentZoom = 1;
            let currentHighlight = null;
            const imgElement = document.getElementById('documentImage');
            let imgRect = null;

            function initImage() {
                imgRect = imgElement.getBoundingClientRect();
            }

            function zoom(factor) {
                currentZoom *= factor;
                imgElement.style.transform = `scale(${currentZoom})`;
                imgElement.style.transformOrigin = 'top left';
                imgRect = imgElement.getBoundingClientRect();
            }

            function highlightBBox(element) {
                if(currentHighlight) currentHighlight.remove();
                
                const bbox = JSON.parse(element.dataset.bbox || '{}');
                if(bbox?.width > 0 && bbox?.height > 0) {
                    currentHighlight = document.createElement('div');
                    currentHighlight.className = 'highlight-box';

                    const scaleX = imgElement.naturalWidth / imgElement.offsetWidth;
                    const scaleY = imgElement.naturalHeight / imgElement.offsetHeight;

                    currentHighlight.style.left = `${bbox.left * imgElement.offsetWidth + imgRect.left}px`;
                    currentHighlight.style.top = `${bbox.top * imgElement.offsetHeight + imgRect.top}px`;
                    currentHighlight.style.width = `${bbox.width * imgElement.offsetWidth}px`;
                    currentHighlight.style.height = `${bbox.height * imgElement.offsetHeight}px`;

                    document.body.appendChild(currentHighlight);
                }
            }

            function handleBlueprintChange() {
            const dropdown = document.getElementById("blueprintSelection");
            const selectedBlueprint = dropdown.value;

            // Get initial blueprint from the template
            const initialBlueprint = "{{ task.input.blueprintName }}";

            // Disable all key-value pairs if blueprint is changed
            const keyValuePairs = document.querySelectorAll(".key-value-pair");
            if (selectedBlueprint !== initialBlueprint) {
                keyValuePairs.forEach(pair => {
                    pair.classList.add("disabled");
                    const input = pair.querySelector("crowd-input");
                    input.setAttribute("disabled", "true");
                });
            } else {
                keyValuePairs.forEach(pair => {
                    pair.classList.remove("disabled");
                    const input = pair.querySelector("crowd-input");
                    input.removeAttribute("disabled");
                });
            }
        }

            document.addEventListener('click', (e) => {
                if(!e.target.closest('.key-value-pair') && currentHighlight) {
                    currentHighlight.remove();
                    currentHighlight = null;
                }
            });

            window.addEventListener('resize', () => {
                imgRect = imgElement.getBoundingClientRect();
            });
        </script>
    </body>
    </html>
    """

    try:
        response = sagemaker.create_human_task_ui(
            HumanTaskUiName=human_task_ui_name,
            UiTemplate={
                'Content': ui_template_content
            }
        )
        return response['HumanTaskUiArn']
    except Exception as e:
        print(f"Error creating HumanTaskUI: {e}")
        return None


def create_flow_definition(stack_name, human_task_ui_arn, a2i_workteam_arn, flow_definition_name):
    role_arn = os.environ.get('A2I_FLOW_DEFINITION_ROLE_ARN')  # Use dedicated Flow Definition role
    try:
        response = sagemaker.create_flow_definition(
            FlowDefinitionName=flow_definition_name,
            HumanLoopConfig={
                'WorkteamArn': a2i_workteam_arn,
                'HumanTaskUiArn': human_task_ui_arn,
                'TaskTitle': 'Review Extracted Key Values',
                'TaskDescription': 'Review the key values extracted from the document.',
                'TaskCount': 1 
            },
            OutputConfig={
                'S3OutputPath': f's3://{os.environ["BDA_OUTPUT_BUCKET"]}/a2i-output' #Output to BDA Bucket
            },
            RoleArn=role_arn
        )
        return response['FlowDefinitionArn']
    except Exception as e:
        print(f"Error creating FlowDefinition: {e}")
        return None


def comprehensive_workforce_cleanup(workteam_name, stack_name):
    """
    Comprehensive cleanup of SageMaker workforce resources to prevent orphaned resources
    Handles all scenarios including orphaned workforces when workteam is already deleted
    """
    cleanup_results = []
    
    try:
        print(f"Starting comprehensive workforce cleanup for workteam: {workteam_name}")
        
        # Step 1: Clean up any remaining human loops
        try:
            # Use the sanitized flow definition name
            resource_names = generate_resource_names(stack_name)
            flow_definition_name = resource_names['flow_definition']
            
            # Try to list human loops (this might fail if flow definition is already deleted)
            try:
                response = sagemaker.list_human_loops(
                    FlowDefinitionArn=f'arn:aws:sagemaker:{get_region()}:{get_account_id()}:flow-definition/{flow_definition_name}',
                    MaxResults=100
                )
                
                for human_loop in response.get('HumanLoops', []):
                    if human_loop['HumanLoopStatus'] in ['InProgress', 'Waiting']:
                        try:
                            sagemaker.stop_human_loop(HumanLoopName=human_loop['HumanLoopName'])
                            cleanup_results.append(f"Stopped human loop: {human_loop['HumanLoopName']}")
                        except Exception as e:
                            cleanup_results.append(f"Warning: Could not stop human loop {human_loop['HumanLoopName']}: {e}")
                            
            except Exception as e:
                cleanup_results.append(f"Could not list human loops (flow definition may be deleted): {e}")
                
        except Exception as e:
            cleanup_results.append(f"Human loop cleanup failed: {e}")
        
        # Step 2: Wait for operations to settle
        print("Waiting for SageMaker operations to settle...")
        time.sleep(10)
        
        # Step 3: Check if workteam exists and try direct deletion
        workteam_exists = False
        try:
            sagemaker.describe_workteam(WorkteamName=workteam_name)
            workteam_exists = True
            print(f"Workteam {workteam_name} exists, attempting deletion")
            
            try:
                sagemaker.delete_workteam(WorkteamName=workteam_name)
                cleanup_results.append(f"Successfully deleted workteam: {workteam_name}")
                time.sleep(5)  # Wait for deletion to propagate
                
            except Exception as delete_error:
                cleanup_results.append(f"Direct workteam deletion failed: {delete_error}")
                
        except Exception as describe_error:
            if 'ValidationException' in str(describe_error):
                cleanup_results.append(f"Workteam {workteam_name} already deleted or doesn't exist")
                workteam_exists = False
            else:
                cleanup_results.append(f"Error describing workteam: {describe_error}")
                workteam_exists = False
        
        # Step 4: ALWAYS check for and clean up orphaned workforces
        # This is critical - we must check regardless of workteam status
        print("Checking for orphaned workforce resources...")
        try:
            workforces = sagemaker.list_workforces()
            
            for workforce in workforces.get('Workforces', []):
                workforce_name = workforce['WorkforceName']
                
                # Check if this is a private workforce
                if 'private' in workforce_name.lower():
                    try:
                        # Get workforce details to check if it's associated with our stack
                        workforce_details = sagemaker.describe_workforce(WorkforceName=workforce_name)
                        
                        # Multiple ways to identify if this workforce belongs to our stack:
                        # 1. Check if workteam name appears in workforce details
                        # 2. Check if stack name appears in workforce details  
                        # 3. Check workforce creation patterns
                        
                        workforce_str = str(workforce_details).lower()
                        stack_name_lower = stack_name.lower()
                        workteam_name_lower = workteam_name.lower()
                        
                        is_our_workforce = (
                            workteam_name_lower in workforce_str or
                            stack_name_lower in workforce_str or
                            # Check for common naming patterns
                            f"{stack_name_lower}-private" in workforce_name.lower() or
                            # Check if workforce was created around the same time as our stack
                            # (This is a heuristic but helps identify orphaned resources)
                            workforce_name.lower().startswith('private-crowd')
                        )
                        
                        if is_our_workforce:
                            print(f"Found associated workforce: {workforce_name}")
                            cleanup_results.append(f"Found workforce associated with our stack: {workforce_name}")
                            
                            # Check if workforce has any remaining workteams
                            try:
                                # If workteam still exists, we already tried to delete it above
                                # If workteam doesn't exist, we can safely delete the workforce
                                if not workteam_exists:
                                    print(f"Workteam already deleted, cleaning up orphaned workforce: {workforce_name}")
                                    sagemaker.delete_workforce(WorkforceName=workforce_name)
                                    cleanup_results.append(f"Deleted orphaned workforce: {workforce_name}")
                                    time.sleep(5)
                                    break
                                else:
                                    # Workteam exists but deletion might have failed, try workforce deletion as fallback
                                    print(f"Attempting workforce-level cleanup for: {workforce_name}")
                                    sagemaker.delete_workforce(WorkforceName=workforce_name)
                                    cleanup_results.append(f"Deleted workforce (workteam deletion fallback): {workforce_name}")
                                    time.sleep(5)
                                    break
                                    
                            except Exception as workforce_delete_error:
                                cleanup_results.append(f"Could not delete workforce {workforce_name}: {workforce_delete_error}")
                                continue
                        else:
                            cleanup_results.append(f"Skipped unrelated workforce: {workforce_name}")
                            
                    except Exception as workforce_describe_error:
                        cleanup_results.append(f"Could not describe workforce {workforce_name}: {workforce_describe_error}")
                        
                        # If we can't describe it, but it's a private workforce, try to delete it anyway
                        # This handles cases where the workforce is in a bad state
                        if 'private-crowd' in workforce_name.lower():
                            try:
                                print(f"Attempting cleanup of potentially orphaned workforce: {workforce_name}")
                                sagemaker.delete_workforce(WorkforceName=workforce_name)
                                cleanup_results.append(f"Deleted potentially orphaned workforce: {workforce_name}")
                                time.sleep(5)
                                break
                            except Exception as fallback_delete_error:
                                cleanup_results.append(f"Could not delete potentially orphaned workforce {workforce_name}: {fallback_delete_error}")
                        continue
                        
        except Exception as workforce_list_error:
            cleanup_results.append(f"Workforce listing/cleanup failed: {workforce_list_error}")
        
        # Step 5: Final verification - check both workteam and workforce status
        print("Performing final verification...")
        try:
            time.sleep(5)
            sagemaker.describe_workteam(WorkteamName=workteam_name)
            cleanup_results.append(f"Warning: Workteam {workteam_name} still exists after cleanup attempts")
        except Exception:
            cleanup_results.append(f"Verification: Workteam {workteam_name} successfully removed")
        
        # Also verify no orphaned workforces remain
        try:
            remaining_workforces = sagemaker.list_workforces()
            private_workforces = [w for w in remaining_workforces.get('Workforces', []) 
                                if 'private' in w['WorkforceName'].lower()]
            
            if private_workforces:
                cleanup_results.append(f"Note: {len(private_workforces)} private workforce(s) still exist in account")
                for wf in private_workforces:
                    cleanup_results.append(f"  - Remaining workforce: {wf['WorkforceName']}")
            else:
                cleanup_results.append("Verification: No private workforces remain in account")
                
        except Exception as verification_error:
            cleanup_results.append(f"Could not verify workforce cleanup: {verification_error}")
        
        print("Workforce cleanup completed")
        print("Cleanup results:", cleanup_results)
        return cleanup_results
        
    except Exception as e:
        error_msg = f"Comprehensive workforce cleanup failed: {e}"
        cleanup_results.append(error_msg)
        print(error_msg)
        return cleanup_results


def delete_flow_definition(flow_definition_name):
    try:
        sagemaker.delete_flow_definition(FlowDefinitionName=flow_definition_name)
        print(f"Flow Definition '{flow_definition_name}' deleted successfully.")
    except Exception as e:
        print(f"Error deleting Flow Definition '{flow_definition_name}': {e}")


def delete_human_task_ui(human_task_ui_name):
    try:
        sagemaker.delete_human_task_ui(HumanTaskUiName=human_task_ui_name)
        print(f"HumanTaskUI '{human_task_ui_name}' deleted successfully.")
    except Exception as e:
        print(f"Error deleting HumanTaskUI '{human_task_ui_name}': {e}")

def handler(event, context):
    stack_name = os.environ['STACK_NAME']
    a2i_workteam_arn = os.environ['A2I_WORKTEAM_ARN']
    
    # Generate AWS-compliant resource names
    resource_names = generate_resource_names(stack_name)
    human_task_ui_name = resource_names['human_task_ui']
    flow_definition_name = resource_names['flow_definition']
    
    ssm = boto3.client('ssm')
    
    # For debugging
    print(f"Event received: {json.dumps(event)}")
    print(f"Using AWS-compliant names: HumanTaskUI={human_task_ui_name}, FlowDefinition={flow_definition_name}")
    
    response_data = {}
    
    try:
        # Handle CloudFormation lifecycle events
        if event.get('RequestType') == 'Create':
            print("Creating A2I Resources...")
            # Ignore the SourceCodeHash property as it's only used to force updates
            _ = event['ResourceProperties'].get('SourceCodeHash')
            human_task_ui_arn = create_human_task_ui(human_task_ui_name)
            if human_task_ui_arn:
                flow_definition_arn = create_flow_definition(stack_name, human_task_ui_arn, a2i_workteam_arn,flow_definition_name)
                if flow_definition_arn:
                    # Store the Flow Definition ARN in SSM
                    ssm.put_parameter(
                        Name=f"/{stack_name}/FlowDefinitionArn",
                        Value=flow_definition_arn,
                        Type='String',
                        Overwrite=True
                    )
                    
                    # Create HITL confidence threshold SSM parameter with default value 80
                    try:
                        ssm.put_parameter(
                            Name=f"/{stack_name}/hitl_confidence_threshold",
                            Value="80",
                            Type='String',
                            Overwrite=True,
                            Description="HITL confidence threshold for Pattern-1 BDA processing"
                        )
                        print(f"Created SSM parameter /{stack_name}/hitl_confidence_threshold with default value 80")
                    except Exception as e:
                        print(f"Warning: Failed to create HITL confidence threshold SSM parameter: {e}")
                        # Don't fail the entire operation if SSM parameter creation fails
                    
                    response_data['HumanTaskUiArn'] = human_task_ui_arn
                    response_data['FlowDefinitionArn'] = flow_definition_arn
                    send_cfn_response(event, context, 'SUCCESS', response_data)
                else:
                    print("Failed to create flow definition")
                    send_cfn_response(event, context, 'FAILED', {'Error': 'Failed to create flow definition'})
                    return
            else:
                print("Failed to create human task UI")
                send_cfn_response(event, context, 'FAILED', {'Error': 'Failed to create human task UI'})
                return
        
        elif event.get('RequestType') == 'Update':
            print("Updating A2I Resources...")
            # Ignore the SourceCodeHash property as it's only used to force updates
            _ = event['ResourceProperties'].get('SourceCodeHash')
            delete_flow_definition(flow_definition_name)
            delete_human_task_ui(human_task_ui_name)
            
            human_task_ui_arn = create_human_task_ui(stack_name)
            if human_task_ui_arn:
                flow_definition_arn = create_flow_definition(stack_name, human_task_ui_arn, a2i_workteam_arn, flow_definition_name)
                if flow_definition_arn:
                    # Store the Flow Definition ARN in SSM
                    ssm.put_parameter(
                        Name=f"/{stack_name}/FlowDefinitionArn",
                        Value=flow_definition_arn,
                        Type='String',
                        Overwrite=True
                    )
                    response_data['HumanTaskUiArn'] = human_task_ui_arn
                    response_data['FlowDefinitionArn'] = flow_definition_arn
                    send_cfn_response(event, context, 'SUCCESS', response_data)
                else:
                    print("Failed to update flow definition")
                    send_cfn_response(event, context, 'FAILED', {'Error': 'Failed to update flow definition'})
                    return
            else:
                print("Failed to update human task UI")
                send_cfn_response(event, context, 'FAILED', {'Error': 'Failed to update human task UI'})
                return
                
        elif event.get('RequestType') == 'Delete':
            print("Deleting A2I Resources...")
            
            # Step 1: Delete Flow Definition and Human Task UI first
            delete_flow_definition(flow_definition_name)
            delete_human_task_ui(human_task_ui_name)
            # sagemaker.delete_workforce(WorkforceName='default')
            
            # Step 2: Perform comprehensive workforce cleanup
            # Extract workteam name from environment or construct it
            workteam_arn = os.environ.get('A2I_WORKTEAM_ARN', '')
            if workteam_arn:
                # Extract workteam name from ARN
                workteam_name = workteam_arn.split('/')[-1] if '/' in workteam_arn else ''
                if workteam_name:
                    print(f"Performing workforce cleanup for workteam: {workteam_name}")
                    cleanup_results = comprehensive_workforce_cleanup(workteam_name, stack_name)
                    print(f"Workforce cleanup completed with results: {len(cleanup_results)} operations")
                else:
                    print("Could not extract workteam name from ARN")
            else:
                print("No workteam ARN found in environment - skipping workforce cleanup")
            
            print("Success in deleting all A2I resources (Flow Definition, Human Task UI, and Workforce)")
            send_cfn_response(event, context, 'SUCCESS', {})
            return
            
        # In case RequestType is not provided or recognized
        else:
            print(f"Unknown RequestType: {event.get('RequestType')}")
            send_cfn_response(event, context, 'FAILED', {'Error': f"Unknown RequestType: {event.get('RequestType')}"})
            return
    except Exception as e:
        print(f"Error: {str(e)}")
        send_cfn_response(event, context, 'FAILED', {'Error': str(e)})
        return