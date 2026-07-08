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

## Notes

- The Jobs API is a **Private API Gateway** — run the script from inside the VPC (WorkSpace, bastion, VPN)
- The Cognito token endpoint is public — token acquisition works from anywhere
- Results are saved to `output/results.zip` and extracted to `output/results/`

## Output structure

```
output/results/
  jobs/{job_id}/{filename}/
    sections/{N}/result.json    ← structured extraction (key-value pairs)
    pages/{N}/result.json       ← raw OCR text per page
    pages/{N}/image.jpg         ← rendered page image
```
