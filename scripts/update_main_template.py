#!/usr/bin/env python3
"""
Update main template - remove extracted resources and add nested stack reference
"""

import re
from pathlib import Path

# Resources to remove from main template
RESOURCES_TO_REMOVE = [
    'GraphQLSchema',
    'AppSyncServiceRole',
    'TrackingTableDataSource',
    'DiscoveryTableDataSource',
    'ChatMessagesDataSource',
    'AgentTableDataSource',
    'NoneDataSource',
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

def find_resource_boundaries(lines, resource_name):
    """Find start and end line numbers for a resource"""
    resource_pattern = rf'^\s{{2}}{resource_name}:\s*$'
    start_idx = None
    
    for i, line in enumerate(lines):
        if re.match(resource_pattern, line):
            start_idx = i
            break
    
    if start_idx is None:
        return None, None
    
    # Find end (next resource at same indent or end of file)
    end_idx = start_idx + 1
    while end_idx < len(lines):
        line = lines[end_idx]
        if re.match(r'^\s{2}[A-Z][a-zA-Z0-9]+:', line):
            break
        end_idx += 1
    
    return start_idx, end_idx

# Read main template
with open('template.yaml', 'r') as f:
    lines = f.readlines()

# Find all resources to remove and mark their line ranges
lines_to_remove = set()
removed_resources = []
not_found = []

for resource_name in RESOURCES_TO_REMOVE:
    start, end = find_resource_boundaries(lines, resource_name)
    if start is not None:
        # Mark these lines for removal
        for i in range(start, end):
            lines_to_remove.add(i)
        removed_resources.append(resource_name)
        print(f"✓ Will remove: {resource_name} (lines {start+1}-{end})")
    else:
        not_found.append(resource_name)
        print(f"✗ Not found: {resource_name}")

# Create new file with removed resources
new_lines = [line for i, line in enumerate(lines) if i not in lines_to_remove]

# Check if APPSYNCSTACK already exists
appsync_exists = any(re.match(r'^\s{2}APPSYNCSTACK:', line) for line in new_lines)
if appsync_exists:
    print("APPSYNCSTACK already exists in template - skipping insertion")
    pattern3_idx = None
else:
    # Find where to insert APPSYNCSTACK (after PATTERN3STACK)
    pattern3_idx = None
    for i, line in enumerate(new_lines):
        if re.match(r'^\s{2}PATTERN3STACK:', line):
            # Find the end of PATTERN3STACK resource
            j = i + 1
            while j < len(new_lines):
                if re.match(r'^\s{2}[A-Z][a-zA-Z0-9]+:', new_lines[j]):
                    pattern3_idx = j
                    break
                j += 1
            break
    
    if pattern3_idx is None:
        print("ERROR: Could not find insertion point after PATTERN3STACK")
        exit(1)

# Create APPSYNCSTACK resource
appsync_stack = """
  ##########################################################################
  # Nested stack for AppSync resolvers
  ##########################################################################

  APPSYNCSTACK:
    DependsOn:
      - IsStacknameLengthOK
      - GraphQLApi
      - AgentChatProcessorFunction
      - AgentProcessorFunction
    Type: AWS::CloudFormation::Stack
    Properties:
      TemplateURL: ./nested/appsync/.aws-sam/packaged.yaml
      Parameters:
        # Core AppSync resources
        GraphQLApiId: !GetAtt GraphQLApi.ApiId
        GraphQLApiArn: !GetAtt GraphQLApi.Arn
        GraphQLApiUrl: !GetAtt GraphQLApi.GraphQLUrl
        
        # Background worker ARNs
        AgentChatProcessorFunctionArn: !GetAtt AgentChatProcessorFunction.Arn
        AgentProcessorFunctionArn: !GetAtt AgentProcessorFunction.Arn
        
        # DynamoDB Tables
        TrackingTableName: !Ref TrackingTable
        ConfigurationTableName: !Ref ConfigurationTable
        AgentTableName: !Ref AgentTable
        ChatMessagesTableName: !Ref ChatMessagesTable
        ChatSessionsTableName: !Ref ChatSessionsTable
        IdHelperChatMemoryTableName: !Ref IdHelperChatMemoryTable
        DiscoveryTrackingTableName: !Ref DiscoveryTrackingTable
        
        # S3 Buckets
        InputBucketName: !Ref InputBucket
        OutputBucketName: !Ref OutputBucket
        ConfigurationBucketName: !Ref ConfigurationBucket
        TestSetBucketName: !Ref TestSetBucket
        EvaluationBaselineBucketName: !If
          - ShouldCreateEvaluationBaselineBucket
          - !Ref EvaluationBaselineBucket
          - !Ref EvaluationBaselineBucketName
        ReportingBucketName: !If
          - ShouldCreateReportingBucket
          - !Ref ReportingBucket
          - !Ref ReportingBucketName
        WorkingBucketName: !Ref WorkingBucket
        DiscoveryBucketName: !Ref DiscoveryBucket
        
        # SQS Queues
        DocumentQueueUrl: !Ref DocumentQueue
        DiscoveryQueueUrl: !Ref DiscoveryQueue
        TestFileCopyQueueUrl: !Ref TestFileCopyQueue
        TestSetFileCopyQueueUrl: !Ref TestSetFileCopyQueue
        TestResultCacheUpdateQueueUrl: !Ref TestResultCacheUpdateQueue
        
        # Other resources
        CustomerManagedEncryptionKeyArn: !GetAtt CustomerManagedEncryptionKey.Arn
        ReportingDatabaseName: !Ref ReportingDatabase
        StateMachineArn: !If
          - IsPattern3
          - !GetAtt PATTERN3STACK.Outputs.StateMachineArn
          - !If
            - IsPattern2
            - !GetAtt PATTERN2STACK.Outputs.StateMachineArn
            - !GetAtt PATTERN1STACK.Outputs.StateMachineArn
        StateMachineName: !If
          - IsPattern3
          - !GetAtt PATTERN3STACK.Outputs.StateMachineName
          - !If
            - IsPattern2
            - !GetAtt PATTERN2STACK.Outputs.StateMachineName
            - !GetAtt PATTERN1STACK.Outputs.StateMachineName
        LookupFunctionName: !Ref LookupFunction
        SaveReportingFunctionName: !Ref SaveReportingDataFunction
        
        # Configuration
        StackName: !Ref AWS::StackName
        LogRetentionDays: !Ref LogRetentionDays
        LogLevel: !Ref LogLevel
        DataRetentionInDays: !Ref DataRetentionInDays
        PermissionsBoundaryArn: !Ref PermissionsBoundaryArn
        ExecutionTimeThresholdMs: !Ref ExecutionTimeThresholdMs
        
        # Conditional parameters
        HasGuardrailConfig: !If [HasGuardrailConfig, "true", "false"]
        BedrockGuardrailId: !Ref BedrockGuardrailId
        BedrockGuardrailVersion: !Ref BedrockGuardrailVersion
        ShouldUseDocumentKnowledgeBase: !If [ShouldUseDocumentKnowledgeBase, "true", "false"]
        KnowledgeBaseId: !If
          - ShouldUseDocumentKnowledgeBase
          - !GetAtt DOCUMENTKB.Outputs.KnowledgeBaseID
          - ""
        ShouldCreateEvaluationBaselineBucket: !If [ShouldCreateEvaluationBaselineBucket, "true", "false"]
        ShouldCreateReportingBucket: !If [ShouldCreateReportingBucket, "true", "false"]
        IsPattern1: !If [IsPattern1, "true", "false"]
        Pattern1BDAProjectArn: !If
          - ShouldCreateBDASampleProject
          - !GetAtt BDASAMPLEPROJECT.Outputs.ProjectArn
          - !Ref Pattern1BDAProjectArn
        HasPattern1BDAProjectArn: !If [HasPattern1BDAProjectArn, "true", "false"]

"""

# Insert APPSYNCSTACK after PATTERN3STACK if not already exists
if pattern3_idx is not None:
    new_lines.insert(pattern3_idx, appsync_stack)
    print(f"Inserted APPSYNCSTACK at line {pattern3_idx + 1}")

# Write updated template
backup_path = 'template.yaml.backup'
with open(backup_path, 'w') as f:
    f.writelines(lines)
print(f"Backup saved to: {backup_path}")

with open('template.yaml', 'w') as f:
    f.writelines(new_lines)

print(f"\n=== Summary ===")
print(f"Removed: {len(removed_resources)} resources")
print(f"Not found: {len(not_found)} resources")
print(f"Original lines: {len(lines)}")
print(f"New lines: {len(new_lines)}")
print(f"Reduction: {len(lines) - len(new_lines)} lines removed")