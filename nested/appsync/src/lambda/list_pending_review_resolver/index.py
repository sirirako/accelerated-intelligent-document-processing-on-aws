# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Lambda resolver for listPendingReviewDocuments GraphQL query."""

import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Key
from idp_common.dynamodb.service import convert_decimals_to_native

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

dynamodb = boto3.resource("dynamodb")

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
BATCH_GET_LIMIT = 100
GSI_NAME = "HITLPendingReviewIndex"


def _batch_get_documents(table_name, object_keys):
    """Fetch full document records using BatchGetItem."""
    if not object_keys:
        return {}

    ddb_client = boto3.client("dynamodb")
    deserializer = boto3.dynamodb.types.TypeDeserializer()
    documents = {}

    for i in range(0, len(object_keys), BATCH_GET_LIMIT):
        chunk = object_keys[i : i + BATCH_GET_LIMIT]
        keys = [{"PK": {"S": key}, "SK": {"S": "none"}} for key in chunk]
        request_items = {table_name: {"Keys": keys}}

        while request_items:
            response = ddb_client.batch_get_item(RequestItems=request_items)
            for item in response.get("Responses", {}).get(table_name, []):
                doc = {k: deserializer.deserialize(v) for k, v in item.items()}
                if doc.get("PK"):
                    documents[doc["PK"]] = doc
            request_items = response.get("UnprocessedKeys", {})

    return documents


def handler(event, context):
    """AppSync Lambda resolver handler."""
    logger.info("listPendingReviewDocuments invoked")
    logger.debug(f"Event: {json.dumps(event, default=str)}")

    args = event.get("arguments", {})
    limit = min(args.get("limit") or DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE)
    next_token = args.get("nextToken")

    table_name = os.environ["TRACKING_TABLE_NAME"]
    table = dynamodb.Table(table_name)

    # Query the sparse GSI — only documents with HITLPendingReview attribute exist here
    query_kwargs = {
        "IndexName": GSI_NAME,
        "KeyConditionExpression": Key("HITLPendingReview").eq("true"),
        "ScanIndexForward": False,  # Most recent first
        "Limit": limit,
    }

    if next_token:
        try:
            query_kwargs["ExclusiveStartKey"] = json.loads(next_token)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Invalid nextToken: {next_token}")

    response = table.query(**query_kwargs)
    gsi_items = response.get("Items", [])

    # Build next token from LastEvaluatedKey
    last_key = response.get("LastEvaluatedKey")
    result_next_token = (
        json.dumps(convert_decimals_to_native(last_key)) if last_key else None
    )

    # Extract PKs and batch-fetch full document records
    pks = [item["PK"] for item in gsi_items if item.get("PK")]
    documents_map = _batch_get_documents(table_name, pks)

    # Build response preserving GSI query order
    documents = []
    for item in gsi_items:
        pk = item.get("PK")
        if pk and pk in documents_map:
            documents.append(convert_decimals_to_native(documents_map[pk]))

    logger.info(
        f"Returning {len(documents)} pending review documents, "
        f"hasNextPage={result_next_token is not None}"
    )

    return {"Documents": documents, "nextToken": result_next_token}
