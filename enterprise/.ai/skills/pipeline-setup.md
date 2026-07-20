# SDLC/CD Pipeline Setup

Automated pipeline that builds, publishes, and deploys the IDP accelerator from a code zip uploaded to S3.

## Overview

The pipeline supports three modes controlled by a per-environment config file:

| Mode | Config | Behavior |
|------|--------|----------|
| **CI (testing)** | No `stack_name`, no `skip_tests` | Deploy → Test → Tear down |
| **CD (production)** | `stack_name` + `skip_tests: true` | Publish → Deploy/Update → Done |
| **CD + smoke test** | `stack_name`, no `skip_tests` | Deploy/Update → Test → Keep stack |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  S3 Source Bucket (per account)                                     │
│                                                                     │
│  deploy/code.zip              ← Triggers pipeline on upload         │
│  deploy/pipeline-config.yaml  ← This environment's config          │
└────────────────┬────────────────────────────────────────────────────┘
                 │ EventBridge (Object Created on deploy/code.zip)
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  CodePipeline (one per environment/account)                         │
│  ├── Source Stage: Pull code.zip                                    │
│  └── Build Stage: CodeBuild runs codebuild_deployment.py            │
│       1. Download config from S3 (deploy/pipeline-config.yaml)      │
│       2. Build enterprise layers (enterprise/build.sh)              │
│       3. Publish templates (SAM build + Docker images → S3)         │
│       4. Deploy CFN stack (idp-cli deploy --parameters ...)         │
│       5. Run integration tests (if skip_tests != true)              │
│       6. Tear down (if no stack_name in config)                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Config management flow

```
Git (source of truth)              S3 (per account)              Pipeline
enterprise/environments/           deploy/pipeline-config.yaml
├── dev.yaml          ──copy──▶    (in dev account S3)     ──▶   deploys with dev params
├── staging.yaml      ──copy──▶    (in staging account S3) ──▶   deploys with staging params
└── prod.yaml         ──copy──▶    (in prod account S3)    ──▶   deploys with prod params
```

---

## Part 1: One-Time Setup

These steps are performed **once per AWS account**. You only revisit them if changing pipeline infrastructure (VPC, secrets, etc.) or adding a new account.

### Prerequisites

- AWS account with Bedrock model access (see main README)
- AWS CLI configured with appropriate permissions
- The `scripts/sdlc/cfn/` templates from this repo

### 1.1 Deploy the S3 Source Bucket

One bucket per account:

```bash
aws cloudformation deploy \
  --template-file scripts/sdlc/cfn/s3-sourcecode.yml \
  --stack-name aidp-sdlc-sourcecode \
  --parameter-overrides BucketName=aidp-sdlc-sourcecode-{ACCOUNT_ID}-{REGION} \
  --region {REGION}
```

### 1.2 Deploy the CloudFormation Service Role

This role is assumed by CloudFormation to create/update/delete the IDP stack resources (Lambda functions, DynamoDB tables, S3 buckets, etc.). It is **not** the CodeBuild role — it's the role that CFN uses during stack operations.

```bash
aws cloudformation deploy \
  --template-file iam-roles/cloudformation-management/IDP-Cloudformation-Service-Role.yaml \
  --stack-name aidp-cfn-service-role \
  --capabilities CAPABILITY_NAMED_IAM \
  --region {REGION}
```

Note the output ARN — you'll need it for the config file:
```bash
aws cloudformation describe-stacks \
  --stack-name aidp-cfn-service-role \
  --query 'Stacks[0].Outputs[?OutputKey==`ServiceRoleArn`].OutputValue' \
  --output text --region {REGION}
```

> **Security note:** This role has broad permissions (it creates the entire IDP infrastructure) but can only be assumed by `cloudformation.amazonaws.com`. It does NOT have a permissions boundary — that would prevent it from creating the stack's IAM roles. Instead, the `PermissionsBoundaryArn` parameter is applied to all roles **created by** the stack (Lambda execution roles, etc.).
>
> **Customer review:** Share `iam-roles/cloudformation-management/IDP-Cloudformation-Service-Role.yaml` with the customer's security team before deployment. They may want to scope it further or add conditions.

### 1.3 Create the Environment Config

Copy a template from `enterprise/environments/` and fill in the values, including the service role ARN from step 1.2 and your customer's permissions boundary ARN:

```bash
# Copy the template
cp enterprise/environments/prod.yaml enterprise/environments/local-myenv.yaml

# Edit with your values (role_arn, PermissionsBoundaryArn, VPC, IdP, etc.)
vim enterprise/environments/local-myenv.yaml

# Upload to S3 as the standard config name
aws s3 cp enterprise/environments/local-myenv.yaml \
  s3://aidp-sdlc-sourcecode-{ACCOUNT_ID}-{REGION}/deploy/pipeline-config.yaml
```

