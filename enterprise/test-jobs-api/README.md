# Jobs API Test Script

End-to-end test of the IDP Jobs API: submit → upload → poll → download results.

Available in both Python and PowerShell.

## Setup

1. Copy and fill in credentials:
   ```bash
   cp env_api.example .env_api
   # Edit .env_api with values from your stack outputs
   ```

2. Get credentials from your stack:
   ```bash
   # API endpoint and client ID (from stack outputs)
   aws cloudformation describe-stacks --stack-name <STACK> \
     --query 'Stacks[0].Outputs[?contains(OutputKey,`Api`)].{Key:OutputKey,Value:OutputValue}' --output table

   # Cognito domain (stack-name-api-account-id)
   # e.g. https://my-stack-api-123456789012.auth.us-east-1.amazoncognito.com

   # Client secret
   aws cognito-idp describe-user-pool-client \
     --user-pool-id <pool-id> --client-id <client-id> \
     --query 'UserPoolClient.ClientSecret' --output text
   ```

3. Prepare a test document:
   ```bash
   zip test-doc.zip document.pdf
   ```

## Run (PowerShell)

```powershell
.\test_jobs_api.ps1 -ZipFile "test-doc.zip"

# With configuration version
.\test_jobs_api.ps1 -ZipFile "test-doc.zip" -ConfigVersion "v2"
```

## Run (Python)

```bash
pip install requests
python test_jobs_api.py test-doc.zip

# With configuration version
python test_jobs_api.py test-doc.zip v2
```

## Ping Auth (Enterprise)

For deployments using Ping JWT authorizer (`EnableHeadless=true`):

### Setup

```bash
cp env_api_ping.example .env_api_ping
# Edit with Ping token endpoint, client ID/secret, username/password, API endpoint
```

### Run (PowerShell)

```powershell
# Full flow (gets token + tests API)
.\test_jobs_api_ping.ps1 -ZipFile "test-doc.zip"

# With a pre-fetched token
.\Get-PingToken.ps1 -TokenEndpoint "https://..." -ClientId "..." -ClientSecret "..." -Username "..." -Password "..."
.\test_jobs_api_ping.ps1 -ZipFile "test-doc.zip" -Token (Get-Clipboard)
```

### Run (Python)

```bash
python test_jobs_api_ping.py test-doc.zip

# With pre-fetched token
python test_jobs_api_ping.py test-doc.zip --token <jwt>
```

### Get a token only (for API Gateway console testing)

```powershell
.\Get-PingToken.ps1 -TokenEndpoint "https://..." -ClientId "..." -ClientSecret "..." -Username "..." -Password "..."
# Token is decoded and copied to clipboard
```

---

## Notes

- The Jobs API is a **Private API Gateway** — run the script from inside the VPC (WorkSpace, bastion, VPN)
- For Ping auth: use the VPC endpoint URL format (`https://<api-id>-<vpce-id>.execute-api...`)
- The Cognito token endpoint is public — token acquisition works from anywhere
- The Ping token endpoint may require VPC access (depends on customer network)
- Results are saved to `output/results.zip` and extracted to `output/results/`

## Output structure

```
output/results/
  jobs/{job_id}/{filename}/
    sections/{N}/result.json    ← structured extraction (key-value pairs)
    pages/{N}/result.json       ← raw OCR text per page
    pages/{N}/image.jpg         ← rendered page image
```
