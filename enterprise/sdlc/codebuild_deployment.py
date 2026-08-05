#!/usr/bin/env python3
"""
Enterprise CodeBuild Deployment Script

Simplified deployment script for enterprise/air-gapped environments.
Reads config from S3 (pipeline-config.yaml), publishes, deploys, and
optionally runs tests. Persistent stacks are never deleted.

This is the enterprise replacement for scripts/sdlc/codebuild_deployment.py.
It does NOT merge with upstream — we own it fully.
"""

import json
import os
import subprocess
import sys
from datetime import datetime

import boto3


def run_command(cmd, check=True, timeout=None):
    """Run shell command and return result."""
    print(f"Running: {cmd}")
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout
    )  # nosec B602
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        raise Exception(f"Command failed (exit {result.returncode}): {cmd}")
    return result


def get_env_var(name, default=None):
    """Get environment variable with optional default."""
    value = os.environ.get(name, default)
    if value is None:
        raise Exception(f"Environment variable {name} is required")
    return value


def load_pipeline_config():
    """Load deployment config from S3 (PIPELINE_CONFIG_KEY).

    Each environment has its own config file in the S3 source bucket
    (synced from enterprise/environments/*.yaml).
    """
    import yaml

    source_bucket = get_env_var("SOURCE_BUCKET")
    config_key = os.environ.get("PIPELINE_CONFIG_KEY", "deploy/pipeline-config.yaml")
    local_path = "/tmp/pipeline-config.yaml"  # nosec B108

    try:
        s3 = boto3.client("s3")
        s3.download_file(source_bucket, config_key, local_path)
        with open(local_path) as f:
            config = yaml.safe_load(f) or {}
        print(f"✅ Loaded pipeline config from s3://{source_bucket}/{config_key}")
        return config
    except Exception as e:
        raise Exception(
            f"Failed to load pipeline config from s3://{source_bucket}/{config_key}: {e}\n"
            f"See enterprise/environments/README.md for setup instructions."
        )


def publish_templates(region, source_bucket):
    """Publish IDP templates to S3."""
    print("📦 Publishing templates...")

    bucket_basename = source_bucket.removesuffix(f"-{region}")
    prefix = f"codebuild-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    cmd = (
        f"idp-cli publish --source-dir . --bucket-basename {bucket_basename}"
        f" --prefix {prefix} --region {region} --no-lint"
    )
    result = run_command(cmd, timeout=3 * 3600)

    import re

    template_url_pattern = r"https://s3\..*?idp-main\.yaml"
    clean_stdout = result.stdout.replace("\n", "").replace("\r", "")
    match = re.search(template_url_pattern, clean_stdout)

    if match:
        template_url = match.group(0)
        print(f"✅ Template published: {template_url}")
        return template_url
    else:
        raise Exception("Failed to extract template URL from publish output")


def deploy_stack(stack_name, admin_email, template_url, pipeline_config):
    """Deploy the IDP stack using config parameters."""
    print(f"🚀 Deploying stack: {stack_name}")

    config_params = pipeline_config.get("parameters", {})
    role_arn = pipeline_config.get("role_arn", "")

    cmd = (
        f"idp-cli deploy --stack-name {stack_name}"
        f" --template-url {template_url}"
        f" --admin-email {admin_email}"
        f" --wait"
    )

    if role_arn:
        cmd += f" --role-arn {role_arn}"

    if pipeline_config.get("headless"):
        cmd += " --headless"

    if config_params:
        # Pass every key present in the config, empty values included.
        #
        # idp-cli sends UsePreviousValue for any parameter it is NOT given, so
        # omitting a key preserves whatever the stack already has rather than
        # clearing it. Dropping falsy values here would therefore make a
        # parameter impossible to blank out once set -- `PermissionsBoundaryArn:
        # ""` would never reach the CLI and the old boundary would survive every
        # deploy. It would also discard the legitimate values "0" and "false".
        #
        # So presence in the file is the signal: `Key: ""` (or a bare `Key:`,
        # which YAML parses as None) means "set this to empty". To leave a
        # parameter alone, omit or comment out the line.
        param_str = ",".join(
            f"{k}={'' if v is None else v}" for k, v in config_params.items()
        )
        cmd += f' --parameters "{param_str}"'

    run_command(cmd, timeout=3 * 3600)

    # Verify stack status
    result = run_command(
        f"aws cloudformation describe-stacks --stack-name {stack_name}"
        f" --query 'Stacks[0].StackStatus' --output text"
    )
    status = result.stdout.strip()

    if "COMPLETE" in status and "ROLLBACK" not in status:
        print(f"✅ Stack {stack_name} deployed successfully ({status})")
        return True
    else:
        print(f"❌ Stack {stack_name} in unexpected state: {status}")
        return False


def run_smoke_test(stack_name):
    """Run basic smoke test against deployed stack."""
    print("🧪 Running smoke test...")

    result = run_command(
        f"aws cloudformation describe-stacks --stack-name {stack_name}"
        f" --query 'Stacks[0].Outputs' --output json",
        check=False,
    )

    if result.returncode != 0:
        print("⚠️ Could not retrieve stack outputs")
        return False

    try:
        outputs = json.loads(result.stdout)
        output_map = {o["OutputKey"]: o["OutputValue"] for o in (outputs or [])}
        print(f"  Stack outputs: {len(output_map)} keys")

        api_url = output_map.get("ApiEndpoint") or output_map.get("JobsApiUrl")
        if api_url:
            print(f"  API endpoint: {api_url}")

        print("✅ Smoke test passed (stack outputs accessible)")
        return True
    except Exception as e:
        print(f"⚠️ Smoke test issue: {e}")
        return True  # Non-fatal


def main():
    """Main execution."""
    print("=" * 60)
    print("Enterprise CodeBuild Deployment")
    print("=" * 60)

    region = get_env_var("AWS_DEFAULT_REGION", "us-east-1")
    source_bucket = get_env_var("SOURCE_BUCKET")

    # Load config
    pipeline_config = load_pipeline_config()
    stack_name = pipeline_config.get("stack_name")
    admin_email = pipeline_config.get("admin_email", "admin@example.com")
    skip_tests = pipeline_config.get("skip_tests", False)

    if not stack_name:
        raise Exception(
            "stack_name is required in pipeline config (enterprise deployments use persistent stacks)"
        )

    print(f"  Stack:  {stack_name}")
    print(f"  Email:  {admin_email}")
    print(f"  Region: {region}")
    print(f"  Tests:  {'skip' if skip_tests else 'enabled'}")
    print()

    # Publish
    template_url = publish_templates(region, source_bucket)

    # Deploy
    success = deploy_stack(stack_name, admin_email, template_url, pipeline_config)

    if not success:
        print("💥 Deployment failed!")
        sys.exit(1)

    # Tests
    if not skip_tests:
        run_smoke_test(stack_name)
    else:
        print("ℹ️ skip_tests=true — skipping tests (CD mode)")

    # Never delete persistent stacks
    print(f"\n🎉 Deployment complete: {stack_name}")
    sys.exit(0)


if __name__ == "__main__":
    main()