Key fields to fill:
- `role_arn` — the service role ARN from step 1.2
- `parameters.PermissionsBoundaryArn` — customer's boundary (applied to all stack-created roles)

> **Note:** Files prefixed with `local-` are gitignored (they contain real account IDs/ARNs). The committed `dev.yaml` and `prod.yaml` are templates with placeholder values.

### 1.4 Deploy the Pipeline Stack

**Standard (public internet access):**
```bash
aws cloudformation deploy \
  --template-file scripts/sdlc/cfn/codepipeline-s3.yml \
  --stack-name aidp-sdlc-pipeline \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    BucketNamePrefix=aidp-sdlc-sourcecode \
    PipelineName=aidp-deploy-pipeline \
  --region {REGION}
```

**Air-gapped (private registry + VPC):**
```bash
aws cloudformation deploy \
  --template-file scripts/sdlc/cfn/codepipeline-s3.yml \
  --stack-name aidp-sdlc-pipeline \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    BucketNamePrefix=aidp-sdlc-sourcecode \
    PipelineName=aidp-deploy-pipeline \
    DockerConfigSecretArn=arn:aws:secretsmanager:...:secret:idp/registry/docker-xxx \
    PipConfigSecretArn=arn:aws:secretsmanager:...:secret:idp/registry/pip-xxx \
    UvConfigSecretArn=arn:aws:secretsmanager:...:secret:idp/registry/uv-xxx \
    NpmConfigSecretArn=arn:aws:secretsmanager:...:secret:idp/registry/npm-xxx \
    CACertBundleS3Uri=s3://bucket/certs/ca-bundle.tar.gz \
    VpcId=vpc-xxx \
    PrivateSubnetIds=subnet-a,subnet-b \
    CodeBuildSecurityGroupId=sg-xxx \
  --region {REGION}
```

---

## Part 2: Release Workflow (Repeating)

These steps are performed **every time you want to deploy a new version**.

### 2.1 Create the Release Zip

From the repo root:

```bash
zip -r /tmp/code.zip . \
  -x '.git/*' \
  -x '*.pyc' \
  -x '__pycache__/*' \
  -x '.venv/*' \
  -x 'node_modules/*' \
  -x '.mypy_cache/*' \
  -x '*.egg-info/*' \
  -x 'dist/*' \
  -x 'build/*' \
  -x '.tox/*'
```

> **What goes in the zip:** Source code, templates, Dockerfiles, UI source, sample documents — everything needed to build. The zip is ~2.5-3 GB.
>
> **What stays out:** Git history, virtualenvs, IDE files, compiled artifacts. The per-environment config is **not** in the zip — it lives in S3.

### 2.2 Upload to S3

```bash
# This TRIGGERS the pipeline
aws s3 cp /tmp/code.zip \
  s3://aidp-sdlc-sourcecode-{ACCOUNT_ID}-{REGION}/deploy/code.zip
```

That's it. The pipeline runs automatically.

### 2.3 Updating Config Without Changing Code

```bash
# 1. Edit and upload config
aws s3 cp enterprise/environments/local-myenv.yaml \
  s3://aidp-sdlc-sourcecode-{ACCOUNT_ID}-{REGION}/deploy/pipeline-config.yaml

# 2. Re-upload code.zip to trigger pipeline with new config
aws s3 cp /tmp/code.zip \
  s3://aidp-sdlc-sourcecode-{ACCOUNT_ID}-{REGION}/deploy/code.zip
```

> **Note:** Only `deploy/code.zip` triggers the pipeline. Config uploads alone do not start a run.

---

## S3 Bucket Layout

```
s3://aidp-sdlc-sourcecode-{ACCOUNT_ID}-{REGION}/
├── deploy/
│   ├── code.zip                  ← Triggers pipeline (release artifact)
│   └── pipeline-config.yaml      ← This environment's deployment config
└── codebuild-YYYYMMDD-HHMMSS/    ← Published templates (auto-generated per run)
    └── idp-main.yaml
```

---

## Configuration Reference

### Pipeline Config File (`deploy/pipeline-config.yaml`)

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `admin_email` | Yes | — | Email for Cognito admin user |
| `stack_name` | No | Auto-generated (`idp-MMDD-HHMMSS`) | Fixed stack name. When set, stack persists after pipeline runs |
| `skip_tests` | No | `false` | Skip integration tests (CD mode) |
| `headless` | No | `false` | Deploy without UI/AppSync/Cognito/WAF |
| `role_arn` | No | Auto-created | Pre-deployed CloudFormation service role ARN. If provided along with `PermissionsBoundaryArn` in parameters, the pipeline skips creating IAM resources |
| `parameters` | No | `{}` | CloudFormation parameters passed to `idp-cli deploy --parameters` |

