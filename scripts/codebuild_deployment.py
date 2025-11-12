#!/usr/bin/env python3
"""
CodeBuild Deployment Script

Handles IDP stack deployment and testing in AWS CodeBuild environment.
"""

import json
import os
import re
import shlex
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from textwrap import dedent

import boto3

# Configuration for patterns to deploy
DEPLOY_PATTERNS = [
    {
        "name": "Pattern 1 - BDA",
        "id": "pattern-1",
        "suffix": "p1",
        "sample_file": "lending_package.pdf",
        "verify_string": "ANYTOWN, USA 12345",
        "result_location": "pages/0/result.json",
        "content_path": "pages.0.representation.markdown",
    },
    {
        "name": "Pattern 2 - OCR + Bedrock",
        "id": "pattern-2",
        "suffix": "p2",
        "sample_file": "lending_package.pdf",
        "verify_string": "ANYTOWN, USA 12345",
        "result_location": "pages/1/result.json",
        "content_path": "text",
    },
    # {"name": "Pattern 3 - UDOP + Bedrock", "id": "pattern-3", "suffix": "p3", "sample_file": "rvl_cdip_package.pdf", "verify_string": "WESTERN DARK FIRED TOBACCO GROWERS", "result_location": "pages/1/result.json", "content_path": "text"},
]


def run_command(cmd, check=True):
    """Run shell command and return result"""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True) # nosemgrep: python.lang.security.audit.subprocess-shell-true.subprocess-shell-true - Reviewed: command input is controlled and sanitized
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        raise Exception(f"Command failed: {cmd}")
    return result


def get_env_var(name, default=None):
    """Get environment variable with optional default"""
    value = os.environ.get(name, default)
    if value is None:
        raise Exception(f"Environment variable {name} is required")
    return value


def generate_stack_prefix():
    """Generate unique stack prefix with timestamp including seconds"""
    timestamp = datetime.now().strftime("%m%d-%H%M%S")  # Format: MMDD-HHMMSS
    return f"idp-{timestamp}"


def publish_templates():
    """Run publish.py to build and upload templates to S3"""
    print("📦 Publishing templates to S3...")

    # Get AWS account ID and region
    account_id = get_env_var("IDP_ACCOUNT_ID", "020432867916")
    region = get_env_var("AWS_DEFAULT_REGION", "us-east-1")

    # Generate bucket name and prefix
    bucket_basename = f"genaiic-sdlc-sourcecode-{account_id}-{region}"
    prefix = f"codebuild-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Run publish.sh
    cmd = f"./publish.sh {bucket_basename} {prefix} {region}"
    result = run_command(cmd)

    # Extract template URL from output - match S3 URLs only
    template_url_pattern = r"https://s3\..*?idp-main\.yaml"
    
    # Remove line breaks that might split the URL in terminal output
    clean_stdout = result.stdout.replace('\n', '').replace('\r', '')
    template_url_match = re.search(template_url_pattern, clean_stdout)

    if template_url_match:
        template_url = template_url_match.group(0)
        print(f"✅ Template published: {template_url}")
        return template_url
    else:
        print("❌ Failed to extract template URL from publish output")
        raise Exception("Failed to extract template URL from publish output")


