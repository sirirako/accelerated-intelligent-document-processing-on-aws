# Skill: Set Up a New Environment

## When to use
Deploying IDP to a new AWS account/environment for the first time.

## Prerequisites

- AWS account with admin access
- VPC with:
  - Private subnets (at least 1, ideally 2 in different AZs)
  - NAT Gateway (CodeBuild needs internet for Docker pulls)
  - Security group allowing outbound HTTPS (443)
- ACM certificate (self-signed OK for testing)
- S3 bucket for source artifacts (pipeline trigger)

## Steps

### 1. Create VPC endpoints

Required for private deployment:
```bash
./scripts/create_vpc_endpoints.sh \
  --vpc-id <vpc-id> \
  --subnet-ids <subnet-a>,<subnet-b> \
  --security-group-id <sg-id> \
  --region <region>
```

Ensure `execute-api` endpoint is created (for Private API Gateway).

### 2. Create the environment config

Copy `enterprise/environments/dev.yaml` → `enterprise/environments/local-<env>.yaml`
Fill in all VPC, subnet, SG, cert, Ping values.

### 3. Upload config to S3

```bash
aws s3 cp enterprise/environments/local-<env>.yaml s3://<source-bucket>/deploy/pipeline-config.yaml
```

### 4. Deploy (manual first time)

```bash
./enterprise/build.sh
idp-cli publish --source-dir . --bucket-basename <bucket> --prefix idp --region <region>
idp-cli deploy --stack-name <name> --template-url <url> --admin-email <email> \
  --region <region> --wait --parameters "<from your local config>"
```

### 5. Deploy the SDLC pipeline (for subsequent deploys)

```bash
aws cloudformation deploy \
  --stack-name <name>-sdlc-pipeline \
  --template-file scripts/sdlc/cfn/codepipeline-s3.yml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    BucketNamePrefix=<source-bucket-prefix> \
    PipelineName=<name>-deploy
```

### 6. Deploy the config pipeline (optional)

```bash
aws cloudformation deploy \
  --stack-name <name>-config-pipeline \
  --template-file enterprise/config-pipeline/cfn/config-pipeline.yml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    SourceBucketName=<config-bucket> \
    IdpStackName=<stack-name>
```

### 7. Verify

- Web UI accessible via ALB URL
- Jobs API: run `enterprise/test-jobs-api/test_jobs_api.ps1`
- VPC endpoints: `./scripts/check-vpc-endpoints.sh`

## Common issues

| Issue | Fix |
|---|---|
| `ApiUserPoolDomain` Invalid request | Stack name must be lowercase |
| CodeBuild `kms:Decrypt` AccessDenied | Add `ArtifactsBucketKmsKeyArn` to params |
| CodeBuild Docker timeout | Verify NAT gateway exists and SG allows outbound 443 |
| Cognito schema upgrade fails | Old stacks can't upgrade — deploy fresh |
