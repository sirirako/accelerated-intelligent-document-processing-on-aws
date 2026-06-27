# IDP Jobs API — Integration Guide

REST API for programmatic document submission and result retrieval. Designed for machine-to-machine (M2M) integration with external systems such as loan origination, claims processing, or case management platforms.

## Base URL

```
https://{api-id}-{vpce-id}.execute-api.{region}.amazonaws.com/{stage}
```

The API is a **Private API Gateway** — it is only reachable through the configured VPC endpoint.

## Authentication

All requests (except where noted) require a Bearer token in the `Authorization` header.

The token can be provided in any of these headers:

| Header | Format |
|---|---|
| `Authorization` | `Bearer <token>` |
| Custom header | `<token>` (raw JWT) — configurable via `CUSTOM_TOKEN_HEADER` env var |
| `x-jwt-token` | `<token>` (raw JWT) |

**How to obtain a token:**

```bash
curl -X POST https://your-ping-server.example.com/as/token \
  -d "grant_type=client_credentials" \
  -u "<client_id>:<client_secret>"
```

Response:
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

**Authorization model:**

The authorizer validates:
1. **JWT signature** — verified against the issuer's JWKS endpoint (RS256, ES256, or HS256)
2. **Issuer** — must match one of the configured Ping issuers
3. **Role membership** (if `PingRequiredRoles` is configured) — the token's `userRoles` or `memberOf` claim must contain at least one of the required roles

If all checks pass, the caller has full access to all Jobs API endpoints. There is no per-method scope differentiation — a valid token with the required role can call both `POST /jobs` and `GET /jobs/{id}`.

**Multiple issuers:**

The authorizer supports up to two Ping environments (configured via `PingIssuer1`/`PingJwksUri1` and optionally `PingIssuer2`/`PingJwksUri2`). It tries each issuer's JWKS to find the signing key, so tokens from either environment are accepted.

---

## Endpoints

### POST /jobs

Submit a document for processing. Returns a presigned upload URL.

**Required scope:** `jobs.write`

**Request:**

```json
{
  "fileName": "loan-application.zip",
  "configurationVersion": "lending-v2",
  "metadata": {
    "source": "loan-origination-system"
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `fileName` | string | Yes | Filename with `.zip` extension. The zip should contain the document(s) to process. |
| `configurationVersion` | string | No | Processing configuration version to use (e.g. `v1`, `lending-v2`). If omitted, the stack's active/default configuration is used. Max 128 chars, alphanumeric + `.` `_` `-` only. |
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
  "configurationVersion": "lending-v2",
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
  "configurationVersion": "lending-v2",
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

The `downloadUrl` is a presigned S3 URL that expires after the indicated time. The `results.zip` contains all processing outputs for each document in the submission.

---

## Results ZIP structure

The downloaded `results.zip` contains three types of data per document:

```
jobs/{job_id}/{filename}/
├── sections/
│   └── {section_number}/
│       └── result.json          ← Structured extraction (key-value pairs)
└── pages/
    └── {page_number}/
        ├── result.json          ← Raw OCR text for this page
        └── image.jpg            ← Rendered page image
```

### Structured extraction (`sections/{N}/result.json`)

Contains the classified document type and extracted fields:

```json
{
  "document_class": {
    "type": "W2"
  },
  "split_document": {
    "page_indices": [0, 1]
  },
  "inference_result": {
    "employee_name": "Jane Smith",
    "employer_name": "Acme Corp",
    "wages": "85000.00",
    "federal_tax_withheld": "12750.00"
  },
  "metadata": {
    "extraction_time_seconds": 3.2,
    "extraction_method": "agentic",
    "parsing_succeeded": true
  }
}
```

### Raw OCR text (`pages/{N}/result.json`)

Contains the full text extracted from each page by OCR (Textract or Bedrock):

```json
{
  "text": "FORM W-2 Wage and Tax Statement 2024\nEmployee: Jane Smith\nSSN: XXX-XX-1234\nEmployer: Acme Corp\nEIN: 12-3456789\nWages: $85,000.00\n..."
}
```

### Page images (`pages/{N}/image.jpg`)

The rendered page image (JPEG). Useful for visual verification or display alongside extracted data.

### Multi-document example

A zip containing a lending package (loan application + W2 + bank statement) produces:

```
jobs/a3b2c1d4-.../lending_package.pdf/
├── sections/
│   ├── 0/result.json    ← loan application extraction
│   ├── 1/result.json    ← W2 extraction
│   └── 2/result.json    ← bank statement extraction
└── pages/
    ├── 0/
    │   ├── result.json  ← page 1 OCR text
    │   └── image.jpg
    ├── 1/
    │   ├── result.json  ← page 2 OCR text
    │   └── image.jpg
    └── 2/
        ├── result.json  ← page 3 OCR text
        └── image.jpg
```

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
| 422 | Validation error (e.g. invalid `configurationVersion` format) |
| 500 | Internal server error |

---

## Complete example

```bash
# 1. Get a token from PingFederate
TOKEN=$(curl -s -X POST https://sso.corp.example.com/as/token \
  -d "grant_type=client_credentials&scope=jobs.read jobs.write" \
  -u "my-client-id:my-client-secret" | jq -r .access_token)

# 2. Submit a job (with optional configurationVersion)
RESPONSE=$(curl -s -X POST \
  https://{api-id}-{vpce-id}.execute-api.us-east-1.amazonaws.com/beta/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"fileName": "documents.zip", "configurationVersion": "lending-v2", "metadata": {"source": "my-system"}}')

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
