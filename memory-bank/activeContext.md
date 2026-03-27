# Active Context

## Current Work Focus

### Private AppSync API — Feature Complete (March 25–26, 2026)

**Branch**: `feature/private-appsync-api`  
**Latest commit**: `42484ee6`  
**Status**: ✅ All 8 steps implemented and end-to-end tested. Ready for PR/merge.

**Goal**: Make AppSync GraphQL API only accessible from within the VPC when `AppSyncVisibility=PRIVATE`.

**Reference Plan**: `docs/private-appsync-implementation-plan.md`

---

## Implementation Status — All Steps Complete ✅

| Step | What was done | Commit |
|------|---------------|--------|
| 1 | `AppSyncVisibility` + `LambdaSubnetIds` params + `UsePrivateAppSync` condition in `template.yaml` | ca6d0f2f |
| 2 | `LambdaVpcSecurityGroup` (HTTPS egress only) + `GraphQLApi Visibility` conditional | de2d12f2 |
| 3+4 | VPC endpoints refactored — removed from main stack, moved to `scripts/vpc-endpoints.yaml` (networking team owns). Main stack exports `LambdaVpcSecurityGroupId` output. | 141cd3f8 |
| 5 | VpcConfig added to 7 Lambdas in `template.yaml`: `QueueSender`, `QueueProcessor`, `WorkflowTracker`, `SaveReportingDataFunctionV2`, `AgentChatProcessorFunction`, `AgentProcessorFunction`, `DiscoveryProcessorFunction` | 7c962a2a |
| 6 | VpcConfig + params added to `nested/appsync/template.yaml` (4 resolver Lambdas: AbortWorkflow, CopyToBaseline, ProcessChanges, ReprocessDocument) | 6997cddc |
| 7 | VpcConfig added to 10 processing Lambdas in `patterns/unified/template.yaml` (BDAProcessResults, OCR, Classification, Extraction, Assessment, ProcessResults, Summarization, Evaluation, RuleValidation, RuleValidationOrchestration) | 68c853e7 |
| 8 | `docs/deployment-private-network.md` — full private network deployment runbook (ALB + private AppSync) | 7220d9b9 |

### Documentation & Tooling Improvements (March 25–26, 2026)

| Commit | What was done |
|--------|---------------|
| 676232ad | `check-vpc-endpoints.sh` + per-endpoint CFN flags; rewrote deployment runbook |
| 4aea758d | `deploy-vpc-endpoints.py` — cross-platform endpoint deployer |
| 94095aa0 | Added `ssmmessages` + `ec2messages` to vpc-endpoints.yaml and deploy script (14 total) |
| 42484ee6 | Enterprise artifact bucket hardening section in deployment-private-network.md; `sudo -E` fix; endpoint count clarification; app-vs-testing comments in check script and CFN template |

---

## Current State

### What's Working (end-to-end tested)
- All IDP stacks `CREATE/UPDATE_COMPLETE` with `AppSyncVisibility=PRIVATE`
- All 14 VPC interface endpoints `available` + S3 gateway endpoint
- AppSync API confirmed `PRIVATE` visibility
- SSM bastion + port forwarding tested: IDP UI accessible at `https://localhost:8443/` via SSM tunnel
- `publish.py` enterprise flags working: SSE-KMS encryption, SSL-only + account-restricted bucket policy, cost-allocation tags

### Key Learnings: Testing Private AppSync from a Browser (March 26, 2026)

When testing the `AppSyncVisibility=PRIVATE` deployment from a browser (WorkSpaces or any browser inside the VPC), these gotchas apply:

1. **ACM self-signed cert must include the ALB DNS hostname as SAN** — not just a custom internal name like `idp-alb.internal`. Firefox and other browsers block background XHR/fetch/WebSocket requests (JavaScript API calls) to domains with mismatched certs, even if the user clicked through the page-level cert warning. Fix: reimport the cert with the ELB DNS hostname as an additional SAN.

2. **Cognito IDP requires internet access** — `cognito-idp.<region>.amazonaws.com` is called client-side (browser JavaScript) for token exchange. There is no VPC Interface Endpoint for Cognito IDP. The browser needs internet access via NAT Gateway → IGW. Lambda functions do NOT need this (they use Cognito SDK calls which use different endpoints or the VPC-routed path).

3. **NAT Gateway must be in a dedicated PUBLIC subnet** — the subnet containing the NAT GW must have a `0.0.0.0/0 → IGW` route. The NAT GW itself cannot provide egress for resources in the same subnet it lives in. Private subnets with resources (WorkSpaces, Lambda) must route `0.0.0.0/0` to the NAT GW's subnet.

4. **Amazon WorkSpaces internet access is a directory-level setting** — separate from VPC routing. Even if the VPC has a NAT GW, the WorkSpace browser won't have internet unless `EnableInternetAccess=true` is set on the WorkSpaces directory. Changing this setting requires rebuilding existing WorkSpaces (~25 min).

5. **AppSync realtime (WebSocket subscriptions) works through the `appsync-api` VPC endpoint** — there is no separate `appsync-realtime-api` VPC endpoint needed. The `appsync-api` Interface endpoint handles both HTTPS queries/mutations AND WSS subscriptions. Private DNS on the endpoint resolves both `*.appsync-api.*` and `*.appsync-realtime-api.*` hostnames to the endpoint ENIs.

