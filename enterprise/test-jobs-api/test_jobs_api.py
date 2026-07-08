#!/usr/bin/env python3
"""
End-to-end test of the IDP Jobs API.

Usage:
    1. Copy env_api.example to .env_api and fill in values
    2. Place a test zip file (e.g. test-doc.zip containing a PDF) in this directory
    3. Run: python test_jobs_api.py test-doc.zip

The script:
    1. Gets a Cognito M2M access token (client-credentials)
    2. POST /jobs — submits the file, gets presigned upload URL
    3. Uploads the zip to S3 via presigned POST
    4. Polls GET /jobs/{id} until terminal status
    5. Downloads results.zip and extracts it
"""

import json
import os
import sys
import time
import zipfile
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).parent


def load_env():
    env_file = SCRIPT_DIR / ".env_api"
    if not env_file.exists():
        print(
            "ERROR: .env_api not found. Copy env_api.example to .env_api and fill in values."
        )
        sys.exit(1)
    env = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def get_token(cognito_domain, client_id, client_secret):
    """Get M2M access token via client-credentials grant."""
    print("1. Getting Cognito access token...")
    resp = requests.post(
        f"{cognito_domain}/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "scope": "idp-api/jobs.read idp-api/jobs.write",
        },
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code != 200:
        print(f"   FAILED: {resp.status_code} {resp.text}")
        sys.exit(1)
    token = resp.json()["access_token"]
    print(f"   OK — token: {token[:30]}...")
    return token


def submit_job(api_endpoint, token, filename, config_version=None):
    """POST /jobs — submit a document for processing."""
    print(f"2. Submitting job for: {filename}")
    body = {"fileName": filename}
    if config_version:
        body["configurationVersion"] = config_version
    resp = requests.post(
        f"{api_endpoint}/jobs",
        json=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    if resp.status_code != 200:
        print(f"   FAILED: {resp.status_code} {resp.text}")
        sys.exit(1)
    data = resp.json()
    job_id = data["jobId"]
    upload_url = data["upload"]["uploadUrl"]
    required_headers = data["upload"]["requiredHeaders"]
    print(f"   OK — jobId: {job_id}")
    print(f"   Upload URL: {upload_url}")
    return job_id, upload_url, required_headers


def upload_file(upload_url, required_headers, file_path):
    """Upload the file via presigned POST."""
    print("3. Uploading file to S3...")
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f)}
        resp = requests.post(upload_url, data=required_headers, files=files)
    if resp.status_code not in (200, 201, 204):
        print(f"   FAILED: {resp.status_code} {resp.text}")
        sys.exit(1)
    print(f"   OK — upload complete (status: {resp.status_code})")


def poll_status(api_endpoint, token, job_id, interval=5, timeout=300):
    """Poll GET /jobs/{id} until terminal status."""
    print(f"4. Polling job status (every {interval}s, timeout {timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(
            f"{api_endpoint}/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            print(f"   ERROR: {resp.status_code} {resp.text}")
            sys.exit(1)
        data = resp.json()
        status = data["status"]
        elapsed = int(time.time() - start)
        print(f"   [{elapsed}s] Status: {status}")

        if status in ("SUCCEEDED", "PARTIALLY_SUCCEEDED", "FAILED", "ABORTED"):
            print(f"\n   Final status: {status}")
            if data.get("configurationVersion"):
                print(f"   Config version: {data['configurationVersion']}")
            return data

        time.sleep(interval)

    print(f"   TIMEOUT after {timeout}s — last status: {status}")
    sys.exit(1)


def download_results(result_data, output_dir):
    """Download and extract results.zip."""
    result = result_data.get("result")
    if not result:
        print("5. No results available (job may have failed)")
        return

    download_url = result["downloadUrl"]
    print("5. Downloading results...")

    resp = requests.get(download_url)
    if resp.status_code != 200:
        print(f"   FAILED: {resp.status_code}")
        sys.exit(1)

    zip_path = output_dir / "results.zip"
    zip_path.write_bytes(resp.content)
    print(f"   Saved: {zip_path} ({len(resp.content)} bytes)")

    # Extract
    extract_dir = output_dir / "results"
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)
    print(f"   Extracted to: {extract_dir}")

    # Show structure
    print("\n   Results structure:")
    for p in sorted(extract_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(extract_dir)
            size = p.stat().st_size
            print(f"     {rel} ({size} bytes)")

    # Show extraction results (sections/*/result.json)
    for result_json in sorted(extract_dir.rglob("sections/*/result.json")):
        print(f"\n   === {result_json.relative_to(extract_dir)} ===")
        data = json.loads(result_json.read_text())
        print(
            f"   Document class: {data.get('document_class', {}).get('type', 'unknown')}"
        )
        inference = data.get("inference_result", {})
        print(f"   Extracted fields ({len(inference)}):")
        for k, v in list(inference.items())[:10]:
            print(f"     {k}: {v}")
        if len(inference) > 10:
            print(f"     ... and {len(inference) - 10} more fields")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file.zip> [configurationVersion]")
        print(f"       {sys.argv[0]} test-doc.zip")
        print(f"       {sys.argv[0]} test-doc.zip v2")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    config_version = sys.argv[2] if len(sys.argv) > 2 else None

    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    if not file_path.name.endswith(".zip"):
        print("ERROR: File must be a .zip")
        sys.exit(1)

    env = load_env()
    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(exist_ok=True)

    # Step 1: Get token
    token = get_token(env["COGNITO_DOMAIN"], env["CLIENT_ID"], env["CLIENT_SECRET"])

    # Step 2: Submit job
    job_id, upload_url, required_headers = submit_job(
        env["API_ENDPOINT"], token, file_path.name, config_version
    )

    # Step 3: Upload file
    upload_file(upload_url, required_headers, file_path)

    # Step 4: Poll until done
    result_data = poll_status(env["API_ENDPOINT"], token, job_id)

    # Step 5: Download results
    download_results(result_data, output_dir)

    print("\nDone!")


if __name__ == "__main__":
    main()
