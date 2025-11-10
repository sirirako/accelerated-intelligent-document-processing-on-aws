#!/usr/bin/env python3
import concurrent.futures
import time
from typing import List

import boto3
from botocore.config import Config


def delete_log_group(log_group_name: str) -> str:
    """Delete a single log group"""
    try:
        config = Config(
            read_timeout=30, connect_timeout=10, retries={"max_attempts": 2}
        )
        client = boto3.client("logs", config=config)
        client.delete_log_group(logGroupName=log_group_name)
        return f"✓ Deleted: {log_group_name}"
    except Exception as e:
        return f"✗ Failed to delete {log_group_name}: {str(e)}"


def get_idp_log_groups() -> List[str]:
    """Get all log groups with 'LMA' in the name"""
    config = Config(read_timeout=30, connect_timeout=10, retries={"max_attempts": 2})
    client = boto3.client("logs", config=config)
    log_groups = []
    next_token = None
    page_count = 0

    print("Scanning for log groups...")
    while True:
        try:
            page_count += 1
            print(f"Processing page {page_count}...")

            kwargs = {"limit": 50}
            if next_token:
                kwargs["nextToken"] = next_token

            response = client.describe_log_groups(**kwargs)

            page_idp_count = 0
            for log_group in response["logGroups"]:
                if "LMA" in log_group["logGroupName"]:
                    log_groups.append(log_group["logGroupName"])
                    page_idp_count += 1

            print(
                f"Page {page_count}: {page_idp_count} idp- groups, {len(log_groups)} total so far"
            )

            if "nextToken" not in response:
                print("Reached end of log groups")
                break
            next_token = response["nextToken"]

        except Exception as e:
            print(f"Error on page {page_count}: {e}")
            break

    return log_groups


def main():
    log_groups = get_idp_log_groups()

    if not log_groups:
        print("No log groups found with 'idp-' in the name.")
        return

    print(f"\nTotal found: {len(log_groups)} log groups")

    confirm = input(f"Delete all {len(log_groups)} log groups? (y/N): ")
    if confirm.lower() != "y":
        print("Cancelled.")
        return

    # Process in batches of 50
    batch_size = 50
    total_deleted = 0
    total_failed = 0

    for i in range(0, len(log_groups), batch_size):
        batch = log_groups[i : i + batch_size]
        batch_num = (i // batch_size) + 1

        print(
            f"Processing batch {batch_num}/{(len(log_groups) + batch_size - 1) // batch_size} ({len(batch)} log groups)..."
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_name = {
                executor.submit(delete_log_group, name): name for name in batch
            }

            for future in concurrent.futures.as_completed(future_to_name, timeout=60):
                result = future.result()
                if result.startswith("✓"):
                    total_deleted += 1
                else:
                    total_failed += 1
                    print(result)

        print(
            f"Batch {batch_num} complete: {total_deleted} total deleted, {total_failed} total failed"
        )
        time.sleep(0.5)

    print(f"\nFinal results: {total_deleted} deleted, {total_failed} failed")


if __name__ == "__main__":
    main()
