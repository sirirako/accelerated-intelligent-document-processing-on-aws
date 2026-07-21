# Open Work

Active workstreams, blockers, and coordination notes. Update this when starting
or completing significant work.

## Active Workstreams

### 1. v0.6.1 Upstream Merge
- **Status:** ✅ DONE (2026-07-20, commit 367a68e0, pushed to origin)
- **What:** Merged upstream main (v0.6.1) into `enterprise/develop`
- **Conflicts resolved:** template.yaml, CLAUDE.md, feature-platform template, patterns/unified/template.yaml, codepipeline-s3.yml, codebuild_deployment.py
- **Fixes during merge:**
  - Added registry params (DockerConfigSecretArn, etc.) back to `patterns/unified/template.yaml`
  - Restored `docker buildx create --driver docker-container` in buildspec (arm64 cross-compile)
  - Added SECRET_ARGS for pip/uv/cacert Docker build mounts
- **Principle applied:** Take upstream for all application code; our changes are only install phase + SECRET_ARGS in buildspec, registry params in nested template, enterprise block in main template
- **Test deployments:** `idp-default` (x86_64) ✅, `idp-enterprise` (arm64, PRIVATE APIGW, headless, Ping) ✅

### 2. Customer Beta Release (v0.6.1)
- **Status:** Creating beta release for customer testing
- **What:** v0.6.1 enterprise fork ready for customer environment
- **Next:** Deploy to customer environment, redeploy pipeline stack with new template
- **Note:** Customer uses x86_64, air-gapped (no Docker Hub/ghcr.io access)

### 3. Ping Auth End-to-End Testing
- **Status:** Blocked on real Ping environment
- **What:** Test the authorizer with actual PingFederate tokens
- **Need:** Customer provides Ping dev environment access or a test Ping instance

### 4. Completion Hook End-to-End Testing
- **Status:** Blocked on RabbitMQ broker
- **What:** Test the hook publishes to a real RabbitMQ broker with Ping OAuth2
- **Need:** Customer provisions an Amazon MQ broker with OAuth2 backend configured

### 5. Cross-Account Networking
- **Status:** Design documented, not implemented
- **What:** PrivateLink both directions (API: us→them, MQ: them→us)
- **Need:** Customer's network team to create NLB + endpoint service for their MQ

## Completed Recently

- JFrog cache warming scripts created (`enterprise/registry/scripts/`) — PS1 + bash
- JFrog warming tested at customer site — most packages cached, some need Zap Caches
- WebUI buildspec fixed for air-gapped builds:
  - Removed `n 22.14.0` (uses CodeBuild built-in Node)
  - Added `install` phase with `.npmrc` from Secrets Manager + CA cert install
  - Added IAM permissions for secrets + CA cert S3 to UICodeBuildServiceRole
  - Added `HasCACertBundle` condition
- `src/ui/package.json` xlsx URL updated to customer's internal registry
- `--only-binary` arg split for PowerShell compatibility in warm-python.ps1
- v0.6 private VPC deployment tested (account 502161568083)
- Jobs API tested end-to-end with PowerShell script (Cognito M2M auth)
- Per-job configurationVersion tested and PR submitted upstream
- Environment config structure created (`enterprise/environments/`)
- Config pipeline created (`enterprise/config-pipeline/`)
- Layer binaries removed from git (build.sh before publish)
- Pipeline buildspec includes `enterprise/build.sh`
- All docs consolidated and customer-specific info removed
- v0.6.1 merged and tested (2026-07-20): idp-default + idp-enterprise stacks deployed
- Enterprise-owned deployment script created (`enterprise/sdlc/codebuild_deployment.py`)
- Pipeline buildspec now: chmod build.sh, use enterprise script if present, fallback to upstream
- Pipeline fixes: `--no-lint` on publish, `CreateTestVpc=false`, permissions boundary on roles
- Pipeline template orphan issue documented (hardcoded names: pipeline, CodeBuild project, IAM role, KMS alias, SNS topic — must be manually deleted before redeploying with same PipelineName)

## Coordination Notes

- **Multiple agents** work on this repo (enterprise integration, SDLC pipeline, registry)
- **`enterprise/develop`** is the integration branch — all feature branches merge here
- **Main branch** is synced with upstream main (v0.6.1) — no enterprise commits on main
- **Releases** tagged from `enterprise/develop` (e.g., `v0.6.1-enterprise-beta1`)
- **Customer deployment:** Download release zip → upload to S3 → redeploy pipeline stack once → pipeline handles the rest
