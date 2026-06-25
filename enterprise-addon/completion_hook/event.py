"""Pure parsing of the upstream completion event -> a notification message.

The upstream PostProcessingDecompressor invokes this hook asynchronously with the
full EventBridge "Step Functions Execution Status Change" event.
"""

import json


def _extract_document(output: dict) -> dict:
    if not isinstance(output, dict):
        return {}
    if "document" in output:
        return output["document"] or {}
    result = output.get("Result")
    if isinstance(result, dict) and "document" in result:
        return result["document"] or {}
    return output


def _first(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


def parse_completion(event: dict) -> dict:
    """Build the completion notification payload from the EventBridge event."""
    detail = event.get("detail") or {}

    out_raw = detail.get("output")
    try:
        output = json.loads(out_raw) if isinstance(out_raw, str) else (out_raw or {})
    except (ValueError, TypeError):
        output = {}

    doc = _extract_document(output)

    return {
        "document_id": _first(doc, "id", "object_key", "input_key", "objectKey", "key")
        or "",
        "status": detail.get("status", "SUCCEEDED"),
        "num_pages": doc.get("num_pages") or doc.get("numPages"),
        "results_location": _first(
            doc, "output_s3_uri", "outputS3Uri", "s3_uri", "output_key", "outputKey"
        ),
        "execution_arn": detail.get("executionArn", ""),
        "completed_at": detail.get("stopDate") or detail.get("completedAt"),
    }
