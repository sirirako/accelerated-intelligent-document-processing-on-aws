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
│  S3 Source Bucket (aidp-sdlc-sourcecode-{account}-{region})         │
│                                                                     │
│  deploy/code.zip                        ← Triggers pipeline         │
│  enterprise/deploy/prod-config.yaml     ← Per-environment config    │
│  enterprise/deploy/staging-config.yaml                              │
└────────────────┬────────────────────────────────────────────────────┘
                 │ EventBridge (Object Created on deploy/code.zip)
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  CodePipeline (one per environment)                                 │
│  ├── Source Stage: Pull code.zip                                    │
│  └── Build Stage: CodeBuild runs codebuild_deployment.py            │
│       1. Download config from S3 (PIPELINE_CONFIG_KEY)              │
│       2. Publish templates (SAM build + Docker images → S3)         │
│       3. Deploy CFN stack (idp-cli deploy --parameters ...)         │
│       4. Run integration tests (if skip_tests != true)              │
│       5. Tear down (if no stack_name in config)                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: One-Time Setup

These steps are performed **once per AWS account** (for the bucket) and **once per environment** (for the pipeline stack and config). You only revisit these if adding a new environment or changing pipeline infrastructure (VPC, secrets, etc.).

### Prerequisites

- AWS account with Bedrock model access (see main README)
- AWS CLI configured with appropriate permissions
- The `scripts/sdlc/cfn/` templates from this repo

### 1.1 Deploy the S3 Source Bucket

One bucket per account. All environments share it.

```bash
aws cloudformation deploy \
  --template-file scripts/sdlc/cfn/s3-sourcecode.yml \
  --stack-name aidp-sdlc-sourcecode \
  --parameter-overrides BucketName=aidp-sdlc-sourcecode-{ACCOUNT_ID}-{REGION} \
  --region {REGION}
```

### 1.2 Create the Environment Config File

Create a YAML file for each environment. This controls what gets deployed and how.

**CI testing config** (`enterprise/deploy/ci-config.yaml`):
```yaml
admin_email: admin@example.com
parameters:
  LambdaArchitecture: x86_64
```

**Production config** (`enterprise/deploy/prod-config.yaml`):
```yaml
admin_email: admin@customer.com
stack_name: aidp-prod
skip_tests: true
parameters:
  LambdaArchitecture: x86_64
  ALBVpcId: vpc-0abc123
  ALBSubnetIds: subnet-aaa,subnet-bbb
  LambdaSubnetIds: subnet-aaa,subnet-bbb
  AppSyncVisibility: PRIVATE
  ExternalIdPType: OIDC
  ExternalIdPName: PingFederate
  ExternalIdPOIDCIssuer: https://sso.customer.com
  ExternalIdPOIDCClientId: idp-app-client
  PermissionsBoundaryArn: arn:aws:iam::123456789012:policy/boundary
```

**Staging config** (`enterprise/deploy/staging-config.yaml`):
```yaml
admin_email: admin@customer.com
stack_name: aidp-staging
# skip_tests not set — runs smoke tests but keeps the stack
parameters:
  LambdaArchitecture: x86_64
```

Upload the config to S3:
```bash
aws s3 cp enterprise/deploy/prod-config.yaml \
  s3://aidp-sdlc-sourcecode-{ACCOUNT_ID}-{REGION}/enterprise/deploy/prod-config.yaml
```

### 1.3 Deploy the Pipeline Stack

One pipeline stack per environment. Each points to its own config file.

**Standard (public internet access):**
```bash
aws cloudformation deploy \
  --template-file scripts/sdlc/cfn/codepipeline-s3.yml \
  --stack-name aidp-{ENV}-pipeline \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    BucketNamePrefix=aidp-sdlc-sourcecode \
    PipelineName=aidp-{ENV}-deploy-pipeline \
    PipelineConfigKey=enterprise/deploy/{ENV}-config.yaml \
  --region {REGION}
```

**Air-gapped (private registry + VPC):**
```bash
aws cloudformation deploy \
  --template-file scripts/sdlc/cfn/codepipeline-s3.yml \
  --stack-name aidp-{ENV}-pipeline \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    BucketNamePrefix=aidp-sdlc-sourcecode \
    PipelineName=aidp-{ENV}-deploy-pipeline \
    PipelineConfigKey=enterprise/deploy/{ENV}-config.yaml \
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

### 1.4 Multi-Environment Setup

```bash
# CI pipeline (ephemeral — tests every push, destroys after)
aws cloudformation deploy ... \
  --stack-name aidp-ci-pipeline \
  --parameter-overrides PipelineConfigKey=enterprise/deploy/ci-config.yaml ...

