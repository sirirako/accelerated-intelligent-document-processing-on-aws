#!/usr/bin/env python3
"""
Generate complete nested AppSync template by extracting and transforming resources from main template
"""

import re
from pathlib import Path

def extract_resource_block(lines, resource_name, start_idx=0):
    """Extract a complete resource block starting from start_idx"""
    resource_pattern = rf'^\s{{2}}{resource_name}:\s*$'
    found_idx = None
    
    for i in range(start_idx, len(lines)):
        if re.match(resource_pattern, lines[i]):
            found_idx = i
            break
    
    if found_idx is None:
        return None, -1
    
    # Extract until next resource at same indent (2 spaces)
    result = [lines[found_idx]]
    i = found_idx + 1
    
    while i < len(lines):
        line = lines[i]
        # Stop if we hit another resource at indent level 2
        if re.match(r'^\s{2}[A-Z][a-zA-Z0-9]+:', line):
            break
        result.append(line)
        i += 1
    
    return ''.join(result), i

def transform_resource(resource_text):
    """Transform resource text to work in nested stack"""
    # Replace !GetAtt GraphQLApi.ApiId with !Ref GraphQLApiId
    resource_text = re.sub(r'!GetAtt GraphQLApi\.ApiId', '!Ref GraphQLApiId', resource_text)
    
    # Replace !GetAtt GraphQLApi.Arn with !Ref GraphQLApiArn
    resource_text = re.sub(r'!GetAtt GraphQLApi\.Arn', '!Ref GraphQLApiArn', resource_text)
    
    # Replace !GetAtt GraphQLApi.GraphQLUrl with !Ref GraphQLApiUrl
    resource_text = re.sub(r'!GetAtt GraphQLApi\.GraphQLUrl', '!Ref GraphQLApiUrl', resource_text)
    
    # Replace table !Ref with parameter names
    table_replacements = {
        '!Ref TrackingTable': '!Ref TrackingTableName',
        '!Ref ConfigurationTable': '!Ref ConfigurationTableName',
        '!Ref AgentTable': '!Ref AgentTableName',
        '!Ref ChatMessagesTable': '!Ref ChatMessagesTableName',
        '!Ref ChatSessionsTable': '!Ref ChatSessionsTableName',
        '!Ref DiscoveryTrackingTable': '!Ref DiscoveryTrackingTableName',
    }
    
    for old, new in table_replacements.items():
        resource_text = resource_text.replace(old, new)
    
    # Replace bucket !Ref with parameter names
    bucket_replacements = {
        '!Ref InputBucket': '!Ref InputBucketName',
        '!Ref OutputBucket': '!Ref OutputBucketName',
        '!Ref ConfigurationBucket': '!Ref ConfigurationBucketName',
        '!Ref WorkingBucket': '!Ref WorkingBucketName',
        '!Ref DiscoveryBucket': '!Ref DiscoveryBucketName',
        '!Ref TestSetBucket': '!Ref TestSetBucketName',
    }
    
    for old, new in bucket_replacements.items():
        resource_text = resource_text.replace(old, new)
    
    # Replace queue references
    queue_replacements = {
        '!Ref DocumentQueue': '!Ref DocumentQueueUrl',
        '!Ref DiscoveryQueue': '!Ref DiscoveryQueueUrl',
        '!Ref TestFileCopyQueue': '!Ref TestFileCopyQueueUrl',
        '!Ref TestSetFileCopyQueue': '!Ref TestSetFileCopyQueueUrl',
        '!Ref TestResultCacheUpdateQueue': '!Ref TestResultCacheUpdateQueueUrl',
    }
    
    for old, new in queue_replacements.items():
        resource_text = resource_text.replace(old, new)
    
    # Replace !GetAtt QueueName with parsed QueueName from URL parameter
    resource_text = re.sub(
        r'QueueName: !GetAtt DocumentQueue\.QueueName',
        'QueueName: !Select [5, !Split ["/", !Ref DocumentQueueUrl]]',
        resource_text
    )
    resource_text = re.sub(
        r'QueueName: !GetAtt DiscoveryQueue\.QueueName',
        'QueueName: !Select [5, !Split ["/", !Ref DiscoveryQueueUrl]]',
        resource_text
    )
    resource_text = re.sub(
        r'QueueName: !GetAtt TestFileCopyQueue\.QueueName',
        'QueueName: !Select [5, !Split ["/", !Ref TestFileCopyQueueUrl]]',
        resource_text
    )
    resource_text = re.sub(
        r'QueueName: !GetAtt TestSetFileCopyQueue\.QueueName',
        'QueueName: !Select [5, !Split ["/", !Ref TestSetFileCopyQueueUrl]]',
        resource_text
    )
    
    # Replace Queue: !GetAtt with URL parameter for Events
    resource_text = re.sub(
        r'Queue: !GetAtt TestResultCacheUpdateQueue\.Arn',
        'Queue: !Ref TestResultCacheUpdateQueueUrl',
        resource_text
    )
    
    # Replace Resource: !GetAtt Queue.Arn with constructed ARN
    resource_text = re.sub(
        r'Resource: !GetAtt TestResultCacheUpdateQueue\.Arn',
        'Resource: !Sub "arn:${AWS::Partition}:sqs:${AWS::Region}:${AWS::AccountId}:${TestResultCacheUpdateQueueUrl}"',
        resource_text
    )
    
    # Replace !GetAtt CustomerManagedEncryptionKey.Arn with parameter
    resource_text = re.sub(
        r'!GetAtt CustomerManagedEncryptionKey\.Arn',
        '!Ref CustomerManagedEncryptionKeyArn',
        resource_text
    )
    
    # Replace !Ref AWS::StackName with !Ref StackName
    resource_text = resource_text.replace('!Ref AWS::StackName', '!Ref StackName')
    
    # Fix CodeUri paths - change src/lambda to ./src/lambda
    resource_text = re.sub(r'CodeUri: src/lambda/', 'CodeUri: ./src/lambda/', resource_text)
    resource_text = re.sub(r'CodeUri: \./src/lambda/', 'CodeUri: ./src/lambda/', resource_text)
    
    # Replace !Ref AgentChatProcessorFunction with parameter
    resource_text = resource_text.replace(
        '!Ref AgentChatProcessorFunction',
        '!Ref AgentChatProcessorFunctionArn'
    )
    resource_text = resource_text.replace(
        '!GetAtt AgentChatProcessorFunction.Arn',
        '!Ref AgentChatProcessorFunctionArn'
    )
    
    # Replace !Ref AgentProcessorFunction with parameter
    resource_text = resource_text.replace(
        '!Ref AgentProcessorFunction',
        '!Ref AgentProcessorFunctionArn'
    )
    resource_text = resource_text.replace(
        '!GetAtt AgentProcessorFunction.Arn',
        '!Ref AgentProcessorFunctionArn'
    )
    
    # Replace SaveReportingDataFunction
    resource_text = resource_text.replace(
        '!Ref SaveReportingDataFunction',
        '!Ref SaveReportingFunctionName'
    )
    resource_text = resource_text.replace(
        '!GetAtt SaveReportingDataFunction.Arn',
        '!Sub "arn:${AWS::Partition}:lambda:${AWS::Region}:${AWS::AccountId}:function:${SaveReportingFunctionName}"'
    )
    
    # Replace Lookup function references
    resource_text = resource_text.replace(
        '!Ref LookupFunction',
        '!Ref LookupFunctionName'
    )
    
    # Replace ReportingDatabase
    resource_text = resource_text.replace(
        '!Ref ReportingDatabase',
        '!Ref ReportingDatabaseName'
    )
    
    # Replace condition names
    resource_text = resource_text.replace('HasGuardrailConfig', 'HasGuardrail')
    resource_text = resource_text.replace('ShouldUseDocumentKnowledgeBase', 'UseDocumentKnowledgeBase')
    resource_text = resource_text.replace('IsPattern1', 'IsPattern1Enabled')
    resource_text = resource_text.replace('HasPattern1BDAProjectArn', 'HasBDAProjectArn')
    
    # Remove references to PATTERN*STACK outputs - use StateMachineName parameter instead
    resource_text = re.sub(
        r'!GetAtt PATTERN3STACK\.Outputs\.StateMachineName',
        '!Ref StateMachineName',
        resource_text
    )
    resource_text = re.sub(
        r'!GetAtt PATTERN2STACK\.Outputs\.StateMachineName',
        '!Ref StateMachineName',
        resource_text
    )
    resource_text = re.sub(
        r'!GetAtt PATTERN1STACK\.Outputs\.StateMachineName',
        '!Ref StateMachineName',
        resource_text
    )
    
    # Replace PATTERN*STACK references inside !Sub expressions
    resource_text = re.sub(
        r'\$\{PATTERN3STACK\.Outputs\.StateMachineName\}',
        '${StateMachineName}',
        resource_text
    )
    resource_text = re.sub(
        r'\$\{PATTERN2STACK\.Outputs\.StateMachineName\}',
        '${StateMachineName}',
        resource_text
    )
    resource_text = re.sub(
        r'\$\{PATTERN1STACK\.Outputs\.StateMachineName\}',
        '${StateMachineName}',
        resource_text
    )
    
    # Replace DOCUMENTKB.Outputs.KnowledgeBaseID with parameter
    resource_text = re.sub(
        r'\$\{DOCUMENTKB\.Outputs\.KnowledgeBaseID\}',
        '${KnowledgeBaseId}',
        resource_text
    )
    resource_text = re.sub(
        r'!GetAtt DOCUMENTKB\.Outputs\.KnowledgeBaseID',
        '!Ref KnowledgeBaseId',
        resource_text
    )
    
    # Replace !If conditions on bucket names with parameter names (multiline pattern)
    resource_text = re.sub(
        r'!If\s*\[\s*ShouldCreateEvaluationBaselineBucket,\s*!Ref EvaluationBaselineBucket,\s*!Ref EvaluationBaselineBucketName\s*\]',
        '!Ref EvaluationBaselineBucketName',
        resource_text,
        flags=re.DOTALL
    )
    resource_text = re.sub(
        r'!If\s*\[\s*ShouldCreateReportingBucket,\s*!Ref ReportingBucket,\s*!Ref ReportingBucketName\s*\]',
        '!Ref ReportingBucketName',
        resource_text,
        flags=re.DOTALL
    )
    
    # Replace any remaining direct bucket references
    resource_text = resource_text.replace('!Ref EvaluationBaselineBucket', '!Ref EvaluationBaselineBucketName')
    resource_text = resource_text.replace('!Ref ReportingBucket', '!Ref ReportingBucketName')
    
    # Replace WAFLambdaServiceIPSet reference (WAF resource stays in main template)
    # IPSetUpdaterFunction shouldn't be in nested stack - it's WAF-related, not AppSync
    resource_text = re.sub(
        r'!GetAtt WAFLambdaServiceIPSet\.Arn',
        '!Sub "arn:${AWS::Partition}:wafv2:${AWS::Region}:${AWS::AccountId}:regional/ipset/${StackName}-lambda-service-ips/PLACEHOLDER"',
        resource_text
    )
    
    # Replace bucket !GetAtt with constructed ARN using parameter
    resource_text = re.sub(
        r'!GetAtt ReportingBucket\.Arn',
        '!Sub "arn:${AWS::Partition}:s3:::${ReportingBucketName}"',
        resource_text
    )
    resource_text = re.sub(
        r'!GetAtt EvaluationBaselineBucket\.Arn',
        '!Sub "arn:${AWS::Partition}:s3:::${EvaluationBaselineBucketName}"',
        resource_text
    )
    
    # Replace BDASAMPLEPROJECT references with parameter
    resource_text = re.sub(
        r'!GetAtt BDASAMPLEPROJECT\.Outputs\.ProjectArn',
        '!Ref Pattern1BDAProjectArn',
        resource_text
    )
    
    # Replace ExternalMCPAgentsSecret with constructed ARN
    resource_text = re.sub(
        r'!Ref ExternalMCPAgentsSecret',
        '!Sub "arn:${AWS::Partition}:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:${StackName}/external-mcp-agents/credentials-??????"',
        resource_text
    )
    
    return resource_text

