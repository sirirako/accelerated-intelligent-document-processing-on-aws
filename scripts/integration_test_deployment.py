#!/usr/bin/env python3
"""
Integration Test Deployment Script

Handles code packaging, S3 upload, and pipeline monitoring for integration tests.
"""

import os
import subprocess
import sys
import time

import boto3


def run_command(cmd, check=True):
    """Run shell command and return result"""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result


def get_env_var(name, default=None):
    """Get environment variable with optional default"""
    value = os.environ.get(name, default)
    if value is None:
        print(f"Error: Environment variable {name} is required")
        sys.exit(1)
    return value


def create_deployment_package():
    """Create deployment zip package"""
    print("Creating deployment package...")

    # Create dist directory
    os.makedirs("./dist", exist_ok=True)

    # Remove existing zip
    if os.path.exists("./dist/code.zip"):
        os.remove("./dist/code.zip")

    # Create zip with exclusions
    excludes = [
        "*.git/*",
        "*.git/**",
        "*__pycache__/*",
        ".gitlab-ci.yml",
        "*.delete/*",
        "*.sav/*",
        "*.venv/*",
        "*.vscode/*",
        "*cdk.out/*",
        "*dist/*",
        "*.DS_Store",
        "*.pyc",
        "*.pyo",
        "*.pyd",
        "*.so",
        "**/.env",
        "*.docker/*",
        "*.aws-sam/*",
    ]

    exclude_args = " ".join([f'-x "{pattern}"' for pattern in excludes])
    cmd = f"zip -r ./dist/code.zip ./ {exclude_args}"

    run_command(cmd)
    print("✅ Deployment package created")


def upload_to_s3(bucket_name):
    """Upload code package to S3 and return version ID"""
    print(f"Uploading to S3 bucket: {bucket_name}")

    s3_client = boto3.client("s3")

    try:
        response = s3_client.put_object(
            Bucket=bucket_name,
            Key="deploy/code.zip",
            Body=open("./dist/code.zip", "rb"),
        )
        version_id = response.get("VersionId", "unknown")
        print(f"✅ Uploaded with version ID: {version_id}")
        return version_id
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        sys.exit(1)


def monitor_pipeline(pipeline_name, max_wait=7200):
    """Monitor CodePipeline execution until completion"""
    print(f"Monitoring pipeline: {pipeline_name}")

    codepipeline = boto3.client("codepipeline")
    wait_time = 0
    poll_interval = 30

    # Initial wait for pipeline to start
    print("Waiting for pipeline to start...")
    time.sleep(30)

    while wait_time < max_wait:
        try:
            # Get latest pipeline execution
            response = codepipeline.list_pipeline_executions(
                pipelineName=pipeline_name, maxResults=1
            )

            if not response["pipelineExecutionSummaries"]:
                print("⏳ No pipeline executions found, waiting...")
            else:
                execution = response["pipelineExecutionSummaries"][0]
                execution_id = execution["pipelineExecutionId"]
                status = execution["status"]

                print(f"Pipeline execution {execution_id}: {status}")

                if status == "Succeeded":
                    print("✅ Pipeline completed successfully!")
                    return True
                elif status in ["Failed", "Cancelled", "Superseded"]:
                    print(f"❌ Pipeline failed with status: {status}")
                    return False
                elif status == "InProgress":
                    print(f"⏳ Pipeline still running... ({wait_time}s elapsed)")

        except Exception as e:
            print(f"Error checking pipeline status: {e}")

        time.sleep(poll_interval)
        wait_time += poll_interval

    print(f"❌ Pipeline monitoring timed out after {max_wait} seconds")
    return False


def main():
    """Main execution function"""
    print("Starting integration test deployment...")

    # Get configuration from environment
    account_id = get_env_var("IDP_ACCOUNT_ID", "020432867916")
    region = get_env_var("AWS_DEFAULT_REGION", "us-east-1")
    bucket_name = f"idp-sdlc-sourcecode-{account_id}-{region}"
    pipeline_name = get_env_var("IDP_PIPELINE_NAME", "idp-sdlc-deploy-pipeline")

    print(f"Account ID: {account_id}")
    print(f"Region: {region}")
    print(f"Bucket: {bucket_name}")
    print(f"Pipeline: {pipeline_name}")

    # Execute deployment steps
    create_deployment_package()
    upload_to_s3(bucket_name)

    success = monitor_pipeline(pipeline_name)

    if success:
        print("🎉 Integration test deployment completed successfully!")
        sys.exit(0)
    else:
        print("💥 Integration test deployment failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