# Staging pipeline (persistent — deploys, runs smoke tests, keeps stack)
aws cloudformation deploy ... \
  --stack-name aidp-staging-pipeline \
  --parameter-overrides PipelineConfigKey=enterprise/deploy/staging-config.yaml ...

# Production pipeline (persistent — deploys only, no tests)
aws cloudformation deploy ... \
  --stack-name aidp-prod-pipeline \
  --parameter-overrides PipelineConfigKey=enterprise/deploy/prod-config.yaml ...

# Business unit pipeline (separate IDP stack per BU)
aws cloudformation deploy ... \
  --stack-name aidp-finance-pipeline \
  --parameter-overrides PipelineConfigKey=enterprise/deploy/bu-finance-config.yaml ...
```

All pipelines trigger from the same `deploy/code.zip` upload.

---

## Part 2: Release Workflow (Repeating)

These steps are performed **every time you want to deploy a new version**. This is the day-to-day operation.

### 2.1 Create the Release Zip

From the repo root, package the code:

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

> **What goes in the zip:** Source code, templates, Dockerfiles, UI source, sample documents, tests — everything needed to build. The zip is ~2.5-3 GB.
>
> **What stays out:** Git history, virtualenvs, IDE files, compiled artifacts. The per-environment config is **not** in the zip — it lives separately in S3.

### 2.2 Upload to S3

```bash
# Upload code zip — this TRIGGERS all pipelines watching this bucket
aws s3 cp /tmp/code.zip \
  s3://aidp-sdlc-sourcecode-{ACCOUNT_ID}-{REGION}/deploy/code.zip
```

That's it. The pipeline runs automatically:
1. Pulls the zip
2. Downloads its environment config from S3
3. Builds templates and Docker images
4. Deploys (creates or updates) the CFN stack
5. Runs tests (if configured)
6. Reports success/failure

### 2.3 Updating Config Without Changing Code

If you need to change deployment parameters (add a VPC, change IdP settings, etc.) without releasing new code:

```bash
# 1. Edit and upload the config
aws s3 cp enterprise/deploy/prod-config.yaml \
  s3://aidp-sdlc-sourcecode-{ACCOUNT_ID}-{REGION}/enterprise/deploy/prod-config.yaml

# 2. Re-upload the same code.zip to trigger pipeline with new config
aws s3 cp /tmp/code.zip \
  s3://aidp-sdlc-sourcecode-{ACCOUNT_ID}-{REGION}/deploy/code.zip
```

> **Note:** Only `deploy/code.zip` triggers the pipeline. Config uploads alone do not start a run.

---

## S3 Bucket Layout

```
s3://aidp-sdlc-sourcecode-{ACCOUNT_ID}-{REGION}/
├── deploy/
│   └── code.zip                              ← Triggers pipelines (release artifact)
└── enterprise/
    └── deploy/
        ├── ci-config.yaml                    ← CI/SDLC testing
        ├── staging-config.yaml               ← Staging environment
        ├── prod-config.yaml                  ← Production environment
        └── bu-finance-config.yaml            ← Business unit
```

### Config resolution order

The deployment script looks for config in this order:
1. **S3** — `s3://{SOURCE_BUCKET}/{PIPELINE_CONFIG_KEY}` (set per-pipeline stack)
2. **Local fallback** — `enterprise/deploy/pipeline-config.yaml` inside the code zip
3. **Defaults** — auto-generated stack name, no extra parameters

---

## Configuration Reference

### Pipeline Config File (`enterprise/deploy/{env}-config.yaml`)

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `admin_email` | Yes | — | Email for Cognito admin user |
| `stack_name` | No | Auto-generated (`idp-MMDD-HHMMSS`) | Fixed stack name. When set, stack persists after pipeline runs |
| `skip_tests` | No | `false` | Skip integration tests (CD mode) |
| `headless` | No | `false` | Deploy without UI/AppSync/Cognito/WAF |
| `parameters` | No | `{}` | CloudFormation parameters passed to `idp-cli deploy --parameters` |

