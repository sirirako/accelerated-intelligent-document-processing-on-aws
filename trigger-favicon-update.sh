#!/bin/bash

# Script to trigger favicon update for existing IDP stacks
# Usage: ./trigger-favicon-update.sh [region] [stack-name]

REGION=${1:-us-east-1}
STACK_NAME=${2:-IDP}

echo "=== Triggering favicon update for existing IDP stack ==="
echo "Region: $REGION"
echo "Stack: $STACK_NAME"
echo ""

# Find the CodeBuild project name for the stack
CODEBUILD_PROJECT="${STACK_NAME}-webui-build"

echo "Looking for CodeBuild project: $CODEBUILD_PROJECT"

# Check if the project exists
if aws codebuild batch-get-projects --names "$CODEBUILD_PROJECT" --region "$REGION" --query 'projects[0].name' --output text 2>/dev/null | grep -q "$CODEBUILD_PROJECT"; then
    echo "✅ Found CodeBuild project: $CODEBUILD_PROJECT"
    
    # Start the build
    echo "Starting build..."
    BUILD_ID=$(aws codebuild start-build --project-name "$CODEBUILD_PROJECT" --region "$REGION" --query 'build.id' --output text)
    
    if [ $? -eq 0 ]; then
        echo "✅ Build started successfully!"
        echo "Build ID: $BUILD_ID"
        echo ""
        echo "Monitor progress at:"
        echo "https://console.aws.amazon.com/codesuite/codebuild/projects/$CODEBUILD_PROJECT/history?region=$REGION"
        echo ""
        echo "The favicon icons will be available once the build completes (usually 5-10 minutes)."
    else
        echo "❌ Failed to start build"
        exit 1
    fi
else
    echo "❌ CodeBuild project '$CODEBUILD_PROJECT' not found in region '$REGION'"
    echo ""
    echo "Available CodeBuild projects:"
    aws codebuild list-projects --region "$REGION" --query 'projects' --output table
    exit 1
fi
