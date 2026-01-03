#!/usr/bin/env python3
"""
Extract AppSync resources from main template.yaml for nested stack migration
"""

import re
import yaml
from pathlib import Path

# List of 25 Lambda functions to extract
FUNCTIONS_TO_EXTRACT = [
    'abort_workflow_resolver',
    'agent_chat_resolver',
    'agent_request_handler',
    'chat_with_document_resolver',
    'configuration_resolver',
    'copy_to_baseline_resolver',
    'create_document_resolver',
    'delete_agent_chat_session_resolver',
    'delete_document_resolver',
    'delete_tests',
    'discovery_upload_resolver',
    'get_agent_chat_messages_resolver',
    'get_file_contents_resolver',
    'get_stepfunction_execution_resolver',
    'ipset_updater',
    'list_agent_chat_sessions_resolver',
    'list_available_agents',
    'process_changes_resolver',
    'query_knowledgebase_resolver',
    'reprocess_document_resolver',
    'sync_bda_idp_resolver',
    'test_results_resolver',
    'test_runner',
    'test_set_resolver',
    'upload_resolver',
]

# Read template
template_path = Path('template.yaml')
with open(template_path, 'r') as f:
    content = f.read()

# Find all resource names that match our functions
extracted_resources = {}

# Pattern to match CloudFormation resource names (CamelCase from directory names)
for func_dir in FUNCTIONS_TO_EXTRACT:
    # Convert snake_case to potential CamelCase names
    parts = func_dir.split('_')
    # Try different CamelCase variations
    potential_names = [
        ''.join(word.capitalize() for word in parts) + 'Function',
        ''.join(word.capitalize() for word in parts) + 'FunctionLogGroup',
        ''.join(word.capitalize() for word in parts) + 'DataSource',
    ]
    
    for name in potential_names:
        # Search for this resource name in the template
        pattern = rf'^  {name}:\s*$'
        if re.search(pattern, content, re.MULTILINE):
            print(f"Found: {name}")

print("\n=== Summary ===")
print(f"Searched for {len(FUNCTIONS_TO_EXTRACT)} functions")