### Supported CloudFormation Parameters

Any parameter from the main `template.yaml` can be specified under `parameters:`. Common ones:

**Networking:**
- `ALBVpcId`, `ALBSubnetIds`, `LambdaSubnetIds`
- `AppSyncVisibility` (`GLOBAL` or `PRIVATE`)
- `S3VpcEndpointIdOverride`, `S3VpcEndpointDnsNameOverride`
- `WAFAllowedIPv4Ranges`

**Identity:**
- `ExternalIdPType` (`NONE`, `SAML`, `OIDC`)
- `ExternalIdPName`, `ExternalIdPOIDCIssuer`, `ExternalIdPOIDCClientId`
- `ExternalIdPOIDCClientSecretArn`
- `ExternalIdPGroupAttributeName`, `ExternalIdPAdminGroupName`

**Security:**
- `PermissionsBoundaryArn`
- `ArtifactsBucketKmsKeyArn`

**Build:**
- `LambdaArchitecture` (`arm64` or `x86_64`)

**Private Registry (build-time):**
- `DockerConfigSecretArn`, `UvConfigSecretArn`, `PipConfigSecretArn`, `NpmConfigSecretArn`
- `CACertBundleS3Uri`
- `UvImage`, `LambdaBaseImage`

**Features:**
- `EnableMCP`, `DocumentKnowledgeBase`, `EnableMLflow`
- `BedrockGuardrailId`, `BedrockGuardrailVersion`
- `MaxConcurrentWorkflows`, `DataRetentionInDays`

### Pipeline Stack Parameters (`codepipeline-s3.yml`)

These are set **once** when deploying the pipeline stack (Part 1, Step 1.3):

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `PipelineName` | No | `genaiic-sdlc-deploy-pipeline` | CodePipeline name |
| `BucketNamePrefix` | No | `genaiic-sdlc-sourcecode` | S3 bucket prefix (account+region appended) |
| `FileKey` | No | `deploy/code.zip` | S3 key that triggers the pipeline |
| `PipelineConfigKey` | No | `deploy/pipeline-config.yaml` | S3 key of the config file for this environment |
| `CodeBuildRoleArn` | No | Auto-created | Bring-your-own CodeBuild role |
| `KMSKeyArn` | No | Auto-created | Customer-managed KMS key |
| `VpcId` | No | — | VPC for CodeBuild (required for air-gapped) |
| `PrivateSubnetIds` | No | — | Subnets for CodeBuild |
| `CodeBuildSecurityGroupId` | No | — | Security group for CodeBuild |
| `DockerConfigSecretArn` | No | — | Docker registry credentials |
| `UvConfigSecretArn` | No | — | UV/PyPI config |
| `PipConfigSecretArn` | No | — | pip config |
| `NpmConfigSecretArn` | No | — | npm config |
| `CACertBundleS3Uri` | No | — | Corporate CA certificate bundle |

---

## Troubleshooting

### Pipeline triggered but build fails on lint
The publish step runs `ruff check` and `ruff format --check`. Fix locally:
```bash
make lint  # or: ruff format . && ruff check --fix .
```

### Docker build fails with "exec format error"
Set `LambdaArchitecture: x86_64` in your config. The default `arm64` requires QEMU emulation which isn't available in standard CodeBuild x86_64 images.

### "The role defined for the function cannot be assumed by Lambda"
Transient IAM propagation issue. Retry the pipeline — re-upload `code.zip`.

### Stack deployment fails with parameter validation
Check that `admin_email` is set and matches the regex `^[\w.+-]+@([\w-]+\.)+[\w-]{2,6}$`.

### Config file not found
Ensure the config is uploaded to S3 at the path matching `PipelineConfigKey`. The script falls back to `enterprise/deploy/pipeline-config.yaml` inside the code zip if S3 download fails.

### BDA sync fails with 1 class error
Bedrock Data Automation may not support all document class schemas. This only affects CI test Step 4 — production deployments with `skip_tests: true` are unaffected.

---

## Related Docs

- [Private Registry Setup](./private-registry-setup.md) — Secrets Manager configuration for air-gapped builds
- [Upstream Sync Guide](./upstream-sync-skill.md) — Conflict resolution for enterprise fork files
