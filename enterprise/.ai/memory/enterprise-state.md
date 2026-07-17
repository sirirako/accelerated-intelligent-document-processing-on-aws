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

### SDLC Pipeline
- **Status:** Implemented, tested
- **Location:** `scripts/sdlc/cfn/codepipeline-s3.yml`, `scripts/sdlc/codebuild_deployment.py`
- **Tested:** Pipeline triggers on S3 upload, publishes, deploys
- **Known issues:**
  - KMS key policy must allow CodeBuild roles BEFORE deploy (`ArtifactsBucketKmsKeyArn` required)
  - `enterprise/build.sh` added as pipeline install step

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
