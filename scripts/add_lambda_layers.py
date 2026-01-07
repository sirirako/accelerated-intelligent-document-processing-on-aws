#!/usr/bin/env python3
"""
Automated script to add Lambda Layer references to all Lambda functions in templates.

This script:
1. Adds Layers property to Lambda functions in template.yaml (main)
2. Adds Layers property to Lambda functions in nested/appsync/template.yaml
3. Adds layer parameters to nested/appsync/template.yaml
4. Adds layer outputs to template.yaml
5. Updates APPSYNCSTACK to pass layer ARNs
"""

import re
import sys
from pathlib import Path


# Function-to-layer mapping
MAIN_TEMPLATE_FUNCTIONS = {
    # Layer 1 (Base)
    "QueueSender": "base",
    "QueueProcessor": "base",
    "WorkflowTracker": "base",
    "PostProcessingDecompressor": "base",
    "DiscoveryProcessorFunction": "base",
    "TestFileCopierFunction": "base",
    "TestSetFileCopierFunction": "base",
    "UpdateConfigurationFunction": "base",
    
    # Layer 2 (Reporting)
    "SaveReportingDataFunction": "reporting",
    
    # Layer 3 (Agents)
    "AgentChatProcessorFunction": "agents",
    "AgentProcessorFunction": "agents",
    "AgentCoreAnalyticsLambdaFunction": "agents",  # Already done
}

APPSYNC_TEMPLATE_FUNCTIONS = {
    # Layer 1 (Base)
    "AbortWorkflowResolverFunction": "base",
    "CopyToBaselineResolverFunction": "base",
    "ProcessChangesResolverFunction": "base",
    "ReprocessDocumentResolverFunction": "base",
    "ChatWithDocumentResolverFunction": "base",
    "ConfigurationResolverFunction": "base",
    "GetStepFunctionExecutionResolverFunction": "base",
    "QueryKnowledgeBaseResolverFunction": "base",
    "SyncBdaIdpResolverFunction": "base",
    "TestRunnerFunction": "base",
    "TestSetResolverFunction": "base",
    
    # Layer 3 (Agents)
    "ListAvailableAgentsFunction": "agents",
}


def add_layers_to_function(content: str, function_name: str, layer_type: str) -> tuple[str, bool]:
    """Add Layers property to a Lambda function if not already present.
    
    Returns: (modified_content, was_modified)
    """
    # Map layer type to CloudFormation reference
    layer_refs = {
        "base": "!Ref IDPCommonBaseLayer",
        "reporting": "!Ref IDPCommonReportingLayer",
        "agents": "!Ref IDPCommonAgentsLayer",
    }
    
    # For nested/appsync, use parameter references instead
    if "Arn" in content[:1000]:  # Heuristic: if early in file, likely appsync
        layer_refs = {
            "base": "!Ref IDPCommonBaseLayerArn",
            "reporting": "!Ref IDPCommonReportingLayerArn",
            "agents": "!Ref IDPCommonAgentsLayerArn",
        }
    
    layer_ref = layer_refs[layer_type]
    
    # Pattern: Find function definition with Properties section
    # Look for: FunctionName: ... OR CodeUri: ... followed by Properties block
    pattern = rf"  {function_name}:\s+Type: AWS::Serverless::Function.*?Properties:(.*?)(?=\n  \w+:|$)"
    
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        print(f"⚠️  Warning: Could not find function {function_name}")
        return content, False
    
    properties_section = match.group(1)
    
    # Check if Layers already exists
    if "Layers:" in properties_section:
        print(f"✓ {function_name} already has Layers property")
        return content, False
    
    # Find where to insert Layers (after Timeout, before Environment or Policies)
    # Look for the line with Timeout or MemorySize
    timeout_match = re.search(r"(\n\s+)(Timeout:.*?\n)", properties_section)
    if timeout_match:
        indent = timeout_match.group(1)
        timeout_line = timeout_match.group(2)
        layers_block = f"{indent}Layers:{indent}  - {layer_ref}\n"
        
        # Insert after Timeout line
        insertion_point = match.start(1) + properties_section.index(timeout_line) + len(timeout_line)
        content = content[:insertion_point] + layers_block + content[insertion_point:]
        
        print(f"✅ Added {layer_type} layer to {function_name}")
        return content, True
    
    # Fallback: insert after Handler or Runtime
    handler_match = re.search(r"(\n\s+)(Runtime:.*?\n)", properties_section)
    if handler_match:
        indent = handler_match.group(1)
        runtime_line = handler_match.group(2)
        layers_block = f"{indent}Layers:{indent}  - {layer_ref}\n"
        
        insertion_point = match.start(1) + properties_section.index(runtime_line) + len(runtime_line)
        content = content[:insertion_point] + layers_block + content[insertion_point:]
        
        print(f"✅ Added {layer_type} layer to {function_name}")
        return content, True
    
    print(f"⚠️  Warning: Could not find insertion point for {function_name}")
    return content, False