def deploy_test_and_cleanup_pattern(stack_prefix, pattern_config, admin_email, template_url):
    """Deploy and test a specific IDP pattern"""
    pattern_name = pattern_config["name"]
    pattern_id = pattern_config["id"]
    pattern_suffix = pattern_config["suffix"]
    sample_file = pattern_config["sample_file"]
    verify_string = pattern_config["verify_string"]
    result_location = pattern_config["result_location"]
    content_path = pattern_config["content_path"]

    stack_name = f"{stack_prefix}-{pattern_suffix}"
    batch_id = f"test-{pattern_suffix}"

    print(f"[{pattern_name}] Starting deployment: {stack_name}")

    try:
        # Step 1: Deploy using template URL
        print(f"[{pattern_name}] Step 1: Deploying stack...")
        cmd = f"idp-cli deploy --stack-name {stack_name} --template-url {template_url} --pattern {pattern_id} --admin-email {admin_email} --wait"
        run_command(cmd)
        print(f"[{pattern_name}] ✅ Deployment completed")

        # Step 2: Test stack status
        print(f"[{pattern_name}] Step 2: Verifying stack status...")
        cmd = f"aws cloudformation describe-stacks --stack-name {stack_name} --query 'Stacks[0].StackStatus' --output text"
        result = run_command(cmd)

        if "COMPLETE" not in result.stdout:
            print(f"[{pattern_name}] ❌ Stack status: {result.stdout.strip()}")
            return {
                "stack_name": stack_name,
                "pattern_name": pattern_name,
                "success": False,
                "error": f"Stack deployment failed with status: {result.stdout.strip()}"
            }

        print(f"[{pattern_name}] ✅ Stack is healthy")

        # Step 3: Run inference test
        print(f"[{pattern_name}] Step 3: Running inference test with {sample_file}...")
        cmd = f"idp-cli run-inference --stack-name {stack_name} --dir samples --file-pattern {sample_file} --batch-id {batch_id} --monitor"
        run_command(cmd)
        print(f"[{pattern_name}] ✅ Inference completed")

        # Step 4: Download and verify results
        print(f"[{pattern_name}] Step 4: Downloading results...")
        results_dir = f"/tmp/results-{pattern_suffix}"

        cmd = f"idp-cli download-results --stack-name {stack_name} --batch-id {batch_id} --output-dir {results_dir}"
        run_command(cmd)

        # Step 5: Verify result content
        print(f"[{pattern_name}] Step 5: Verifying result content...")

        # Find the result file at the specified location
        cmd = f"find {results_dir} -path '*/{result_location}' | head -1"
        result = run_command(cmd)
        result_file = result.stdout.strip()

        if not result_file:
            print(f"[{pattern_name}] ❌ No result file found at {result_location}")
            return {
                "stack_name": stack_name,
                "pattern_name": pattern_name,
                "success": False,
                "error": f"No result file found at expected location: {result_location}"
            }

        # Verify the result file contains expected content
        try:
            import json

            with open(result_file, "r") as f:
                result_json = json.load(f)

            # Extract text content using the specified path
            text_content = result_json
            for key in content_path.split("."):
                if key.isdigit():
                    text_content = text_content[int(key)]
                else:
                    text_content = text_content[key]

            # Verify expected string in content
            if verify_string not in text_content:
                print(
                    f"[{pattern_name}] ❌ Text content does not contain expected string: '{verify_string}'"
                )
                print(
                    f"[{pattern_name}] Actual text starts with: '{text_content[:100]}...'"
                )
                return {
                    "stack_name": stack_name,
                    "pattern_name": pattern_name,
                    "success": False,
                    "error": f"Verification failed: Expected string '{verify_string}' not found in result"
                }

            print(
                f"[{pattern_name}] ✅ Found expected verification string: '{verify_string}'"
            )
            
            success_result = {
                "stack_name": stack_name,
                "pattern_name": pattern_name,
                "success": True,
                "verification_string": verify_string
            }

        except Exception as e:
            print(f"[{pattern_name}] ❌ Failed to validate result content: {e}")
            success_result = {
                "stack_name": stack_name,
                "pattern_name": pattern_name,
                "success": False,
                "error": f"Result validation failed: {str(e)}"
            }

    except Exception as e:
        print(f"[{pattern_name}] ❌ Testing failed: {e}")
        success_result = {
            "stack_name": stack_name,
            "pattern_name": pattern_name,
            "success": False,
            "error": f"Deployment/testing failed: {str(e)}"
        }

    # Always cleanup the stack regardless of success/failure
    finally:
        cleanup_stack(stack_name, pattern_name)
    
    return success_result


def get_codebuild_logs():
    """Get CodeBuild logs from CloudWatch"""
    try:
        # Get CodeBuild build ID from environment
        build_id = os.environ.get('CODEBUILD_BUILD_ID', '')
        if not build_id:
            return "CodeBuild logs not available (not running in CodeBuild)"
        
        # Extract log group and stream from build ID
        log_group = f"/aws/codebuild/{build_id.split(':')[0]}"
        log_stream = build_id.split(':')[-1]
        
        # Get logs from CloudWatch
        logs_client = boto3.client('logs')
        response = logs_client.get_log_events(
            logGroupName=log_group,
            logStreamName=log_stream,
            startFromHead=True
        )
        
        # Extract log messages
        log_messages = []
        for event in response.get('events', []):
            log_messages.append(event['message'])
        
        return '\n'.join(log_messages)
        
    except Exception as e:
        return f"Failed to retrieve CodeBuild logs: {str(e)}"


