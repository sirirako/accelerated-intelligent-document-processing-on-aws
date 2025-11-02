#!/usr/bin/env python3
"""
CodeBuild Deployment Script

Handles IDP stack deployment and testing in AWS CodeBuild environment.
"""

import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

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
        sys.exit(1)
    return result


def get_env_var(name, default=None):
    """Get environment variable with optional default"""
    value = os.environ.get(name, default)
    if value is None:
        print(f"Error: Environment variable {name} is required")
        sys.exit(1)
    return value


def generate_stack_prefix():
    """Generate unique stack prefix with timestamp"""
    timestamp = datetime.now().strftime("%m%d-%H%M")  # Shorter format: MMDD-HHMM
    return f"idp-{timestamp}"


def publish_templates():
    """Run publish.py to build and upload templates to S3"""
    print("📦 Publishing templates to S3...")

    # Get AWS account ID and region
    account_id = get_env_var("IDP_ACCOUNT_ID", "020432867916")
    region = get_env_var("AWS_DEFAULT_REGION", "us-east-1")

    # Generate bucket name and prefix
    bucket_basename = f"idp-sdlc-sourcecode-{account_id}-{region}"
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
        sys.exit(1)


def deploy_and_test_pattern(stack_prefix, pattern_config, admin_email, template_url):
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
                }

            print(
                f"[{pattern_name}] ✅ Found expected verification string: '{verify_string}'"
            )
            return {
                "stack_name": stack_name,
                "pattern_name": pattern_name,
                "success": True,
            }

        except Exception as e:
            print(f"[{pattern_name}] ❌ Failed to validate result content: {e}")
            return {
                "stack_name": stack_name,
                "pattern_name": pattern_name,
                "success": False,
            }

    except Exception as e:
        print(f"[{pattern_name}] ❌ Testing failed: {e}")
        return {
            "stack_name": stack_name,
            "pattern_name": pattern_name,
            "success": False,
        }


def cleanup_stack(stack_name, pattern_name):
    """Clean up a deployed stack"""
    print(f"[{pattern_name}] Cleaning up: {stack_name}")
    try:
        run_command(f"idp-cli delete --stack-name {stack_name} --force", check=False)
        print(f"[{pattern_name}] ✅ Cleanup completed")
    except Exception as e:
        print(f"[{pattern_name}] ⚠️ Cleanup failed: {e}")


def main():
    """Main execution function"""
    print("Starting CodeBuild deployment process...")

    admin_email = get_env_var("IDP_ADMIN_EMAIL", "strahanr@amazon.com")
    stack_prefix = generate_stack_prefix()

    print(f"Stack Prefix: {stack_prefix}")
    print(f"Admin Email: {admin_email}")
    print(f"Patterns to deploy: {[p['name'] for p in DEPLOY_PATTERNS]}")

    # Step 1: Publish templates to S3
    template_url = publish_templates()

    deployed_stacks = []
    all_success = True

    # Step 2: Deploy and test patterns concurrently
    print("🚀 Starting concurrent deployment of all patterns...")
    with ThreadPoolExecutor(max_workers=len(DEPLOY_PATTERNS)) as executor:
        # Submit all deployment tasks
        future_to_pattern = {
            executor.submit(
                deploy_and_test_pattern,
                stack_prefix,
                pattern_config,
                admin_email,
                template_url,
            ): pattern_config
            for pattern_config in DEPLOY_PATTERNS
        }

        # Collect results as they complete
        for future in as_completed(future_to_pattern):
            pattern_config = future_to_pattern[future]
            try:
                result = future.result()
                deployed_stacks.append(result)
                if not result["success"]:
                    all_success = False
                    print(f"[{pattern_config['name']}] ❌ Failed")
                else:
                    print(f"[{pattern_config['name']}] ✅ Success")
            except Exception as e:
                print(f"[{pattern_config['name']}] ❌ Exception: {e}")
                all_success = False

    # Step 3: Cleanup all stacks concurrently
    print("🧹 Starting concurrent cleanup of all stacks...")
    with ThreadPoolExecutor(max_workers=len(deployed_stacks)) as executor:
        cleanup_futures = [
            executor.submit(cleanup_stack, result["stack_name"], result["pattern_name"])
            for result in deployed_stacks
        ]

        # Wait for all cleanups to complete
        for future in as_completed(cleanup_futures):
            future.result()  # Wait for completion

    if all_success:
        print("🎉 All pattern deployments completed successfully!")
        sys.exit(0)
    else:
        print("💥 Some deployments failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