### Supported CloudFormation Parameters

Any parameter from the main `template.yaml` can be specified under `parameters:`. Common ones:

**Build:**
- `LambdaArchitecture` (`arm64` or `x86_64`) — **must be `x86_64`** unless CodeBuild has ARM support or QEMU registered

**Networking:**
- `ALBVpcId`, `ALBSubnetIds`, `LambdaSubnetIds`
- `AppSyncVisibility` (`GLOBAL` or `PRIVATE`)
- `DeployInVPC`, `VpcId`, `PrivateSubnetIds`, `LambdaSecurityGroupId`
- `WAFAllowedIPv4Ranges`

**Identity:**
- `ExternalIdPType` (`NONE`, `SAML`, `OIDC`)
- `ExternalIdPName`, `ExternalIdPOIDCIssuer`, `ExternalIdPOIDCClientId`
- `PingIssuer1`, `PingJwksUri1`, `PingRequiredRoles`

**Security:**
- `PermissionsBoundaryArn`
- `ArtifactsBucketKmsKeyArn`

**Private Registry (build-time, passed as CFN params to inner Docker build):**
- `DockerConfigSecretArn`, `UvConfigSecretArn`, `PipConfigSecretArn`, `NpmConfigSecretArn`
- `CACertBundleS3Uri`
- `UvImage`, `LambdaBaseImage`

**Enterprise features:**
- `EnableHeadless`, `EnableCompletionHook`
- `CompletionHookMQHost`, `CompletionHookMQExchange`, `CompletionHookMQRoutingKey`

**Other:**
- `EnableMCP`, `DocumentKnowledgeBase`, `EnableMLflow`
- `MaxConcurrentWorkflows`, `DataRetentionInDays`

### Pipeline Stack Parameters (`codepipeline-s3.yml`)

These are set **once** when deploying the pipeline stack (Part 1, Step 1.3):

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `PipelineName` | No | `genaiic-sdlc-deploy-pipeline` | CodePipeline name |
| `BucketNamePrefix` | No | `genaiic-sdlc-sourcecode` | S3 bucket prefix (account+region appended) |
| `FileKey` | No | `deploy/code.zip` | S3 key that triggers the pipeline |
| `PipelineConfigKey` | No | `deploy/pipeline-config.yaml` | S3 key of the config file |
| `CodeBuildRoleArn` | No | Auto-created | Bring-your-own CodeBuild role |
| `KMSKeyArn` | No | Auto-created | Customer-managed KMS key |
| `VpcId` | No | — | VPC for CodeBuild (required for air-gapped) |
| `PrivateSubnetIds` | No | — | Subnets for CodeBuild |
| `CodeBuildSecurityGroupId` | No | — | Security group for CodeBuild |
| `DockerConfigSecretArn` | No | — | Docker registry credentials (outer build) |
| `UvConfigSecretArn` | No | — | UV/PyPI config (outer build) |
| `PipConfigSecretArn` | No | — | pip config (outer build) |
| `NpmConfigSecretArn` | No | — | npm config (outer build) |
| `CACertBundleS3Uri` | No | — | Corporate CA certificate bundle |

---

## Troubleshooting

### Pipeline triggered but build fails on lint
The publish step runs `ruff check` and `ruff format --check`. Fix locally:
```bash
make lint  # or: ruff format . && ruff check --fix .
```

### Docker build fails with "exec format error"
Set `LambdaArchitecture: x86_64` in your config's `parameters:`. The default `arm64` requires QEMU emulation which isn't available in standard CodeBuild x86_64 images.

### "The role defined for the function cannot be assumed by Lambda"
Transient IAM propagation issue. Retry the pipeline — re-upload `code.zip`.

### Stack deployment fails with parameter validation
Check that `admin_email` is set and matches the regex `^[\w.+-]+@([\w-]+\.)+[\w-]{2,6}$`.

### Config file not found
The pipeline requires `deploy/pipeline-config.yaml` in the S3 source bucket. Upload it:
```bash
aws s3 cp enterprise/environments/local-myenv.yaml \
  s3://{BUCKET}/deploy/pipeline-config.yaml
```

### BDA sync fails with 1 class error
Bedrock Data Automation may not support all document class schemas. This only affects CI tests — production deployments with `skip_tests: true` are unaffected.

### Enterprise layer build fails
Check that `LambdaArchitecture` is set in the config. The build script uses it to pick the correct pip platform (`manylinux2014_x86_64` vs `manylinux2014_aarch64`).

---

## Related Docs

- [Private Registry Setup](./private-registry-setup.md) — Secrets Manager configuration for air-gapped builds
- [Upstream Sync Guide](./upstream-sync-guide.md) — Conflict resolution for enterprise fork files
- [enterprise/environments/README.md](../environments/README.md) — Config file format and sync instructions
