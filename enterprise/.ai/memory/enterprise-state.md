# Enterprise Feature State

Current status of each enterprise feature, known issues, and what's tested.

## Features

### Ping JWT Authorizer
- **Status:** Implemented, deployed, not tested with real Ping
- **Location:** `enterprise/ping_authorizer/app.py`
- **Template:** `EnterprisePingAuthorizerFunction` (conditioned on `DeployApiGateway`)
- **Config:** `PingIssuer1`, `PingJwksUri1`, `PingIssuer2`, `PingJwksUri2`, `PingRequiredRoles`
- **Known issues:**
  - Deployed with mock Ping URLs (`https://mock-ping.example.com`) — not validated against real Ping
  - `CUSTOM_TOKEN_HEADER` env var for custom header (was hardcoded to customer-specific header)
- **Tested:** Deploy succeeds, Lambda created. No real JWT validation tested.

### Completion Hook (Amazon MQ)
- **Status:** Implemented, deployed, not tested end-to-end
- **Location:** `enterprise/completion_hook/`
- **Template:** `EnterpriseCompletionHookFunction` (conditioned on `DeployCompletionHook`)
- **Config:** `CompletionHookMQ*` params + `EnableCompletionHook=true`
- **Known issues:**
  - No RabbitMQ broker available for testing
  - Wiring: `ShouldEnablePostProcessingLambdaHook` expanded with `!Or` to include our hook
  - Decompressor `CUSTOM_POST_PROCESSOR_ARN` uses `!If [DeployCompletionHook, ...]`
- **Tested:** Deploy succeeds with `EnableCompletionHook=false`. Not tested with real MQ.

### Per-job configurationVersion
- **Status:** Implemented, tested, PR submitted upstream
- **Location:** `src/lambda/api_handler/`, `src/lambda/batch_pre_processor/`
- **Branch:** `feature/per-job-config` (upstream PR), merged into `enterprise/develop`
- **Tested:**
  - Unit tests: 9/9 passing (api_handler + batch_pre_processor)
  - E2E: Lambda invoked directly, `x-amz-meta-config-version` confirmed in presigned POST
  - Deployed to `idp-headless-test` stack and verified

### Private Registry
- **Status:** Implemented, tested in pipeline
- **Location:** Template params + `Dockerfile.optimized` + `buildspec.yml`
- **Branch:** `feature/internal-artifact-registry`, merged into `enterprise/develop`
- **Tested:** Deployed with JFrog secrets, builds pull from private registry

### SDLC/CD Pipeline
- **Status:** Implemented, deployed, working end-to-end in air-gapped environment
- **Location:** `scripts/sdlc/cfn/codepipeline-s3.yml`, `scripts/sdlc/codebuild_deployment.py`
- **Tested:** Full CD pipeline — publish + deploy with private registry, VPC, AppSync PRIVATE
- **Air-gap fixes applied:**
  - `Dockerfile.optimized`: Install uv via pip (not ghcr.io image pull), `BASE_IMAGE` ARG for full image:tag
  - `patterns/unified/buildspec.yml`: Removed buildx docker-container driver, removed `INSTALL_GIT=true`, removed `UV_IMAGE` arg
  - `nested/multi-doc-discovery/template.yaml`: Removed gcc install, use `docker --config` for JFrog auth, full image:tag support
  - `template.yaml` (UI buildspec): `npm install --engine-strict=false` (Node 18 compat)
  - `codepipeline-s3.yml`: Amazon Linux 2 image, CA cert format detection, `NodeDistUrl` param, boundary on all roles
  - `iam-roles/.../IDP-Cloudformation-Service-Role.yaml`: Added `PermissionsBoundaryArn` param
  - `feature-platform/main-stack-extensions/template.yaml`: Added `PermissionsBoundaryArn` pass-through to both roles
  - `src/ui/package.json`: xlsx pointed to internal registry, vite updated to ^7.3.6
- **Pipeline config fields:** `stack_name`, `skip_tests`, `headless`, `role_arn`, `parameters:{}`
- **Config loaded from:** S3 at `{PIPELINE_CONFIG_KEY}` (default `deploy/pipeline-config.yaml`)
- **Known issues:**
  - `n 22.14.0` can't reach nodejs.org in air-gap — falls back to built-in Node 18 (works with `--engine-strict=false`)
  - Bedrock model `anthropic.claude-sonnet-4-5-20250929-v1:0` not available in all accounts (non-critical, AI summary only)
  - mlflow-logger built without git (no git metadata tracking)
  - `LambdaVpcSecurityGroup` auto-created when `AppSyncVisibility=PRIVATE` — can block stack deletion (ENI detach delay)
  - `npm install` instead of `npm ci` — less reproducible but works on Node 18
- **Base image:** Customer mirrors `public.ecr.aws/lambda/python` in their internal Docker registry. `LambdaBaseImage` parameter takes the full image:tag (e.g., `internal-registry/lambda/python:3.12-x86_64`). Both `Dockerfile.optimized` and `multi-doc-discovery` support this via `BASE_IMAGE` ARG.
- **Required VPC endpoints:** `com.amazonaws.us-east-1.codebuild` (for Custom Resource Lambda calling CodeBuild API)
- **Docs:** `enterprise/docs/sdlc-pipeline-setup.md`, `enterprise/environments/`

### Config Pipeline
- **Status:** Implemented, not tested
- **Location:** `enterprise/config-pipeline/`
- **Tested:** Not deployed yet

## Upstream Version Compatibility

- **Current fork:** v0.5.16
- **Tested upgrade to v0.6:** Works for non-VPC and VPC stacks (with caveats below)
- **v0.6 known issues:**
  - `custom:idp_groups` schema constraint: stacks created before the `MaxLength: "2048"`
    constraint was added cannot upgrade in-place (Cognito limitation)
  - `ApiUserPoolDomain` fails with uppercase stack names (Cognito domain must be lowercase)
  - `ArtifactsBucketKmsKeyArn` required when S3 bucket uses KMS encryption
  - Fresh VPC deploys need working NAT for CodeBuild Docker pulls
  - v0.6 replaces AppSync with API Gateway REST API — our `AppSyncVisibility=PRIVATE`
    workaround is no longer needed (use `ApiGatewayVisibility=PRIVATE` instead)

## What's NOT done

- Testing Ping authorizer with real PingFederate
- Testing completion hook with real RabbitMQ broker
- Cross-account PrivateLink setup (API + MQ)
- Merging v0.6 upstream into enterprise/develop
- AI agent automated fork maintenance (planned)
- Node 22 install in air-gap (workaround: Node 18 + `--engine-strict=false`)
- Submit FeaturePlatformStack boundary fix upstream (reported)
- Config pipeline (`enterprise/config-pipeline/`) not yet deployed at customer
- UI build at customer blocked by JFrog quarantine (vite 7.3.6 now released, needs retest with headless=false)
