# Open Work

Active workstreams, blockers, and coordination notes. Update this when starting
or completing significant work.

## Active Workstreams

### 1. v0.6 Upstream Merge
- **Status:** Tested, not merged
- **What:** Merge upstream v0.6 (AppSync → API Gateway REST) into `enterprise/develop`
- **Blocker:** Waiting for upstream to release v0.6 (currently dev9)
- **Impact on enterprise:**
  - `AppSyncVisibility=PRIVATE` → replaced by `ApiGatewayVisibility=PRIVATE` (native in v0.6)
  - Our Ping authorizer on Jobs API — still needed (v0.6 still uses Cognito M2M on headless)
  - Completion hook — unchanged (PostProcessingLambdaHookFunctionArn still exists)
  - Private registry — unchanged
- **Test results:** v0.6 deploys successfully with `ApiGatewayVisibility=PRIVATE` + `EnableHeadless=true`

### 2. Customer Delivery
- **Status:** Code pushed to customer repo
- **What:** Enterprise features delivered to customer's internal repo
- **Next:** Customer to fill in their Ping/MQ/VPC values and deploy

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

## Coordination Notes

- **Multiple agents** work on this repo (enterprise integration, SDLC pipeline, registry)
- **`enterprise/develop`** is the integration branch — all feature branches merge here
- **Don't merge to `main`** until upstream releases v0.6 and we validate the full merge
- **Customer repo** is separate — copy `enterprise/` folder there, no git history