# Read main template
with open('template.yaml', 'r') as f:
    lines = f.readlines()

# Read the partial nested template we started
with open('nested/appsync/template.yaml', 'r') as f:
    partial_content = f.read()

# Find where Resources section starts in partial template
resources_marker = 'Resources:'
resources_idx = partial_content.find(resources_marker)
if resources_idx == -1:
    print("ERROR: Could not find Resources: section")
    exit(1)

# Keep everything up to and including "Resources:\n"
header = partial_content[:resources_idx + len(resources_marker) + 1]

# All resource names to extract
ALL_RESOURCES = [
    'GraphQLSchema',
    'AppSyncServiceRole',
    'TrackingTableDataSource',
    'DiscoveryTableDataSource',
    'ChatMessagesDataSource',
    'AgentTableDataSource',
    'NoneDataSource',
    # Lambda functions and their resources
    'AbortWorkflowResolverFunctionLogGroup',
    'AbortWorkflowResolverFunction',
    'AbortWorkflowDataSource',
    'AbortWorkflowResolver',
    'AgentChatResolverLogGroup',
    'AgentChatResolverFunction',
    'AgentChatResolverDataSource',
    'AgentChatDataSource',
    'SendAgentChatMessageResolver',
    'OnAgentChatMessageUpdateResolver',
    'AgentRequestHandlerLogGroup',
    'AgentRequestHandlerFunction',
    'AgentRequestHandlerDataSource',
    'SubmitAgentQueryResolver',
    'ChatWithDocumentResolverFunctionLogGroup',
    'ChatWithDocumentResolverFunction',
    'ChatWithDocumentDataSource',
    'ChatWithDocumentResolver',
    'ConfigurationResolverFunctionLogGroup',
    'ConfigurationResolverFunction',
    'ConfigurationDataSource',
    'GetConfigurationResolver',
    'UpdateConfigurationResolver',
    'ListConfigurationLibraryResolver',
    'GetConfigurationLibraryFileResolver',
    'GetPricingResolver',
    'UpdatePricingResolver',
    'RestoreDefaultPricingResolver',
    'CopyToBaselineResolverFunctionLogGroup',
    'CopyToBaselineResolverFunction',
    'CopyToBaselineDataSource',
    'CopyToBaselineResolver',
    'CreateDocumentResolverFunctionLogGroup',
    'CreateDocumentResolverFunction',
    'CreateDocumentDataSource',
    'CreateDocumentResolver',
    'DeleteAgentChatSessionFunctionLogGroup',
    'DeleteAgentChatSessionFunction',
    'DeleteAgentChatSessionDataSource',
    'DeleteChatSessionResolver',
    'DeleteDocumentResolverFunctionLogGroup',
    'DeleteDocumentResolverFunction',
    'DeleteDocumentDataSource',
    'DeleteDocumentResolver',
    'DeleteTestsResolverFunctionLogGroup',
    'DeleteTestsResolverFunction',
    'DeleteTestsDataSource',
    'DeleteTestsResolver',
    'DiscoveryUploadResolverFunctionLogGroup',
    'DiscoveryUploadResolverFunction',
    'DiscoveryUploadResolverDataSource',
    'DiscoveryUploadDocumentResolver',
    'DiscoveryJobsResolver',
    'UpdateDiscoveryJobStatusResolver',
    'GetAgentChatMessagesFunctionLogGroup',
    'GetAgentChatMessagesFunction',
    'GetAgentChatMessagesDataSource',
    'GetChatMessagesResolver',
    'GetFileContentsResolverFunctionLogGroup',
    'GetFileContentsResolverFunction',
    'GetFileContentsDataSource',
    'GetFileContentsResolver',
    'GetStepFunctionExecutionResolverFunctionLogGroup',
    'GetStepFunctionExecutionResolverFunction',
    'GetStepFunctionExecutionDataSource',
    'GetStepFunctionExecutionResolver',
    'ListAgentChatSessionsFunctionLogGroup',
    'ListAgentChatSessionsFunction',
    'ListAgentChatSessionsDataSource',
    'ListChatSessionsResolver',
    'ListAvailableAgentsLogGroup',
    'ListAvailableAgentsFunction',
    'ListAvailableAgentsDataSource',
    'ListAvailableAgentsResolver',
    'ProcessChangesResolverFunctionLogGroup',
    'ProcessChangesResolverFunction',
    'ProcessChangesDataSource',
    'ProcessChangesResolver',
    'QueryKnowledgeBaseResolverFunctionLogGroup',
    'QueryKnowledgeBaseResolverFunction',
    'QueryKnowledgeBaseDataSource',
    'QueryKnowledgeBaseResolver',
    'ReprocessDocumentResolverFunctionLogGroup',
    'ReprocessDocumentResolverFunction',
    'ReprocessDocumentDataSource',
    'ReprocessDocumentResolver',
    'SyncBdaIdpResolverFunctionLogGroup',
    'SyncBdaIdpResolverFunction',
    'SyncBdaIdpDataSource',
    'SyncBdaIdpResolver',
    'TestResultsResolverFunctionLogGroup',
    'TestResultsResolverFunction',
    'TestResultsDataSource',
    'GetTestRunsResolver',
    'CompareTestRunsResolver',
    'GetTestRunResolver',
    'GetTestRunStatusResolver',
    'TestRunnerFunctionLogGroup',
    'TestRunnerFunction',
    'TestRunnerDataSource',
    'TestRunnerResolver',
    'TestSetResolverFunctionLogGroup',
    'TestSetResolverFunction',
    'TestSetDataSource',
    'AddTestSetResolver',
    'AddTestSetFromUploadResolver',
    'DeleteTestSetsResolver',
    'GetTestSetsResolver',
    'ListBucketFilesResolver',
    'ValidateTestFileNameResolver',
    'UploadResolverFunctionLogGroup',
    'UploadResolverFunction',
    'UploadResolverDataSource',
    'UploadDocumentResolver',
    # Additional resolvers
    'UpdateDocumentResolver',
    'GetDocumentResolver',
    'ListDocumentResolver',
    'ListDocumentDateHourResolver',
    'ListDocumentDateShardResolver',
    'GetAgentJobStatusResolver',
    'ListAgentJobsResolver',
    'UpdateAgentJobStatusResolver',
    'DeleteAgentJobResolver',
]

