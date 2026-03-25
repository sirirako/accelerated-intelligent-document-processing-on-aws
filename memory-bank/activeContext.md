# Active Context

## Current Work Focus

### Private AppSync API Implementation (March 25, 2026)

**Branch**: `feature/private-appsync-api`

**Goal**: Make AppSync GraphQL API only accessible from within the VPC when `AppSyncVisibility=PRIVATE`.

**Reference Plan**: `docs/private-appsync-implementation-plan.md`

---

## Implementation Status

### ✅ Completed Steps (Steps 1–6, commits ca6d0f2f → 6997cddc)

| Step | What was done | Commit |
|------|---------------|--------|
| 1 | `AppSyncVisibility` + `LambdaSubnetIds` params + `UsePrivateAppSync` condition in `template.yaml` | ca6d0f2f |
| 2 | `LambdaVpcSecurityGroup` (HTTPS egress only) + `GraphQLApi Visibility` conditional | de2d12f2 |
| 3+4 | VPC endpoints **refactored** — removed from main stack, moved to `scripts/vpc-endpoints.yaml` (networking team owns). Main stack exports `LambdaVpcSecurityGroupId` output. | 141cd3f8 |
| 5 | VpcConfig added to 7 Lambdas in `template.yaml`: `QueueSender`, `QueueProcessor`, `WorkflowTracker`, `SaveReportingDataFunctionV2`, `AgentChatProcessorFunction`, `AgentProcessorFunction`, `DiscoveryProcessorFunction` | 7c962a2a |
| 6 | VpcConfig + params added to `nested/appsync/template.yaml` (4 resolver Lambdas: AbortWorkflow, CopyToBaseline, ProcessChanges, ReprocessDocument) | 6997cddc |

### 🔄 In Progress — Uncommitted changes

- `patterns/unified/template.yaml` — Parameters and condition added (NOT yet committed):
  - `UsePrivateAppSync`, `LambdaSubnetIds`, `LambdaSecurityGroupId` params
  - `IsPrivateAppSync` condition
  - **VpcConfig NOT yet added** to any processing functions

### ⏳ Remaining Steps

---

## Approved Implementation Plan (Ready for ACT mode)

### Task 1 — Merge `feature/enterprise-artifact-bucket-hardening` → `feature/private-appsync-api`

```bash
git merge feature/enterprise-artifact-bucket-hardening
```

Brings in:
- `docs/deployment-private-network.md` (ALB runbook — base for Step 8)
- `scripts/alb-test-vpc.yaml` (test VPC CFN template)
- `publish.py`/`publish.sh` enterprise bucket hardening flags (`--kms-key-arn`, `--enterprise-bucket-policy`, `--tags`)

Potential conflict: `pr-description.md` (keep private-appsync version).

**Commit message**: `chore: merge enterprise-artifact-bucket-hardening into private-appsync-api`

---

### Task 2 — Step 7: VpcConfig for all 10 processing Lambdas in `patterns/unified/template.yaml`

**10 Functions to update** (all have `APPSYNC_API_URL`):

| # | Function | Approx Line |
|---|----------|-------------|
| 1 | `BDAProcessResultsFunction` | ~2159 |
| 2 | `OCRFunction` | ~2402 |
| 3 | `ClassificationFunction` | ~2519 |
| 4 | `ExtractionFunction` | ~2646 |
| 5 | `AssessmentFunction` | ~2775 |
| 6 | `ProcessResultsFunction` | ~2893 |
| 7 | `SummarizationFunction` | ~2981 |
| 8 | `EvaluationFunction` | ~3101 |
| 9 | `RuleValidationFunction` | ~3266 |
| 10 | `RuleValidationOrchestrationFunction` | ~3377 |

> `InvokeBDAFunction` does NOT use APPSYNC_API_URL — skip it.

**VpcConfig pattern** (uses `IsPrivateAppSync` condition + `!Split` because LambdaSubnetIds is passed as comma-joined String):
```yaml
      VpcConfig: !If
        - IsPrivateAppSync
        - SubnetIds: !Split [",", !Ref LambdaSubnetIds]
          SecurityGroupIds:
            - !Ref LambdaSecurityGroupId
        - !Ref AWS::NoValue
```

**Also update cfn_nag/checkov suppressions** on each function:
```yaml
    # checkov:skip=CKV_AWS_117: "Function placed in VPC when AppSyncVisibility=PRIVATE via IsPrivateAppSync condition"
```

Also need to pass params from `template.yaml` → PATTERNSTACK (already done — verified at line ~1404):
```yaml
UsePrivateAppSync: !If [UsePrivateAppSync, "true", "false"]
LambdaSubnetIds: !If [UsePrivateAppSync, !Join [",", !Ref LambdaSubnetIds], ""]
LambdaSecurityGroupId: !If [UsePrivateAppSync, !Ref LambdaVpcSecurityGroup, ""]
```

**Commit**: `feat: step 7 — add VpcConfig to all processing Lambdas in patterns/unified (req #2)`

---

### Task 3 — Step 8: Update `docs/deployment-private-network.md`

Add new section **"Private AppSync API (AppSyncVisibility=PRIVATE)"** covering:

1. When to use (private network — AppSync must be inaccessible from internet)
2. Two-step deploy process (App team first, then networking team)
3. Full deploy command with private AppSync params
4. How to get `LambdaVpcSecurityGroupId` output for networking team
5. Networking team step: deploy `scripts/vpc-endpoints.yaml`
6. Test VPC reference values:
   - VPC: `vpc-0f42ddb124c806ba1`
   - Subnets (ALB): `subnet-0ae7c007a67c0a483`, `subnet-00b39e8345d9f0ff2`
   - Cert: `arn:aws:acm:us-east-1:<account-id>:certificate/<cert-id>`

**Commit**: `docs: step 8 — add private AppSync section to deployment-private-network.md`

---

### Task 4 — Update `docs/private-appsync-implementation-plan.md`

Mark Steps 7 and 8 as ✅ complete, update "Remaining Steps" section.

**Commit**: `docs: mark all steps complete in private-appsync-implementation-plan.md`

---

### Task 5 — Testing

Deploy to test VPC using credentials provided by user:
- VPC: `vpc-0f42ddb124c806ba1`
- Subnets: `subnet-0ae7c007a67c0a483`, `subnet-00b39e8345d9f0ff2`
- Cert: `arn:aws:acm:us-east-1:<account-id>:certificate/<cert-id>`

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
- 12 Interface endpoints: appsync-api, appsync, sqs, states, kms, logs, bedrock-runtime, ssm, secretsmanager, lambda, events, athena
- 2 Gateway endpoints (free): s3, dynamodb
- `VpcEndpointSecurityGroup` allows inbound 443 from Lambda SG

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

### Private AppSync Architecture (March 25, 2026 — in progress)
- `AppSyncVisibility=PRIVATE` → all traffic stays on AWS backbone via VPC endpoints
- Lambda SG (HTTPS egress only) → VPC Interface Endpoints → AWS services
- 3 templates updated: `template.yaml`, `nested/appsync/template.yaml`, `patterns/unified/template.yaml`
- VPC endpoint management separated to `scripts/vpc-endpoints.yaml` (networking team)

### RBAC Architecture (March 9, 2026)
- 3-layer enforcement: AppSync auth directives → Lambda resolver filtering → UI adaptation
- 4 Cognito groups: Admin, Author, Reviewer, Viewer
- Server-side document filtering for Reviewer role in listDocuments resolver
- Config-version scoping data model ready (Phase 2)
