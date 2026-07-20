# Skill: Test Jobs API

## When to use
Testing the headless Jobs API end-to-end (submit → upload → poll → download).

## Full guide
**Read `enterprise/test-jobs-api/README.md`** for setup instructions.
**Read `enterprise/docs/testing-skill.md`** for broader enterprise testing.

## Quick steps

1. Get API credentials (stack outputs + Cognito client secret)
2. Create `.env_api` from `env_api.example`
3. Run from inside the VPC:
   - PowerShell: `.\test_jobs_api.ps1 -ZipFile "test-doc.zip"`
   - Python: `python test_jobs_api.py test-doc.zip`

## Alternative: Lambda invoke (from outside VPC)

```bash
aws lambda invoke --function-name <stack>-ApiHandlerFunction-<id> \
  --cli-binary-format raw-in-base64-out \
  --payload '{"httpMethod":"POST","path":"/jobs","body":"{\"fileName\":\"test.zip\"}","requestContext":{"authorizer":{"claims":{"sub":"test","client_id":"test","scope":"idp-api/jobs.write idp-api/jobs.read"}}}}' \
  /tmp/response.json
```

## Expected results

`results.zip` contains:
```
jobs/{job_id}/{filename}/
  sections/{N}/result.json  — structured extraction (key-value)
  pages/{N}/result.json     — raw OCR text
  pages/{N}/image.jpg       — page images
```
