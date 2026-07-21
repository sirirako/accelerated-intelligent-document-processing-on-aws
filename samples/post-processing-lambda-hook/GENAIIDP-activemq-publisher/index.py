# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
GENAIIDP-activemq-publisher

Post-processing Lambda hook that publishes completed IDP document results to an
Amazon MQ for ActiveMQ broker over STOMP+SSL.

Invocation contract (see src/lambda/post_processing_decompressor/index.py):
  - Invoked ASYNCHRONOUSLY (InvocationType='Event') by the IDP stack's
    decompression Lambda. The return value is discarded; failures are retried by
    the Lambda service and then land in this function's own DLQ.
  - The payload is the original EventBridge event, with detail.output rewritten
    to contain the DECOMPRESSED document. detail.output is a JSON *string*.

The handler treats the incoming event as read-only.
"""

import copy
import json
import logging
import os
import ssl
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import boto3
import stomp

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# --- Configuration (all supplied by template.yaml) -------------------------

BROKER_SECRET_ARN = os.environ["BROKER_SECRET_ARN"]
BROKER_STOMP_ENDPOINTS = os.environ["BROKER_STOMP_ENDPOINTS"]  # "host:port,host:port"
DESTINATION = os.environ["DESTINATION"]  # e.g. "/queue/idp.document.completed"
DRY_RUN = os.environ.get("DRY_RUN", "false").strip().lower() == "true"
INCLUDE_SECTION_ATTRIBUTES = (
    os.environ.get("INCLUDE_SECTION_ATTRIBUTES", "true").strip().lower() == "true"
)
CONNECT_TIMEOUT_SECONDS = float(os.environ.get("CONNECT_TIMEOUT_SECONDS", "15"))
RECEIPT_TIMEOUT_SECONDS = float(os.environ.get("RECEIPT_TIMEOUT_SECONDS", "15"))
MAX_MESSAGE_BYTES = int(os.environ.get("MAX_MESSAGE_BYTES", "131072"))  # 128 KiB

# Sentinel written into the secret at stack-create time. Publishing is refused
# while the secret still holds it, so a half-configured stack fails loudly
# instead of opening an anonymous/garbage connection to the broker.
CREDENTIAL_PLACEHOLDER = "REPLACE_ME"

_secrets_client = boto3.client("secretsmanager")
_secret_cache: Dict[str, Any] = {"value": None, "fetched_at": 0.0}
_SECRET_TTL_SECONDS = 300


class _PublishListener(stomp.ConnectionListener):
    """Captures broker ERROR frames and RECEIPT acknowledgements."""

    def __init__(self) -> None:
        self.receipt_seen = threading.Event()
        self.error_frame: Optional[str] = None

    def on_error(self, frame) -> None:  # noqa: D102
        self.error_frame = getattr(frame, "body", str(frame))
        logger.error("STOMP ERROR frame from broker: %s", self.error_frame)
        self.receipt_seen.set()  # unblock the waiter; caller inspects error_frame

    def on_receipt(self, frame) -> None:  # noqa: D102
        logger.debug("STOMP receipt: %s", getattr(frame, "headers", {}))
        self.receipt_seen.set()

    def on_disconnected(self) -> None:  # noqa: D102
        self.receipt_seen.set()


def _parse_endpoints(raw: str) -> List[Tuple[str, int]]:
    """Parse "host:port,host:port" into stomp.py host_and_ports tuples."""
    endpoints: List[Tuple[str, int]] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        host, _, port = chunk.rpartition(":")
        if not host or not port.isdigit():
            raise ValueError(
                f"Invalid broker endpoint '{chunk}'. Expected host:port "
                "(Amazon MQ ActiveMQ STOMP+SSL default port is 61614)."
            )
        endpoints.append((host, int(port)))
    if not endpoints:
        raise ValueError("BROKER_STOMP_ENDPOINTS is empty.")
    return endpoints


def _get_credentials() -> Tuple[str, str]:
    """Fetch and cache broker credentials; refuse placeholder values."""
    now = time.monotonic()
    cached = _secret_cache["value"]
    if cached is not None and (now - _secret_cache["fetched_at"]) < _SECRET_TTL_SECONDS:
        return cached

    raw = _secrets_client.get_secret_value(SecretId=BROKER_SECRET_ARN)["SecretString"]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Secret {BROKER_SECRET_ARN} is not valid JSON; expected "
            '{"username": "...", "password": "..."}'
        ) from exc

    username = parsed.get("username", "")
    password = parsed.get("password", "")
    if not username or not password:
        raise ValueError(
            f"Secret {BROKER_SECRET_ARN} must contain non-empty 'username' and "
            "'password' keys."
        )
    if CREDENTIAL_PLACEHOLDER in (username, password):
        raise ValueError(
            f"Secret {BROKER_SECRET_ARN} still holds the placeholder value "
            f"'{CREDENTIAL_PLACEHOLDER}'. Populate it with the real Amazon MQ "
            "broker credentials before enabling this hook."
        )

    _secret_cache["value"] = (username, password)
    _secret_cache["fetched_at"] = now
    return username, password


def _extract_document(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pull the decompressed document out of the EventBridge event.

    Mirrors the shape-handling in the IDP decompression Lambda: the document may
    sit at output['document'] (pipeline mode), output['Result']['document']
    (BDA mode), or be the entire output.
    """
    detail = event.get("detail")
    if not isinstance(detail, dict):
        raise ValueError("Event is missing 'detail'; not a Step Functions event.")

    status = detail.get("status")
    if status != "SUCCEEDED":
        logger.info("Ignoring execution with status=%s", status)
        return {}

    raw_output = detail.get("output")
    if not raw_output:
        raise ValueError("Event detail has no 'output' payload.")

    output = json.loads(raw_output) if isinstance(raw_output, str) else raw_output
    if not isinstance(output, dict):
        raise ValueError("Step Functions output did not decode to an object.")

    if isinstance(output.get("document"), dict):
        return output["document"]
    result = output.get("Result")
    if isinstance(result, dict) and isinstance(result.get("document"), dict):
        return result["document"]

    logger.warning("Document not found in expected locations; using entire output.")
    return output


