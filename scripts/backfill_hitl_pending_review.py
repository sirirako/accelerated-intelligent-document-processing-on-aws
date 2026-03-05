# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
One-time backfill script to populate HITLPendingReview GSI attribute
on existing documents that are waiting in review state.

This script scans the TrackingTable for documents where:
  - PK starts with "doc#" (document records only)
  - HITLTriggered = true
  - HITLCompleted is not true
  - HITLStatus is not a completed/skipped status

For each matching document, it sets HITLPendingReview = "true" using a
conditional update that only writes if the attribute doesn't already exist.

Performance notes:
  - Uses parallel scan segments to speed up the scan phase
  - The scan reads every item but the FilterExpression runs server-side,
    so only matching items are returned over the network
  - Matching documents (pending HITL review) are typically a tiny fraction
    of the table — the write phase is fast
  - For a 100K-item table, expect ~30-60 seconds scan time with default
    settings; increase --segments for larger tables

Usage:
  # Dry run (default) - shows what would be updated
  python scripts/backfill_hitl_pending_review.py --table-name <TABLE_NAME>

  # Apply changes
  python scripts/backfill_hitl_pending_review.py --table-name <TABLE_NAME> --apply

  # With explicit region and more parallelism for large tables
  python scripts/backfill_hitl_pending_review.py --table-name <TABLE_NAME> --region us-west-2 --segments 10 --apply
"""

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

COMPLETED_STATUSES = {
    "completed",
    "reviewcompleted",
    "reviewcompleted",
    "skipped",
    "reviewskipped",
    "reviewskipped",
}

FILTER_EXPRESSION = (
    Attr("PK").begins_with("doc#")
    & Attr("HITLTriggered").eq(True)
    & (Attr("HITLCompleted").not_exists() | Attr("HITLCompleted").eq(False))
    & Attr("HITLPendingReview").not_exists()
)

PROJECTION = "PK, SK, ObjectKey, HITLStatus"


def _scan_segment(table, segment, total_segments):
    """Scan a single parallel segment."""
    documents = []
    scan_kwargs = {
        "FilterExpression": FILTER_EXPRESSION,
        "ProjectionExpression": PROJECTION,
        "Segment": segment,
        "TotalSegments": total_segments,
    }
    while True:
        response = table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            status = (item.get("HITLStatus") or "").lower().replace(" ", "")
            if status in COMPLETED_STATUSES:
                continue
            documents.append(item)
        if "LastEvaluatedKey" not in response:
            break
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return documents


def scan_pending_review_documents(table, total_segments):
    """Scan for documents in pending HITL review state using parallel segments."""
    documents = []
    with ThreadPoolExecutor(max_workers=total_segments) as executor:
        futures = {
            executor.submit(_scan_segment, table, seg, total_segments): seg
            for seg in range(total_segments)
        }
        for future in as_completed(futures):
            documents.extend(future.result())
    return documents


def backfill_document(table, pk, sk):
    """Set HITLPendingReview on a single document, only if not already set."""
    try:
        table.update_item(
            Key={"PK": pk, "SK": sk},
            UpdateExpression="SET HITLPendingReview = :val",
            ConditionExpression="attribute_not_exists(HITLPendingReview)",
            ExpressionAttributeValues={":val": "true"},
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Backfill HITLPendingReview attribute for existing pending review documents"
    )
    parser.add_argument(
        "--table-name", required=True, help="DynamoDB tracking table name"
    )
    parser.add_argument("--region", default=None, help="AWS region")
    parser.add_argument(
        "--segments",
        type=int,
        default=5,
        help="Number of parallel scan segments (default: 5, increase for large tables)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Without this flag, runs in dry-run mode.",
    )
    args = parser.parse_args()

    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    table = dynamodb.Table(args.table_name)

    logger.info(
        f"Scanning table '{args.table_name}' with {args.segments} parallel segments..."
    )
    documents = scan_pending_review_documents(table, args.segments)
    logger.info(f"Found {len(documents)} documents needing backfill")

    if not documents:
        logger.info("Nothing to do.")
        return

    for doc in documents:
        obj_key = doc.get("ObjectKey", doc["PK"])
        status = doc.get("HITLStatus", "N/A")
        logger.info(
            f"  {'[DRY RUN] ' if not args.apply else ''}"
            f"ObjectKey={obj_key}, HITLStatus={status}"
        )

    if not args.apply:
        logger.info(f"\nDry run complete. {len(documents)} documents would be updated.")
        logger.info("Run with --apply to execute the backfill.")
        return

    updated = 0
    skipped = 0
    for doc in documents:
        if backfill_document(table, doc["PK"], doc["SK"]):
            updated += 1
        else:
            skipped += 1

    logger.info(f"Backfill complete. Updated: {updated}, Already set: {skipped}")


if __name__ == "__main__":
    main()
