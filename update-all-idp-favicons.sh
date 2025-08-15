#!/bin/bash

# Script to update favicon for all IDP stacks in an AWS account
# Usage: ./update-all-idp-favicons.sh [region]

REGION=${1:-us-east-1}

echo "=== Updating favicon for all IDP stacks in region: $REGION ==="
echo ""

# Find all IDP stacks
echo "Finding IDP stacks..."
IDP_STACKS=$(aws cloudformation list-stacks \
  --region "$REGION" \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE UPDATE_ROLLBACK_COMPLETE \
  --query 'StackSummaries[?contains(StackName, `IDP`) && !contains(StackName, `-PATTERN`) && !contains(StackName, `-DOCUMENT`) && !contains(StackName, `-BDA`)].StackName' \
  --output text)

if [ -z "$IDP_STACKS" ]; then
    echo "❌ No IDP stacks found in region $REGION"
    exit 1
fi

echo "Found IDP stacks:"
for stack in $IDP_STACKS; do
    echo "  - $stack"
done
echo ""

# Process each stack
for STACK_NAME in $IDP_STACKS; do
    echo "=== Processing stack: $STACK_NAME ==="
    
    # Find the CodeBuild project
    CODEBUILD_PROJECT="${STACK_NAME}-webui-build"
    
    # Check if the project exists
    if aws codebuild batch-get-projects --names "$CODEBUILD_PROJECT" --region "$REGION" --query 'projects[0].name' --output text 2>/dev/null | grep -q "$CODEBUILD_PROJECT"; then
        echo "✅ Found CodeBuild project: $CODEBUILD_PROJECT"
        
        # Start the build
        echo "Starting build..."
        BUILD_ID=$(aws codebuild start-build --project-name "$CODEBUILD_PROJECT" --region "$REGION" --query 'build.id' --output text 2>/dev/null)
        
        if [ $? -eq 0 ]; then
            echo "✅ Build started successfully!"
            echo "Build ID: $BUILD_ID"
        else
            echo "❌ Failed to start build for $STACK_NAME"
        fi
    else
        echo "⚠️  CodeBuild project '$CODEBUILD_PROJECT' not found - skipping"
    fi
    
    echo ""
done

echo "=== Summary ==="
echo "Favicon update builds have been started for all applicable IDP stacks."
echo "Monitor progress in the CodeBuild console:"
echo "https://console.aws.amazon.com/codesuite/codebuild/projects?region=$REGION"
echo ""
echo "Favicon icons will be available once builds complete (usually 5-10 minutes per stack)."