def generate_publish_failure_summary(publish_error):
    """Generate summary for publish/build failures"""
    try:
        bedrock = boto3.client('bedrock-runtime')
        
        prompt = dedent(f"""
        You are a build system analyst. Analyze this publish/build failure and provide specific technical guidance.

        Publish Error: {publish_error}
        
        Build Logs:
        {get_codebuild_logs()}

        ANALYZE THE LOGS FOR: npm ci errors, package-lock.json sync issues, missing @esbuild packages, UI build failures

        Create a summary focused on BUILD/PUBLISH issues with bullet points:

        🔧 BUILD FAILURE ANALYSIS

        📋 Component Status:
        • UI Build: FAILED - npm dependency issues
        • Lambda Build: SUCCESS - All patterns built correctly
        • Template Publish: FAILED - S3 access denied

        🔍 Technical Root Cause:
        • Extract exact npm/pip error messages from logs
        • Identify specific missing packages or version conflicts
        • Focus on build-time errors, not deployment errors
        • Check AWS credentials and S3 bucket permissions

        💡 Fix Commands:
        • Run: cd src/ui && rm package-lock.json && npm install
        • Check AWS profile: aws configure list --profile <name>
        • Verify S3 access: aws s3 ls s3://bucket-name --profile <name>
        • Update package-lock.json and commit changes

        Keep each bullet point under 75 characters. Use sub-bullets for details.
        
        IMPORTANT: Respond ONLY with the bullet format above. Do not include any text before or after.
        """)
        
        response = bedrock.invoke_model(
            modelId='anthropic.claude-3-5-sonnet-20240620-v1:0',
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        
        response_body = json.loads(response['body'].read())
        summary = response_body['content'][0]['text']
        
        print(summary)
        
    except Exception as e:
        print(f"⚠️ Failed to generate build failure summary: {e}")


def generate_deployment_summary(deployment_results, stack_prefix, template_url):
    """
    Generate deployment summary using Bedrock API
    
    Args:
        deployment_results: List of deployment result dictionaries
        stack_prefix: Stack prefix used for deployment
        template_url: Template URL used for deployment
    
    Returns:
        str: Generated summary text
    """
    try:
        # Get CodeBuild logs
        deployment_logs = get_codebuild_logs()
        
        # Check if log retrieval failed
        if deployment_logs.startswith("Failed to retrieve CodeBuild logs"):
            raise Exception("CodeBuild logs unavailable")
        
        # Initialize Bedrock client
        bedrock = boto3.client('bedrock-runtime')
        
        # Create prompt for Bedrock with actual logs
        prompt = dedent(f"""
        You are an AWS deployment analyst. Analyze the following deployment logs and create a concise summary in table format.

        Deployment Information:
        - Timestamp: {datetime.now().isoformat()}
        - Stack Prefix: {stack_prefix}
        - Template URL: {template_url}
        - Total Patterns: {len(deployment_results)}

        Raw Deployment Logs:
        {deployment_logs}

        Pattern Results Summary:
        {json.dumps(deployment_results, indent=2)}

        Create a summary with clean bullet format:

        🚀 DEPLOYMENT RESULTS

        📋 Pattern Status:
        • Pattern 1 - BDA: SUCCESS - Stack deployed successfully (120s)
        • Pattern 2 - OCR: FAILED - CloudFormation CREATE_FAILED (89s)  
        • Pattern 3 - UDOP: SKIPPED - Not selected for deployment

        🔍 Root Cause Analysis:
        • Analyze actual deployment results from Pattern Results Summary
        • Extract specific CloudFormation error messages and resource names
        • Focus on CREATE_FAILED, UPDATE_FAILED, ROLLBACK events
        • Check for smoke test failures and their underlying causes
        • Report Lambda function errors, API Gateway issues, IAM permissions

        💡 Recommendations:
        • Use actual pattern names and statuses from deployment_results
        • Include specific CloudFormation stack names and error details
        • Provide smoke test error details and remediation steps

        Keep each bullet point under 75 characters. Use clean text format.
        
        IMPORTANT: Respond ONLY with clean bullet format above. No tables or boxes.

        Requirements:
        - Analyze ALL error messages in logs for specific technical details
        - Include exact CloudFormation/Lambda error messages and specific commands to fix
        - Extract specific error patterns like "CREATE_FAILED", "UPDATE_FAILED", "ROLLBACK"
        - Provide detailed technical root cause analysis with specific resource names
        - Include actionable recommendations with exact terminal commands
        
        """)
        
        # Call Bedrock API
        response = bedrock.invoke_model(
            modelId='anthropic.claude-3-5-sonnet-20240620-v1:0',
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        summary = response_body['content'][0]['text']
        
        print(summary)
        
        return summary
        
    except Exception as e:
        print(f"⚠️ Failed to generate Bedrock summary: {e}")
        # Manual summary when Bedrock unavailable
        successful = sum(1 for r in deployment_results if r["success"])
        total = len(deployment_results)
        
        manual_summary = dedent(f"""
        DEPLOYMENT SUMMARY REPORT (MANUAL)
        ==================================
        
        Timestamp: {datetime.now().isoformat()}
        Stack Prefix: {stack_prefix}
        Template URL: {template_url}
        
        Overall Status: {'SUCCESS' if successful == total else 'PARTIAL_FAILURE' if successful > 0 else 'FAILURE'}
        Successful Patterns: {successful}/{total}
        
        Pattern Results:
        """)
        
        for result in deployment_results:
            status = "✅ SUCCESS" if result["success"] else "❌ FAILED"
            manual_summary += f"- {result['pattern_name']}: {status}\n"
        
        if successful < total:
            manual_summary += "\nRecommendation: Review failed patterns and retry deployment.\n"
        
        print("📊 Deployment Summary (Manual):")
        print("=" * 80)
        print(manual_summary)
        print("=" * 80)
        
        return manual_summary

def cleanup_stack(stack_name, pattern_name):
    print(f"[{pattern_name}] Cleaning up: {stack_name}")
    try:
        # Check stack status first
        result = run_command(f"aws cloudformation describe-stacks --stack-name {stack_name} --query 'Stacks[0].StackStatus' --output text", check=False)
        stack_status = result.stdout.strip() if result.returncode == 0 else "NOT_FOUND"
        
        print(f"[{pattern_name}] Stack status: {stack_status}")
        
        # Delete the stack and wait for completion
        print(f"[{pattern_name}] Attempting stack deletion...")
        run_command(f"idp-cli delete --stack-name {stack_name} --force --empty-buckets --force-delete-all --wait", check=False)
        
        # Clean up additional log groups that might not be caught by idp-cli
        print(f"[{pattern_name}] Cleaning up additional log groups...")
        
        # Set AWS retry configuration to handle throttling
        os.environ['AWS_MAX_ATTEMPTS'] = '10'
        os.environ['AWS_RETRY_MODE'] = 'adaptive'

        # CloudWatch log groups
        result = run_command(f"aws logs describe-log-groups --query 'logGroups[?contains(logGroupName, `{stack_name}`)].logGroupName' --output json", check=False)
        if result.stdout.strip():
            try:
                import json
                log_group_names = json.loads(result.stdout.strip())
                for log_group_name in log_group_names:
                    if log_group_name:  # Skip empty names
                        print(f"[{pattern_name}] Deleting log group: {log_group_name}")
                        run_command(f"aws logs delete-log-group --log-group-name {shlex.quote(log_group_name)}", check=False)
            except json.JSONDecodeError:
                print(f"[{pattern_name}] Failed to parse log group names")

        # AppSync logs
        result = run_command(f"aws appsync list-graphql-apis --query 'graphqlApis[?contains(name, `{stack_name}`)].apiId' --output json", check=False)
        if result.stdout.strip():
            try:
                import json
                api_ids = json.loads(result.stdout.strip())
                for api_id in api_ids:
                    if api_id:  # Skip empty IDs
                        print(f"[{pattern_name}] Deleting AppSync log group for API: {api_id}")
                        run_command(f"aws logs delete-log-group --log-group-name {shlex.quote(f'/aws/appsync/apis/{api_id}')}", check=False)
            except json.JSONDecodeError:
                print(f"[{pattern_name}] Failed to parse AppSync API IDs")
        
        # Clean up CloudWatch Logs Resource Policy only if stack-specific
        result = run_command(f"aws logs describe-resource-policies --query 'resourcePolicies[?contains(policyName, `{stack_name}`)].policyName' --output text", check=False)
        if result.stdout.strip():
            policy_names = [name for name in result.stdout.strip().split('\t') if name]
            for policy_name in policy_names:
                print(f"[{pattern_name}] Deleting resource policy: {policy_name}")
                run_command(f"aws logs delete-resource-policy --policy-name '{policy_name}'", check=False)
        
        print(f"[{pattern_name}] ✅ Cleanup completed")
    except Exception as e:
        print(f"[{pattern_name}] ⚠️ Cleanup failed: {e}")


def main():
    """Main execution function"""
    print("Starting CodeBuild deployment process...")

    admin_email = get_env_var("IDP_ADMIN_EMAIL", "tanimath@amazon.com")
    stack_prefix = generate_stack_prefix()

    print(f"Stack Prefix: {stack_prefix}")
    print(f"Admin Email: {admin_email}")
    print(f"Patterns to deploy: {[p['name'] for p in DEPLOY_PATTERNS]}")

    # Step 1: Publish templates to S3
    try:
        template_url = publish_templates()
        publish_success = True
        publish_error = None
    except Exception as e:
        print(f"❌ Publish failed: {e}")
        template_url = "N/A - Publish failed"
        publish_success = False
        publish_error = str(e)

    all_success = publish_success
    deployment_results = []

    # Step 2: Deploy, test, and cleanup patterns concurrently (only if publish succeeded)
    if publish_success:
        print("🚀 Starting concurrent deployment of all patterns...")
        with ThreadPoolExecutor(max_workers=len(DEPLOY_PATTERNS)) as executor:
            # Submit all deployment tasks
            future_to_pattern = {
                executor.submit(
                    deploy_test_and_cleanup_pattern,
                    stack_prefix,
                    pattern_config,
                    admin_email,
                    template_url,
                ): pattern_config
                for pattern_config in DEPLOY_PATTERNS
            }

            # Collect results as they complete (cleanup happens within each pattern)
            for future in as_completed(future_to_pattern):
                pattern_config = future_to_pattern[future]
                try:
                    result = future.result()
                    deployment_results.append(result)
                    if not result["success"]:
                        all_success = False
                        print(f"[{pattern_config['name']}] ❌ Failed")
                    else:
                        print(f"[{pattern_config['name']}] ✅ Success")
                        
                except Exception as e:
                    print(f"[{pattern_config['name']}] ❌ Exception: {e}")
                    # Add failed result for exception cases
                    deployment_results.append({
                        "stack_name": f"{stack_prefix}-{pattern_config['suffix']}",
                        "pattern_name": pattern_config['name'],
                        "success": False,
                        "error": str(e)
                    })
                    all_success = False
    else:
        # Add publish failure to results for AI analysis
        deployment_results.append({
            "stack_name": "N/A",
            "pattern_name": "Template Publishing",
            "success": False,
            "error": "Failed to publish templates to S3"
        })

    # Step 3: Generate deployment summary using Bedrock (ALWAYS run for analysis)
    print("\n🤖 Generating deployment summary with Bedrock...")
    try:
        if not publish_success:
            generate_publish_failure_summary(publish_error)
        else:
            generate_deployment_summary(deployment_results, stack_prefix, template_url)
    except Exception as e:
        print(f"⚠️ Failed to generate deployment summary: {e}")

    # Check final status after all cleanups are done
    if all_success:
        print("🎉 All pattern deployments completed successfully!")
        sys.exit(0)
    else:
        print("💥 Some deployments failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