def _build_message(event: Dict[str, Any], document: Dict[str, Any]) -> Dict[str, Any]:
    """Build the broker payload. Reads only; never mutates the caller's event."""
    detail = event.get("detail", {})
    sections = []
    for section in document.get("sections") or []:
        if not isinstance(section, dict):
            continue
        entry = {
            "sectionId": section.get("section_id"),
            "classification": section.get("classification"),
            "pageIds": section.get("page_ids"),
            "extractionResultUri": section.get("extraction_result_uri"),
            "confidenceThresholdAlerts": section.get("confidence_threshold_alerts"),
        }
        if INCLUDE_SECTION_ATTRIBUTES:
            # deepcopy so downstream trimming can never touch the input event.
            entry["attributes"] = copy.deepcopy(section.get("attributes"))
        sections.append(entry)

    return {
        "schemaVersion": "1.0",
        "eventId": event.get("id"),
        "eventTime": event.get("time"),
        "executionArn": detail.get("executionArn"),
        "status": detail.get("status"),
        "document": {
            "id": document.get("id"),
            "inputBucket": document.get("input_bucket"),
            "inputKey": document.get("input_key"),
            "outputBucket": document.get("output_bucket"),
            "numPages": document.get("num_pages"),
            "status": document.get("status"),
            "summaryReportUri": document.get("summary_report_uri"),
            "evaluationReportUri": document.get("evaluation_report_uri"),
        },
        "sections": sections,
        "metering": document.get("metering"),
    }


def _publish(body: str, headers: Dict[str, str]) -> None:
    """Publish one persistent message and wait for the broker receipt."""
    endpoints = _parse_endpoints(BROKER_STOMP_ENDPOINTS)
    username, password = _get_credentials()

    listener = _PublishListener()
    conn = stomp.Connection(
        host_and_ports=endpoints,
        heartbeats=(0, 0),
        timeout=CONNECT_TIMEOUT_SECONDS,
        reconnect_attempts_max=len(endpoints),
    )
    # Amazon MQ terminates TLS with a public CA cert; verify it.
    conn.set_ssl(for_hosts=endpoints, ssl_version=ssl.PROTOCOL_TLS_CLIENT)
    conn.set_listener("publish", listener)

    try:
        conn.connect(username, password, wait=True, timeout=CONNECT_TIMEOUT_SECONDS)
        conn.send(
            destination=DESTINATION,
            body=body,
            content_type="application/json",
            headers=headers,
            receipt=headers["message-id"],
        )
        if not listener.receipt_seen.wait(RECEIPT_TIMEOUT_SECONDS):
            raise TimeoutError(
                f"No STOMP receipt from broker within {RECEIPT_TIMEOUT_SECONDS}s "
                f"for destination {DESTINATION}."
            )
        if listener.error_frame:
            raise RuntimeError(f"Broker rejected the message: {listener.error_frame}")
    finally:
        try:
            conn.disconnect()
        except Exception:  # pragma: no cover - best-effort socket teardown
            logger.debug("Ignoring error during STOMP disconnect", exc_info=True)


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """Entry point. Raises on failure so Lambda retries, then DLQs."""
    if not isinstance(event, dict):
        raise ValueError(f"Expected a dict event, got {type(event).__name__}")

    document = _extract_document(event)
    if not document:
        return {"published": False, "reason": "execution not SUCCEEDED"}

    message = _build_message(event, document)
    body = json.dumps(message, default=str)

    if len(body.encode("utf-8")) > MAX_MESSAGE_BYTES:
        # Amazon MQ accepts large frames, but oversized payloads are usually a
        # sign that per-section attributes belong in S3, not on the queue.
        logger.warning(
            "Message for document %s is %d bytes (limit %d); dropping section "
            "attributes and publishing references only.",
            message["document"]["id"],
            len(body.encode("utf-8")),
            MAX_MESSAGE_BYTES,
        )
        for section in message["sections"]:
            section.pop("attributes", None)
        message["attributesOmitted"] = True
        body = json.dumps(message, default=str)

    # Stable per-execution id lets consumers dedupe Lambda's async retries.
    correlation_id = message["executionArn"] or message["eventId"] or "unknown"
    headers = {
        "message-id": correlation_id,
        "correlation-id": correlation_id,
        "persistent": "true",
        "idp-document-id": str(message["document"]["id"]),
        "idp-schema-version": message["schemaVersion"],
    }

    if DRY_RUN:
        logger.info(
            "DRY_RUN=true - not publishing. destination=%s headers=%s body=%s",
            DESTINATION,
            headers,
            body,
        )
        return {"published": False, "dryRun": True, "bytes": len(body)}

    _publish(body, headers)
    logger.info(
        "Published document %s to %s (%d bytes)",
        message["document"]["id"],
        DESTINATION,
        len(body),
    )
    return {"published": True, "destination": DESTINATION, "bytes": len(body)}
