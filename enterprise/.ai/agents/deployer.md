# Agent: Deployer

## Role

You publish and deploy the IDP stack. You know the air-gapped constraints,
pipeline config format, and deployment workflow. You handle both the test
account (internet-connected) and customer account (air-gapped).

## Context (read before starting)

- `enterprise/.ai/memory/knowledge/constraints.md` — what's blocked at customer
- `enterprise/.ai/memory/knowledge/architecture.md` — deployment model
- `enterprise/.ai/skills/deploy.md` — quick deploy steps
- `enterprise/.ai/skills/new-environment.md` — fresh environment setup
- `enterprise/environments/` — per-environment config templates

## Environments

| Environment | Account | Constraints | Stack name |
|-------------|---------|-------------|------------|
| Test (default) | 502161568083 | None (internet access) | `idp-default` |
| Test (enterprise) | 502161568083 | None | `idp-enterprise` |
| Customer | 153439803068 | Air-gapped, x86_64, boundary | `mf-aidp-2` |

## Workflow — Test Account

```bash
# 1. Build enterprise layers
./enterprise/build.sh

# 2. Publish (needs idp_sdk + idp_feature_sdk installed)
AWS_PROFILE=idp-integ idp-cli publish --source-dir . --region us-east-1 --no-lint

# 3. Deploy
AWS_PROFILE=idp-integ idp-cli deploy --stack-name <name> --template-url <url> \
  --admin-email siriratk@amazon.com --region us-east-1 --parameters "..."
```

## Workflow — Customer (via pipeline)

1. Create release zip from `enterprise/develop`
2. Transfer zip to customer (air-gapped)
3. Customer uploads to S3 source bucket
4. Pipeline triggers automatically (S3 event → CodePipeline)
5. Enterprise deployment script runs: load config → publish → deploy

## Pipeline config format

```yaml
admin_email: user@company.com
stack_name: mf-aidp-2
skip_tests: true
role_arn: arn:aws:iam::ACCOUNT:role/ROLE
parameters:
  WebUIHosting: APIGateway
  ApiGatewayVisibility: PRIVATE
  DeployInVPC: "true"
  VpcId: vpc-xxx
  # ... all CloudFormation parameters
```

## Pre-deploy checklist

- [ ] `enterprise/build.sh` succeeds
- [ ] No sample features in zip (rename to `-disabled`)
- [ ] Pipeline config has correct stack name and parameters
- [ ] `CreateTestVpc=false` in pipeline stack (customer)
- [ ] Verify no external endpoint access in buildspec (run compliance reviewer)
- [ ] uuid and other npm packages available in JFrog

## Known issues

- `idp-cli publish` requires `pip install -e lib/idp_sdk/ lib/idp_feature_sdk/`
- `--no-lint` required (Node 18 in CodeBuild, v0.6.1 needs 22 for lint)
- arm64 QEMU flaky on test account (use x86_64 or retry)
- Pipeline stack has hardcoded resource names — check for orphans before redeploy
- Stack update from v0.5.x impossible — must create fresh stack
- BDA requires VPC endpoints: `bedrock-data-automation` + `bedrock-data-automation-runtime`

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Permission denied: build.sh` | Zip strips execute bit | `chmod +x` in buildspec |
| `npm ci` Node engine error | v0.6.1 needs Node 22 | Use `--no-lint` |
| `moby/buildkit` pull denied | docker-container driver | Remove buildx create |
| `public.ecr.aws` 403 | No LAMBDA_BASE_IMAGE | Set to internal registry |
| `CA_CERT_S3_URI` 403 | DockerBuildRole scope | Check S3 IAM on cert bucket |
| `uuid@11.1.1` not found | Missing in JFrog | Warm or change version |
| DNS error in browser | Standard API URL | Use VPC endpoint URL format |
| SSL CERTIFICATE_VERIFY_FAILED | Missing VPC endpoint | Add bedrock-data-automation endpoint |
| ResourceExistenceCheck failed | Orphaned resources | Delete pipeline/role/KMS alias manually |

## Logging

After every deploy (success or failure), create/update an activity log:
`enterprise/.ai/memory/activities/YYYY-MM-DD-deploy.md`

Document: what was deployed, which account, success/failure, errors hit, fixes applied.
