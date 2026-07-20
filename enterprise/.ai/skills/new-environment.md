# Skill: Set Up a New Environment

## When to use
Deploying IDP to a new AWS account/environment for the first time.

## Full guides
- **Deploy:** `enterprise/docs/deployment-guide.md`
- **Pipeline:** `enterprise/docs/sdlc-pipeline-setup.md`
- **Registry:** `enterprise/docs/private-registry-setup.md`
- **Config:** `enterprise/config-pipeline/README.md`

## Quick steps

1. **VPC endpoints:** `./scripts/create_vpc_endpoints.sh --vpc-id <vpc> --subnet-ids <subnets> --security-group-id <sg> --region <region>`
2. **Environment config:** Copy `enterprise/environments/dev.yaml` → `local-<env>.yaml`, fill values
3. **Upload config to S3:** `aws s3 cp enterprise/environments/local-<env>.yaml s3://<bucket>/deploy/pipeline-config.yaml`
4. **Build + publish + deploy:**
   ```bash
   ./enterprise/build.sh
   idp-cli publish --source-dir . --region <region>
   idp-cli deploy --stack-name <name> --template-url <url> --admin-email <email> --parameters "..."
   ```
5. **Deploy SDLC pipeline** (for automated deploys): see `docs/sdlc-pipeline-setup.md`
6. **Deploy config pipeline** (optional): see `config-pipeline/README.md`
7. **Verify:** Web UI via ALB, Jobs API via `test-jobs-api/`

## Common issues
- Stack names must be lowercase
- `ArtifactsBucketKmsKeyArn` required for KMS-encrypted S3
- CodeBuild needs NAT for Docker pulls
- Old stacks can't upgrade to v0.6 (Cognito schema constraint)