6. **`scripts/alb-test-vpc.yaml` creates 3 subnets** — `PrivateSubnet1` (us-east-1a), `PrivateSubnet2` (us-east-1b), and `LambdaSubnet` (us-east-1a, dedicated for Lambda VpcConfig). The `LambdaSubnet` should be used for `LambdaSubnetIds` parameter, keeping it separate from the ALB subnets.

### Next Steps
- Create PR: `feature/private-appsync-api` → `main`

---

## Key Technical Notes

### VpcConfig Pattern Difference: main vs patterns/unified

In `template.yaml` (main), `LambdaSubnetIds` is a `CommaDelimitedList`:
```yaml
- SubnetIds: !Ref LambdaSubnetIds   # already a list
```

In `patterns/unified/template.yaml`, it's passed as a String (comma-joined):
```yaml
- SubnetIds: !Split [",", !Ref LambdaSubnetIds]   # must split
```

### VPC Endpoints Architecture

App team deploys IDP stack with `AppSyncVisibility=PRIVATE` → exports `LambdaVpcSecurityGroupId`.

Networking team deploys `scripts/vpc-endpoints.yaml` with:
- **12 Interface endpoints required by IDP app**: appsync-api, appsync, sqs, states, kms, logs, bedrock-runtime, ssm (Lambda→SSM Parameter Store), secretsmanager, lambda, events, athena
- **2 Interface endpoints for SSM testing bastion only**: ssmmessages, ec2messages (NOT needed in production with VPN/Direct Connect)
- **2 Gateway endpoints (free, optional)**: s3, dynamodb
- `VpcEndpointSecurityGroup` allows inbound 443 from Lambda SG

### SSM Endpoint Distinction
- `ssm` — **required by IDP app** (Lambda functions call SSM Parameter Store) AND needed for SSM bastion
- `ssmmessages` — **testing bastion only** (SSM Session Manager port-forwarding channel)
- `ec2messages` — **testing bastion only** (SSM agent ↔ SSM service communication)

### Enterprise Artifact Bucket Hardening
`publish.py` supports three enterprise flags:
- `--kms-key-arn <ARN>` — SSE-KMS encryption on artifact bucket
- `--enterprise-bucket-policy` — adds `DenyInsecureTransport` + `DenyExternalAccess` statements
- `--tags Key=Value,...` — cost-allocation and governance tags

### Testing: sudo -E for port 443 AppSync tunnel
Port 443 requires `sudo` on macOS. Use `sudo -E aws ssm start-session ...` — the `-E` flag preserves env var credentials (`AWS_ACCESS_KEY_ID` etc.) that would otherwise be stripped by sudo.

---

## Previous Work (RBAC — March 9, 2026)

### Role-Based Access Control (RBAC) Implementation

**Solution implemented (Phase 1 — Security Hardening + New Roles)**:

1. GraphQL Schema Auth Directives (Server-Side) — `@aws_auth` on all mutations/sensitive queries
2. Server-Side Document Filtering for Reviewer in `list_documents_gsi_resolver/index.py`
3. New Cognito Groups: `AuthorGroup` (precedence 1) and `ViewerGroup` (precedence 3)
4. User Management Lambda: 4 personas (Admin, Author, Reviewer, Viewer) + `allowedConfigVersions` field
5. UI Updates: `useUserRole` hook, 4 nav configs, role badges

### Key Files Modified (March 9)
- `template.yaml` — New Cognito groups (Author, Viewer) + Lambda env vars
- `nested/appsync/src/api/schema.graphql` — Auth directives on all operations
- `nested/appsync/src/lambda/list_documents_gsi_resolver/index.py` — Server-side reviewer filtering
- `src/lambda/user_management/index.py` — 4-role support + allowedConfigVersions
- `src/ui/src/hooks/use-user-role.ts` — Extended role hook with convenience flags
- `src/ui/src/components/genaiidp-layout/navigation.tsx` — 4 nav configurations
- `docs/rbac.md` — RBAC documentation

### Phase 2 (Future — Config-Version Scoping)
- `allowedConfigVersions` attribute already added to User DDB records and GraphQL schema
- Resolver-level filtering by config-version not yet implemented

---

## Architecture Summary

### Unified Architecture (Phase 3 Complete — Feb 26, 2026)
- Single template stack: `template.yaml` → `patterns/unified/template.yaml`
- 12 Lambda functions (BDA branch + Pipeline branch + shared tail)
- Routing via `use_bda` flag in configuration
- Full config per version stored in DynamoDB

### Private AppSync Architecture (March 25, 2026 — COMPLETE)
- `AppSyncVisibility=PRIVATE` → all traffic stays on AWS backbone via VPC endpoints
- Lambda SG (HTTPS egress only) → VPC Interface Endpoints → AWS services
- 3 templates updated: `template.yaml`, `nested/appsync/template.yaml`, `patterns/unified/template.yaml`
- VPC endpoint management separated to `scripts/vpc-endpoints.yaml` (networking team)
- 21 Lambda functions total placed in VPC when `AppSyncVisibility=PRIVATE`

### RBAC Architecture (March 9, 2026)
- 3-layer enforcement: AppSync auth directives → Lambda resolver filtering → UI adaptation
- 4 Cognito groups: Admin, Author, Reviewer, Viewer
- Server-side document filtering for Reviewer role in listDocuments resolver
- Config-version scoping data model ready (Phase 2)