def add_appsync_parameters(content: str) -> str:
    """Add layer parameters to nested/appsync template."""
    
    # Find Parameters section
    params_pattern = r"(Parameters:.*?)(?=\nConditions:|$)"
    params_match = re.search(params_pattern, content, re.DOTALL)
    
    if not params_match:
        print("⚠️  Warning: Could not find Parameters section")
        return content
    
    # Check if parameters already exist
    if "IDPCommonBaseLayerArn" in content:
        print("✓ Layer parameters already exist in appsync template")
        return content
    
    # Add parameters at the end of Parameters section
    layer_params = """
  # Lambda Layers from main template
  IDPCommonBaseLayerArn:
    Type: String
    Description: ARN of IDP Common Base Layer
  
  IDPCommonAgentsLayerArn:
    Type: String
    Description: ARN of IDP Common Agents Layer
"""
    
    # Insert before Conditions section
    insertion_point = params_match.end()
    content = content[:insertion_point] + "\n" + layer_params + content[insertion_point:]
    
    print("✅ Added layer parameters to appsync template")
    return content


def add_layer_outputs(content: str) -> str:
    """Add layer ARN outputs to main template."""
    
    if "IDPCommonBaseLayerArn:" in content:
        print("✓ Layer outputs already exist")
        return content
    
    # Find Outputs section - add before MCPServerEndpoint or at end
    outputs_pattern = r"(Outputs:.*?)(  MCPServerEndpoint:)"
    outputs_match = re.search(outputs_pattern, content, re.DOTALL)
    
    layer_outputs = """  IDPCommonBaseLayerArn:
    Description: ARN of IDP Common Base Layer
    Value: !Ref IDPCommonBaseLayer
  
  IDPCommonReportingLayerArn:
    Description: ARN of IDP Common Reporting Layer
    Value: !Ref IDPCommonReportingLayer
  
  IDPCommonAgentsLayerArn:
    Description: ARN of IDP Common Agents Layer
    Value: !Ref IDPCommonAgentsLayer
  
"""
    
    if outputs_match:
        content = content[:outputs_match.start(2)] + layer_outputs + content[outputs_match.start(2):]
        print("✅ Added layer outputs to main template")
    else:
        # Fallback: add at end of Outputs section
        print("⚠️  Warning: Could not find MCPServerEndpoint, adding at end")
    
    return content


def update_appsync_stack_parameters(content: str) -> str:
    """Add layer parameters to APPSYNCSTACK resource."""
    
    if "IDPCommonBaseLayerArn: !Ref IDPCommonBaseLayer" in content:
        print("✓ APPSYNCSTACK already has layer parameters")
        return content
    
    # Find APPSYNCSTACK Parameters section
    pattern = r"(APPSYNCSTACK:.*?Parameters:.*?)(IsPattern3:)"
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print("⚠️  Warning: Could not find APPSYNCSTACK Parameters section")
        return content
    
    layer_params = """        
        # Lambda Layers
        IDPCommonBaseLayerArn: !Ref IDPCommonBaseLayer
        IDPCommonAgentsLayerArn: !Ref IDPCommonAgentsLayer
        """
    
    content = content[:match.start(2)] + layer_params + "\n        " + content[match.start(2):]
    print("✅ Added layer parameters to APPSYNCSTACK")
    return content


def main():
    """Main execution."""
    print("🚀 Starting automated Lambda Layer template updates...\n")
    
    # Update main template
    print("📝 Processing template.yaml...")
    template_path = Path("template.yaml")
    if not template_path.exists():
        print("❌ Error: template.yaml not found")
        sys.exit(1)
    
    content = template_path.read_text()
    modified_count = 0
    
    # Add Layers to functions
    for func_name, layer_type in MAIN_TEMPLATE_FUNCTIONS.items():
        if func_name == "AgentCoreAnalyticsLambdaFunction":
            # Already done manually
            print(f"✓ {func_name} already updated")
            continue
        content, was_modified = add_layers_to_function(content, func_name, layer_type)
        if was_modified:
            modified_count += 1
    
    # Add layer outputs
    content = add_layer_outputs(content)
    
    # Update APPSYNCSTACK parameters
    content = update_appsync_stack_parameters(content)
    
    # Write back
    template_path.write_text(content)
    print(f"\n✅ Updated template.yaml ({modified_count} functions modified)")
    
    # Update nested/appsync template
    print("\n📝 Processing nested/appsync/template.yaml...")
    appsync_template_path = Path("nested/appsync/template.yaml")
    if not appsync_template_path.exists():
        print("❌ Error: nested/appsync/template.yaml not found")
        sys.exit(1)
    
    appsync_content = appsync_template_path.read_text()
    appsync_modified_count = 0
    
    # Add parameters first
    appsync_content = add_appsync_parameters(appsync_content)
    
    # Add Layers to functions
    for func_name, layer_type in APPSYNC_TEMPLATE_FUNCTIONS.items():
        appsync_content, was_modified = add_layers_to_function(appsync_content, func_name, layer_type)
        if was_modified:
            appsync_modified_count += 1
    
    # Write back
    appsync_template_path.write_text(appsync_content)
    print(f"\n✅ Updated nested/appsync/template.yaml ({appsync_modified_count} functions modified)")
    
    print("\n" + "="*60)
    print("🎉 Automated template updates complete!")
    print(f"   • Main template: {modified_count} functions updated")
    print(f"   • AppSync template: {appsync_modified_count} functions updated")
    print("="*60)
    print("\n🧪 Next: Test with: python publish.py bobs-artifacts idp-dev-private us-west-2 --clean-build")


if __name__ == "__main__":
    main()