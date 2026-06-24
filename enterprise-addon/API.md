# IDP Jobs API — Integration Guide

REST API for programmatic document submission and result retrieval. Designed for machine-to-machine (M2M) integration with external systems such as loan origination, claims processing, or case management platforms.

## Base URL

```
https://{api-id}-{vpce-id}.execute-api.{region}.amazonaws.com/{stage}
```

The API is a **Private API Gateway** — it is only reachable through the configured VPC endpoint.

## Authentication

All requests (except where noted) require a Bearer token in the `Authorization` header.

```
Authorization: Bearer <token>
```

**How to obtain a token:**

```bash
curl -X POST https://your-ping-server.example.com/as/token \
  -d "grant_type=client_credentials&scope=jobs.read jobs.write" \
  -u "<client_id>:<client_secret>"
```

Response:
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "jobs.read jobs.write"
}
```

**Scopes:**

| Scope | Grants access to |
|---|---|
| `jobs.write` | `POST /jobs` (submit documents) |
| `jobs.read` | `GET /jobs/{job_id}` (check status, retrieve results) |

A token with `jobs.write` also satisfies `jobs.read`.

---

## Endpoints

### POST /jobs

Submit a document for processing. Returns a presigned upload URL.

**Required scope:** `jobs.write`

**Request:**

```json
{
  "fileName": "loan-application.zip",
  "metadata": {
    "source": "loan-origination-system"
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `fileName` | string | Yes | Filename with `.zip` extension. The zip should contain the document(s) to process. |
| `metadata` | object | No | Optional metadata attached to the job. |
| `metadata.source` | string | Yes (if metadata provided) | Identifier for the calling system. |

**Response (201):**

```json
{
  "jobId": "a3b2c1d4-5678-9012-abcd-ef3456789012",
  "upload": {
    "uploadUrl": "https://bucket.s3.amazonaws.com/jobs/a3b2c1d4.../loan-application.zip",
    "expiresInSeconds": 3600,
    "requiredHeaders": {
      "Content-Type": "application/zip",
      "key": "jobs/a3b2c1d4-.../loan-application.zip",
      "x-amz-credential": "...",
      "x-amz-date": "...",
      "x-amz-security-token": "...",
      "x-amz-signature": "...",
      "policy": "..."
    }
  }
}
```

**After receiving the response**, upload the file using the presigned POST URL:

```bash
curl -X POST "${uploadUrl}" \
  -F "Content-Type=application/zip" \
  -F "key=jobs/a3b2c1d4-.../loan-application.zip" \
  -F "x-amz-credential=..." \
  -F "x-amz-date=..." \
  -F "x-amz-security-token=..." \
  -F "policy=..." \
  -F "x-amz-signature=..." \
  -F "file=@loan-application.zip"
```

Once uploaded, IDP automatically begins processing (OCR, classification, extraction, assessment).

---

### GET /jobs/{job_id}

Check job status and retrieve results when complete.

**Required scope:** `jobs.read`

**Path parameters:**

| Parameter | Description |
|---|---|
| `job_id` | The `jobId` returned from `POST /jobs` |

**Response (200) — Processing:**

```json
{
  "jobId": "a3b2c1d4-5678-9012-abcd-ef3456789012",
  "status": "IN_PROGRESS",
  "timestamps": {
    "createdAt": "2026-06-24T10:00:00Z",
    "updatedAt": "2026-06-24T10:02:30Z"
  },
  "files": {
    "loan-application.zip": "IN_PROGRESS"
  }
}
```

**Response (200) — Completed:**

```json
{
  "jobId": "a3b2c1d4-5678-9012-abcd-ef3456789012",
  "status": "SUCCEEDED",
  "timestamps": {
    "createdAt": "2026-06-24T10:00:00Z",
    "updatedAt": "2026-06-24T10:05:15Z"
  },
  "files": {
    "loan-application.zip": "COMPLETED"
  },
  "result": {
    "downloadUrl": "https://bucket.s3.amazonaws.com/jobs/a3b2c1d4.../results.zip?X-Amz-...",
    "expiresInSeconds": 3600
  }
}
```

The `downloadUrl` is a presigned S3 URL that expires after the indicated time. The `results.zip` contains the extraction output for each document in the submission.

---

## Job statuses

| Status | Meaning |
|---|---|
| `PENDING_UPLOAD` | Job created but file not yet uploaded |
| `IN_PROGRESS` | File uploaded, processing underway |
| `SUCCEEDED` | All documents processed successfully |
| `PARTIALLY_SUCCEEDED` | Some documents succeeded, some failed |
| `FAILED` | All documents failed processing |
| `ABORTED` | Processing was aborted |

---

## Completion notifications (optional)

If the completion hook is enabled, your system receives a message on your RabbitMQ broker when processing finishes — no polling required.

**Message (published to your configured exchange/routing key):**

```json
{
  "document_id": "jobs/a3b2c1d4-.../loan-application.zip",
  "status": "SUCCEEDED",
  "num_pages": 4,
  "results_location": "s3://output-bucket/jobs/a3b2c1d4-.../results.json",
  "execution_arn": "arn:aws:states:us-east-1:123456789:execution:IDP-...:a3b2c1d4-...",
  "completed_at": "2026-06-24T10:05:15Z"
}
```

On receiving this message, call `GET /jobs/{job_id}` to get the presigned download URL for results.

---

## Error responses

Errors follow a standard structure:

```json
{
  "statusCode": 400,
  "message": "Unsupported file type. Only .zip files are supported"
}
```

| Status code | Meaning |
|---|---|
| 400 | Bad request (invalid filename, missing required fields) |
| 401 | Unauthorized (missing or invalid token) |
| 403 | Forbidden (valid token but insufficient scope) |
| 404 | Job not found (or belongs to a different client) |
| 500 | Internal server error |

---

## Complete example

```bash
# 1. Get a token from PingFederate
TOKEN=$(curl -s -X POST https://sso.corp.example.com/as/token \
  -d "grant_type=client_credentials&scope=jobs.read jobs.write" \
  -u "my-client-id:my-client-secret" | jq -r .access_token)

# 2. Submit a job
RESPONSE=$(curl -s -X POST \
  https://{api-id}-{vpce-id}.execute-api.us-east-1.amazonaws.com/beta/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"fileName": "documents.zip", "metadata": {"source": "my-system"}}')

JOB_ID=$(echo $RESPONSE | jq -r .jobId)
UPLOAD_URL=$(echo $RESPONSE | jq -r .upload.uploadUrl)

# 3. Upload the file (using the presigned POST fields)
# (construct multipart form from .upload.requiredHeaders + file)

# 4. Poll for completion (or wait for MQ notification)
curl -s \
  https://{api-id}-{vpce-id}.execute-api.us-east-1.amazonaws.com/beta/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN"

# 5. Download results when status=SUCCEEDED
DOWNLOAD_URL=$(curl -s \
  https://{api-id}-{vpce-id}.execute-api.us-east-1.amazonaws.com/beta/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN" | jq -r .result.downloadUrl)

curl -o results.zip "$DOWNLOAD_URL"
```

---

## Job isolation

Each API client can only see jobs it created. A `GET /jobs/{job_id}` request for a job created by a different client returns `404` — not `403` — to avoid leaking the existence of other clients' jobs.
