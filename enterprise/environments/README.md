# Environment Configurations

Per-environment deployment parameters for the IDP stack. Each file defines the
CloudFormation parameters for one environment (dev, staging, prod).

## How it works

```
Git (source of truth)              S3 (per account)              Pipeline
enterprise/environments/           deploy/pipeline-config.yaml
├── dev.yaml          ──copy──▶    (in dev account S3)     ──▶   deploys with dev params
├── staging.yaml      ──copy──▶    (in staging account S3) ──▶   deploys with staging params
└── prod.yaml         ──copy──▶    (in prod account S3)    ──▶   deploys with prod params
```

1. Maintain config here in git (version controlled, PR-reviewed)
2. Push to each account's S3 source bucket as `deploy/pipeline-config.yaml`
3. When code.zip is dropped in S3, the pipeline reads its local config and deploys

## Sync to S3

```bash
# Dev account
aws s3 cp enterprise/environments/dev.yaml s3://<dev-source-bucket>/deploy/pipeline-config.yaml

# Staging account
aws s3 cp enterprise/environments/staging.yaml s3://<staging-source-bucket>/deploy/pipeline-config.yaml

# Prod account
aws s3 cp enterprise/environments/prod.yaml s3://<prod-source-bucket>/deploy/pipeline-config.yaml
```

## Configuration format

```yaml
stack_name: idp-prod
region: us-east-1
admin_email: admin@example.com

# Stack parameters (passed to idp-cli deploy --parameters "...")
parameters:
  WebUIHosting: ALB
  ALBVpcId: vpc-xxx
  ALBSubnetIds: subnet-aaa,subnet-bbb
  # ... all CloudFormation parameters for this environment
```

The pipeline's `codebuild_deployment.py` reads this file and constructs the
`idp-cli deploy` command with these parameters.
