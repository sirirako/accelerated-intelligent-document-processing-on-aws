# Skill: Test Jobs API

## When to use
Testing the headless Jobs API end-to-end (submit → upload → poll → download results).

## Prerequisites
- Stack deployed with `EnableHeadless=true`
- Access from inside the VPC (WorkSpace, bastion, VPN) — Private API Gateway
- Cognito client ID and secret (from stack outputs)

## Get credentials

```bash
# API endpoint + client ID (from stack outputs)
aws cloudformation describe-stacks --stack-name <STACK> \
  --query 'Stacks[0].Outputs[?contains(OutputKey,`Api`)].{Key:OutputKey,Value:OutputValue}' --output table

# Find the API user pool
aws cognito-idp list-user-pools --max-results 20 \
  --query 'UserPools[?contains(Name,`<stack-name>-api`)].Id' --output text

# Get client secret
aws cognito-idp describe-user-pool-client \
  --user-pool-id <pool-id> --client-id <client-id> \
  --query 'UserPoolClient.ClientSecret' --output text
```

## Test scripts

Located at `enterprise/test-jobs-api/`:
- `test_jobs_api.ps1` — PowerShell (for Windows WorkSpaces)
- `test_jobs_api.py` — Python (requires `pip install requests`)

Both read from `.env_api` (copy from `env_api.example`).

## Quick test (PowerShell)

```powershell
Compress-Archive -Path "document.pdf" -DestinationPath "test-doc.zip"
.\test_jobs_api.ps1 -ZipFile "test-doc.zip"
```

## Quick test (Lambda invoke, from outside VPC)

```bash
aws lambda invoke --function-name <stack>-ApiHandlerFunction-<id> \
  --cli-binary-format raw-in-base64-out \
  --payload '{"httpMethod":"POST","path":"/jobs","body":"{\"fileName\":\"test.zip\"}","requestContext":{"authorizer":{"claims":{"sub":"test","client_id":"test","scope":"idp-api/jobs.write idp-api/jobs.read"}}}}' \
  /tmp/response.json && cat /tmp/response.json | python3 -m json.tool
```

## Expected results

`results.zip` contains:
```
jobs/{job_id}/{filename}/
  sections/{N}/result.json  — structured extraction (key-value)
  pages/{N}/result.json     — raw OCR text
  pages/{N}/image.jpg       — page images
```

## With configurationVersion

```powershell
.\test_jobs_api.ps1 -ZipFile "test-doc.zip" -ConfigVersion "lending-v2"
```
