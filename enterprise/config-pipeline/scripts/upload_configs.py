#!/usr/bin/env python3
"""
Upload IDP document configurations to the target stack.

Reads config-pipeline.yaml from S3 to determine which config versions to upload,
then runs `idp-cli config-upload` for each one.

Environment variables (set by CodeBuild):
  SOURCE_BUCKET — S3 bucket with configs
  IDP_STACK_NAME — target IDP stack name
  CONFIG_PIPELINE_CONFIG_KEY — S3 key for pipeline config (optional)
"""

import glob
import os
import subprocess
import sys

import boto3
import yaml

SOURCE_BUCKET = os.environ.get("SOURCE_BUCKET", "")
IDP_STACK_NAME = os.environ.get("IDP_STACK_NAME", "")
CONFIG_KEY = os.environ.get("CONFIG_PIPELINE_CONFIG_KEY", "deploy/config-pipeline.yaml")


def load_pipeline_config():
    """Load config-pipeline.yaml from S3 (optional — if missing, upload all configs/)."""
    if not SOURCE_BUCKET:
        return {}
    try:
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=SOURCE_BUCKET, Key=CONFIG_KEY)
        config = yaml.safe_load(obj["Body"].read()) or {}
        print(f"Loaded pipeline config from s3://{SOURCE_BUCKET}/{CONFIG_KEY}")
        return config
    except Exception as e:
        print(f"No pipeline config found ({e}) — will upload all configs/*.yaml")
        return {}


def find_config_files():
    """Find all YAML config files in the configs/ directory."""
    patterns = ["configs/*.yaml", "configs/*.yml"]
    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern))
    return sorted(files)


def upload_config(config_file, version, stack_name):
    """Upload a single config version using idp-cli."""
    print(f"\n  Uploading: {config_file} as version '{version}' to stack '{stack_name}'")

    cmd = [
        "idp-cli", "config-upload",
        "--stack-name", stack_name,
        "--config-file", config_file,
        "--config-version", version,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  OK: {version} uploaded successfully")
    else:
        print(f"  FAILED: {version}")
        print(f"  stdout: {result.stdout}")
        print(f"  stderr: {result.stderr}")
        return False
    return True


def main():
    if not IDP_STACK_NAME:
        print("ERROR: IDP_STACK_NAME not set")
        sys.exit(1)

    pipeline_config = load_pipeline_config()
    stack_name = pipeline_config.get("stack_name", IDP_STACK_NAME)

    # Determine which configs to upload
    config_versions = pipeline_config.get("config_versions")

    if config_versions:
        # Explicit list — upload only these
        config_files = [f"configs/{v}.yaml" for v in config_versions]
        print(f"Uploading {len(config_versions)} specified config version(s) to {stack_name}")
    else:
        # No explicit list — upload all configs/*.yaml
        config_files = find_config_files()
        print(f"Uploading all {len(config_files)} config file(s) to {stack_name}")

    if not config_files:
        print("No config files found in configs/. Nothing to upload.")
        sys.exit(0)

    # Upload each config
    success = 0
    failed = 0
    for config_file in config_files:
        if not os.path.exists(config_file):
            print(f"  SKIP: {config_file} not found")
            failed += 1
            continue
        version = os.path.splitext(os.path.basename(config_file))[0]
        if upload_config(config_file, version, stack_name):
            success += 1
        else:
            failed += 1

    print(f"\nDone: {success} uploaded, {failed} failed")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