print(f"Will extract {len(ALL_RESOURCES)} resources")

# Read main template
with open('template.yaml', 'r') as f:
    lines = f.readlines()

# Extract each resource
extracted = []
not_found = []

for resource_name in ALL_RESOURCES:
    resource_block, _ = extract_resource_block(lines, resource_name)
    if resource_block:
        # Transform the resource
        transformed = transform_resource(resource_block)
        extracted.append(f"\n  ##########################################################################\n")
        extracted.append(f"  # {resource_name}\n")
        extracted.append(f"  ##########################################################################\n")
        extracted.append(transformed)
        print(f"✓ Extracted: {resource_name}")
    else:
        not_found.append(resource_name)
        print(f"✗ Not found: {resource_name}")

# Read existing header from nested template
with open('nested/appsync/template.yaml', 'r') as f:
    existing_content = f.read()

# Find Resources: section
resources_idx = existing_content.find('Resources:')
if resources_idx == -1:
    print("ERROR: Could not find Resources: in nested template")
    exit(1)

# Keep header (everything before Resources:) and add extracted resources
header = existing_content[:resources_idx + len('Resources:\n')]
final_content = header + ''.join(extracted)

# Add Outputs section
final_content += "\n\nOutputs:\n"
final_content += "  AppSyncServiceRoleArn:\n"
final_content += "    Description: ARN of the AppSync service role\n"
final_content += "    Value: !GetAtt AppSyncServiceRole.Arn\n"

# Write final template
with open('nested/appsync/template.yaml', 'w') as f:
    f.write(final_content)

print(f"\n=== Summary ===")
print(f"Extracted: {len(extracted)} resources")
print(f"Not found: {len(not_found)} resources")
if not_found:
    print(f"\nMissing resources:")
    for name in not_found:
        print(f"  - {name}")
print(f"\nGenerated nested/appsync/template.yaml ({len(final_content)} chars)")