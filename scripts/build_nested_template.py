#!/usr/bin/env python3
"""
Build complete nested AppSync template by extracting resources from main template
"""

import re
from pathlib import Path

# Read main template
with open('template.yaml', 'r') as f:
    lines = f.readlines()

# Resource name mappings - convert directory names to CloudFormation resource names
LAMBDA_FUNCTIONS = {
    'abort_workflow_resolver': 'AbortWorkflowResolverFunction',
    'agent_chat_resolver': 'AgentChatResolverFunction',
    'agent_request_handler': 'AgentRequestHandlerFunction',
    'chat_with_document_resolver': 'ChatWithDocumentResolverFunction',
    'configuration_resolver': 'ConfigurationResolverFunction',
    'copy_to_baseline_resolver': 'CopyToBaselineResolverFunction',
    'create_document_resolver': 'CreateDocumentResolverFunction',
    'delete_agent_chat_session_resolver': 'DeleteAgentChatSessionFunction',
    'delete_document_resolver': 'DeleteDocumentResolverFunction',
    'delete_tests': 'DeleteTestsResolverFunction',
    'discovery_upload_resolver': 'DiscoveryUploadResolverFunction',
    'get_agent_chat_messages_resolver': 'GetAgentChatMessagesFunction',
    'get_file_contents_resolver': 'GetFileContentsResolverFunction',
    'get_stepfunction_execution_resolver': 'GetStepFunctionExecutionResolverFunction',
    'ipset_updater': 'IPSetUpdaterFunction',
    'list_agent_chat_sessions_resolver': 'ListAgentChatSessionsFunction',
    'list_available_agents': 'ListAvailableAgentsFunction',
    'process_changes_resolver': 'ProcessChangesResolverFunction',
    'query_knowledgebase_resolver': 'QueryKnowledgeBaseResolverFunction',
    'reprocess_document_resolver': 'ReprocessDocumentResolverFunction',
    'sync_bda_idp_resolver': 'SyncBdaIdpResolverFunction',
    'test_results_resolver': 'TestResultsResolverFunction',
    'test_runner': 'TestRunnerFunction',
    'test_set_resolver': 'TestSetResolverFunction',
    'upload_resolver': 'UploadResolverFunction',
}

def extract_resource_block(lines, resource_name, start_indent=2):
    """Extract a complete resource block from template lines"""
    # Find the resource start
    resource_pattern = f'^{" " * start_indent}{resource_name}:\s*$'
    start_idx = None
    
    for i, line in enumerate(lines):
        if re.match(resource_pattern, line):
            start_idx = i
            break
    
    if start_idx is None:
        return None
    
    # Extract lines until we hit another resource at same indent level
    result_lines = [lines[start_idx]]
    i = start_idx + 1
    
    while i < len(lines):
        line = lines[i]
        # Check if this is a new resource at same indent (not more indented and not blank/comment)
        if line.strip() and not line.strip().startswith('#'):
            # Count leading spaces
            leading_spaces = len(line) - len(line.lstrip())
            if leading_spaces <= start_indent and line.strip() != '':
                break
        result_lines.append(line)
        i += 1
    
    return ''.join(result_lines)

# Extract all resources
output = []
output.append("# Lambda Functions, LogGroups, DataSources, and Resolvers\n")

for func_dir, func_name in LAMBDA_FUNCTIONS.items():
    print(f"Extracting {func_name}...")
    
    # Extract LogGroup (comes before Function usually)
    loggroup_name = f"{func_name.replace('Function', '')}LogGroup"
    if 'Function' not in loggroup_name:
        loggroup_name = f"{func_name}LogGroup"
    
    loggroup = extract_resource_block(lines, loggroup_name)
    if loggroup:
        output.append(f"\n  # LogGroup for {func_dir}\n")
        output.append(loggroup)
    
    # Extract Function
    function = extract_resource_block(lines, func_name)
    if function:
        output.append(f"\n  # Function: {func_dir}\n")
        output.append(function)
    
    # Extract DataSource
    datasource_name = f"{func_name.replace('Function', '')}DataSource"
    datasource = extract_resource_block(lines, datasource_name)
    if datasource:
        output.append(f"\n  # DataSource for {func_dir}\n")
        output.append(datasource)

# Write output
output_file = Path('nested/appsync/extracted_resources.yaml')
with open(output_file, 'w') as f:
    f.write(''.join(output))

print(f"\nExtracted resources written to {output_file}")
print(f"Total lines: {len(output)}")