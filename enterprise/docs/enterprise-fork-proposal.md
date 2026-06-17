# Proposal: IDP Enterprise Deployment Extensions

## Why

The upstream IDP accelerator focuses on the core document processing engine — OCR, classification, extraction, evaluation, and the Web UI. It's designed to be deployed with standard AWS networking and public package registries. This keeps the project simple, well-tested, and broadly applicable.

Enterprise deployments have additional requirements that sit **outside** the scope of core document processing:

- **Build-time security governance** — all dependencies must flow through approved, scanned artifact repositories (JFrog, CodeArtifact, Nexus) for compliance and audit trail
- **System integration** — existing applications need REST APIs to submit documents and retrieve results programmatically
- **Team boundaries** — infrastructure teams, development teams, and API consumers need separate IAM roles with distinct permission sets
- **CI/CD customization** — customer-specific source control (Bitbucket), pipeline triggers, and deployment workflows

These are deployment and integration concerns — not document processing concerns. They vary significantly by customer (different registries, different API shapes, different team structures), making them a poor fit for a one-size-fits-all upstream template.

By maintaining these as a separate enterprise layer, we:
- Keep the upstream focused and maintainable (no enterprise-specific code paths to test)
- Move fast on customer requirements without upstream release cycles
- Let each customer's specific needs (registry URLs, IAM boundaries, API contracts) live in configuration, not in code
- Continue contributing universal improvements (VPC support, architecture flexibility, bug fixes) back upstream

## Principles

1. **Never modify upstream logic** — core processing (OCR, classification, extraction, evaluation) stays untouched
2. **Additive only** — enterprise features go in `enterprise/` directory or as additional parameters/conditions
3. **Default-off** — deploying without enterprise params behaves identically to upstream
4. **Weekly sync** — automated merge from upstream, manual conflict resolution when needed
5. **Push universal improvements upstream** — VPC support, architecture param, bug fixes still go to upstream

## What we maintain (enterprise layer)

| Feature | Why it's outside upstream | Effort |
|---------|--------------------------|--------|
| Private registry support (Secrets Manager configs) | Customer-specific registry URLs, certs, credentials | 1 week |
| Integration REST API (API Gateway + Lambda) | Customer-specific API contracts and auth patterns | 2-3 weeks |
| Infra/dev team IAM separation | Customer-specific org structure and governance model | 1 week |
| SDLC pipeline enhancements (Bitbucket source) | Customer-specific CI/CD toolchain | 3-5 days |
| CA certificate bundle support | Customer-specific corporate PKI | 1-2 days |

## What stays upstream

| Feature | Status |
|---------|--------|
| CodeBuild VPC support | Merged ✅ |
| Lambda architecture parameter | PR pending |
| VPC endpoint SG fix | PR pending |
| Dependency manifest generation | Merged ✅ |
| API Gateway replacing AppSync (future) | Push upstream when ready |
| New model support, processing patterns | Always upstream |

## Phase 1: Fork Setup (Week 1)

### 1.1 Create the fork structure

```bash
# Fork already exists at sirirako/accelerated-intelligent-document-processing-on-aws
# Add upstream remote
git remote add upstream https://github.com/aws-solutions-library-samples/accelerated-intelligent-document-processing-on-aws.git

# Create enterprise develop branch from upstream
git checkout -b enterprise/develop upstream/develop
```

### 1.2 Add enterprise directory

```
enterprise/
├── README.md                    # What's different, how to deploy
├── CHANGELOG.md                 # Enterprise-only changes
├── registry/
│   ├── secrets-setup.yaml       # CFN template to create secrets
│   └── examples/
│       ├── jfrog-pip.conf
│       ├── jfrog-uv.toml
│       ├── jfrog-npmrc
│       └── jfrog-docker-config.json
├── api/
│   ├── template.yaml            # API Gateway nested stack
│   └── src/                     # Lambda handlers
├── iam/
│   ├── infra-role.yaml
│   ├── dev-role.yaml
│   └── api-consumer-role.yaml
└── docs/
    ├── deployment-enterprise.md
    ├── private-registry-setup.md
    ├── team-separation.md
    └── integration-api.md
```

### 1.3 Automated sync workflow

```yaml
# .github/workflows/sync-upstream.yml
name: Sync Upstream
on:
  schedule:
    - cron: '0 9 * * 1'  # Every Monday 9am
  workflow_dispatch: {}

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: enterprise/develop
          fetch-depth: 0

      - name: Fetch upstream
        run: |
          git remote add upstream https://github.com/aws-solutions-library-samples/accelerated-intelligent-document-processing-on-aws.git
          git fetch upstream develop

      - name: Attempt merge
        id: merge
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          if git merge upstream/develop --no-edit; then
            echo "result=clean" >> $GITHUB_OUTPUT
          else
            echo "result=conflict" >> $GITHUB_OUTPUT
          fi

      - name: Push clean merge
        if: steps.merge.outputs.result == 'clean'
        run: git push origin enterprise/develop

      - name: Create PR for conflicts
        if: steps.merge.outputs.result == 'conflict'
        run: |
          git add -A
          git commit -m "chore: sync upstream (conflicts need resolution)"
          BRANCH="sync/upstream-$(date +%Y%m%d)"
          git checkout -b $BRANCH
          git push origin $BRANCH
          gh pr create --title "chore: sync upstream (conflicts)" \
            --body "Automated merge from upstream/develop had conflicts. Resolve manually." \
            --base enterprise/develop --head $BRANCH
```

## Phase 2: Private Registry Support (Week 1-2)

Implement the plan at `~/.claude/plans/internal-artifact-registry.md`.

**Files modified (from upstream):**
- `template.yaml` — add parameters, conditions, pass-through to nested stacks
- `patterns/unified/template.yaml` — CodeBuild env vars for secrets
- `patterns/unified/buildspec.yml` — config file guards in install phase
- `Dockerfile.optimized` — parameterized FROM images + secret mounts
- `nested/multi-doc-discovery/template.yaml` — same pattern

**Files added:**
- `enterprise/registry/secrets-setup.yaml`
- `enterprise/registry/examples/*`
- `enterprise/docs/private-registry-setup.md`

**Test:** Deploy with public registry URLs in Secrets Manager → build succeeds → mechanism validated.

## Phase 3: SDLC Pipeline (Week 2)

Enhance `scripts/sdlc/cfn/codepipeline-s3.yml` for the customer's workflow:
- Add same registry secret params
- Buildspec install phase: write configs from secrets before `make setup`
- Document the Bitbucket → S3 → CodePipeline flow

## Phase 4: Integration REST API (Week 3-4)

### Overview

REST API that allows external systems to submit documents, check processing status, and retrieve results — without GraphQL or the Web UI. Based on the proven pattern from the Investigations & Compliance (InC) accelerator.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Customer's External System                           │
└─────────────────────┬───────────────────────────────────┬───────────────────┘
                      │                                   │
         1. POST /documents                  5. GET /documents/{id}/results
            {filenames: ["loan.pdf"]}           (after notification received)
                      │                                   │
                      ▼                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     API Gateway (REST, IAM Auth)                             │
│                     POST /documents    GET /status    GET /results           │
└─────────────────────┬──────────────────────┬────────────────────────────────┘
                      │                      │
                      ▼                      ▼
┌──────────────────────────┐   ┌──────────────────────────────────────────────┐
│  Documents Handler       │   │  Results Handler                              │
│  (Lambda)                │   │  (Lambda)                                     │
│                          │   │                                               │
│  • Create tracking       │   │  • Read from Output Bucket                   │
│    record in DynamoDB    │   │  • Return extraction JSON                    │
│  • Generate presigned    │   │                                               │
│    upload URL            │   └──────────────────────────────────────────────┘
│  • Return URL to caller  │
└────────────┬─────────────┘
             │
             │  Returns presigned S3 URL
             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Customer's External System                           │
│                                                                             │
│         2. PUT <presigned-url>  (upload loan.pdf directly to S3)            │
└─────────────────────┬───────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              IDP Stack (existing)                            │
│                                                                             │
│  ┌──────────┐    ┌───────────┐    ┌─────────┐    ┌──────────────────────┐  │
│  │  Input   │───▶│EventBridge│───▶│  SQS    │───▶│   Step Functions     │  │
│  │  Bucket  │    │           │    │  Queue  │    │                      │  │
│  │          │    └───────────┘    └─────────┘    │  3. OCR              │  │
│  │(S3 event)│                                    │     ↓                │  │
│  └──────────┘                                    │  Classification      │  │
│                                                  │     ↓                │  │
│                                                  │  Extraction          │  │
│                                                  │     ↓                │  │
│  ┌──────────┐                                    │  Assessment          │  │
│  │  Output  │◀───────────────────────────────────│     ↓                │  │
│  │  Bucket  │                                    │  Write Results       │  │
│  └──────────┘                                    │     ↓                │  │
│                                                  │  Post-Processing Hook│  │
│  ┌──────────────────┐                            └──────────┬───────────┘  │
│  │ Execution        │◀── status updates ────────────────────┘              │
│  │ Tracking Table   │                                                      │
│  │ (DynamoDB)       │                                                      │
│  └──────────────────┘                                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                      │
                      │  4. Post-Processing Lambda Hook
                      │     (on document completion)
                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Completion Hook Lambda                                   │
│                                                                             │
│  Receives: {document_id, status, output_s3_key}                            │
│  Sends to: Amazon MQ / SQS / SNS (configurable)                           │
│                                                                             │
│  Message: {                                                                 │
│    "document_id": "abc-123",                                               │
│    "status": "COMPLETED",                                                  │
│    "results_location": "s3://output-bucket/abc-123/results.json",          │
│    "completed_at": "2026-06-12T15:30:00Z"                                  │
│  }                                                                          │
└─────────────────────┬───────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Amazon MQ (or SQS/SNS)                                  │
│                                                                             │
│  Customer's message queue — their systems consume completion notifications  │
└─────────────────────┬───────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Customer's External System                               │
│                                                                             │
│  • Receives "COMPLETED" notification from MQ                                │
│  • Calls GET /documents/{id}/results to retrieve extraction data           │
│  • Stores results in their database                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Summary of the 5-step flow:**

1. **Submit** — External system calls `POST /documents` → gets presigned upload URL
2. **Upload** — External system uploads file directly to S3 via presigned URL
3. **Process** — IDP pipeline runs automatically (OCR → Classification → Extraction → Assessment) — **already exists**
4. **Notify** — On completion, hook Lambda sends message to customer's MQ
5. **Retrieve** — External system calls `GET /documents/{id}/results` → gets extraction JSON

**What's new (enterprise layer):** Steps 1, 4, 5 (API Gateway + completion hook)
**What already exists (upstream IDP):** Steps 2, 3 (S3 upload trigger + processing pipeline)

### Customer Flow

```
External System                        IDP Stack
──────────────                        ─────────
1. POST /documents                    → Create record in tracking table
   {filenames: ["doc.pdf"]}              Return presigned upload URL
                                      
2. PUT <presigned-url>                → Upload to Input Bucket
   (binary file upload)                  S3 event → EventBridge → SQS → Step Functions
                                         (existing IDP processing pipeline)
                                      
3. GET /documents/{id}/status         → Read from ExecutionTrackingTable
   (poll until complete)                 Return: QUEUED → PROCESSING → COMPLETED
                                      
4. [On completion]                    → PostProcessingLambdaHook fires
                                         → Hook Lambda drops message to MQ
                                         → External system receives notification
                                      
5. GET /documents/{id}/results        → Read from Output Bucket
                                         Return extraction JSON
```

### API Design

**Auth:** IAM Signature V4 (service-to-service). No Cognito — external systems authenticate with IAM credentials/role.

**Base URL:** `https://{api-id}.execute-api.{region}.amazonaws.com/v1`

**Endpoints:**

| Method | Path | Purpose | Request | Response |
|--------|------|---------|---------|----------|
| POST | `/documents` | Submit document(s) for processing | `{filenames, config_preset?}` | `{document_id, upload_urls[]}` |
| GET | `/documents/{id}/status` | Check processing status | — | `{status, documents[{name, status}], started_at, completed_at}` |
| GET | `/documents/{id}/results` | Get extraction results | — | `{documents[{name, extraction_result}]}` |
| DELETE | `/documents/{id}` | Cancel processing | — | `{cancelled: true}` |
| GET | `/health` | Health check | — | `{status: "ok", version}` |

**Error format:** RFC 7807 Problem Details (same as InC pattern):
```json
{
  "type": "https://idp.example.com/errors/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Document batch 'abc-123' not found"
}
```

### Implementation

**Directory structure:**
```
enterprise/api/
├── template.yaml              # API Gateway + Lambda + IAM (CloudFormation)
├── src/
│   ├── documents_handler.py   # POST/GET/DELETE /documents
│   ├── results_handler.py     # GET /documents/{id}/results
│   ├── health_handler.py      # GET /health
│   └── common/
│       ├── models.py          # Pydantic request/response models
│       ├── responses.py       # RFC 7807 error helpers
│       └── auth.py            # IAM auth utilities
└── tests/
    ├── test_documents_handler.py
    └── test_results_handler.py
```

**Key patterns copied from InC accelerator:**
- Presigned URL generation via AssumeRole (security isolation — Lambda assumes a minimal PutObject-only role)
- Pydantic models for request validation and response serialization
- RFC 7807 error responses
- DynamoDB state management for document batches
- Cached boto3 clients for Lambda warm starts

**What's different from InC:**
- IAM auth instead of Cognito (service-to-service)
- No "check sets" or "findings" — just documents and extraction results
- On-completion hook → MQ message (using existing `PostProcessingLambdaHookFunctionArn`)
- Results come from IDP's output S3 bucket (not a separate findings table)

### Template wiring

```yaml
# In main template.yaml (enterprise fork)
EnterpriseAPIStack:
  Type: AWS::CloudFormation::Stack
  Condition: EnableEnterpriseAPI
  Properties:
    TemplateURL: ./enterprise/api/template.yaml
    Parameters:
      StackName: !Ref AWS::StackName
      InputBucket: !Ref InputBucket
      OutputBucket: !Ref OutputBucket
      TrackingTable: !Ref ExecutionTrackingTable
      CustomerManagedEncryptionKeyArn: !GetAtt CustomerManagedEncryptionKey.Arn
      VpcId: !If [DeployInVPC, !Ref VpcId, ""]
      PrivateSubnetIds: !If [DeployInVPC, !Join [",", !Ref PrivateSubnetIds], ""]
      LambdaSecurityGroupId: !If [DeployInVPC, !Ref LambdaSecurityGroupId, ""]
```

### Completion notification (Lambda hook → MQ)

The IDP stack already has `PostProcessingLambdaHookFunctionArn` — a parameter that lets you plug in a Lambda that fires after each document completes processing.

We provide a pre-built hook Lambda (`enterprise/api/src/completion_hook.py`) that:
1. Receives the completion event (document ID, status, output location)
2. Formats a message
3. Sends to Amazon MQ / SQS / SNS (configurable via env var)

```python
# enterprise/api/src/completion_hook.py
def handler(event, context):
    """Post-processing hook — fires when a document finishes processing."""
    document_id = event["document_id"]
    status = event["status"]
    output_key = event["output_s3_key"]
    
    message = {
        "document_id": document_id,
        "status": status,
        "results_location": f"s3://{OUTPUT_BUCKET}/{output_key}",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # Send to configured destination
    if MQ_BROKER_URL:
        send_to_mq(message)
    elif SNS_TOPIC_ARN:
        send_to_sns(message)
    elif SQS_QUEUE_URL:
        send_to_sqs(message)
```

### API Gateway configuration

- **Type:** REST API (regional or private based on `DeployInVPC`)
- **Auth:** IAM (`AWS_IAM` authorization type)
- **Throttling:** 50 req/s sustained, 100 burst (configurable)
- **WAF:** AWS managed rules (CommonRuleSet, KnownBadInputs)
- **Logging:** Access logs to CloudWatch
- **VPC:** Private endpoint when `DeployInVPC=true` (same pattern as AppSync private)

### Parameters

```yaml
EnableEnterpriseAPI:
  Type: String
  Default: "false"
  AllowedValues: ["true", "false"]
  Description: "Enable REST API Gateway for system integration"

MQBrokerUrl:
  Type: String
  Default: ""
  Description: "(Optional) Amazon MQ broker URL for completion notifications"

CompletionNotificationTarget:
  Type: String
  Default: ""
  AllowedValues: ["", "MQ", "SNS", "SQS"]
  Description: "Where to send document completion notifications"
```
```

## Phase 5: IAM Team Separation (Week 4-5)

### What "team separation" means here

Team separation is about **access boundaries** (who can do what), not resource-level code ownership (who can change which resource within a deployment). The IDP stack is a single CloudFormation stack — there's no way to say "this role can update Lambda code but not IAM roles" within the same stack.

**What we can enforce:**

| Boundary | Enforcement | Mechanism |
|----------|-------------|-----------|
| Who can deploy/update the stack | IAM role (infra team only) | Only infra role has `cloudformation:*` |
| Who can trigger a deployment | CI pipeline only | Dev team pushes to repo → CI runs tests → CI drops zip to S3 → CodePipeline deploys. No human has direct `s3:PutObject` on source bucket. |
| Who can use the application | Cognito groups | Already exists upstream (Admin/Author/Reviewer/Viewer) |
| Who can call the integration API | IAM role or API key | API consumer role with `execute-api:Invoke` only |

**What we cannot technically enforce:**

- Dev team pushes code that modifies `template.yaml` (adds IAM roles, changes VPC) — the pipeline deploys it because it runs `idp-cli deploy` on whatever's in the zip
- Resource-level ownership within a single stack (e.g., "dev can change Lambda but not KMS keys")

**Mitigation:** Code review (infra team approves PRs that touch templates/IAM). The gate is a human process, not a technical one. Optionally, a CloudFormation stack policy can lock specific resources (KMS keys, IAM roles) from modification even through the pipeline.

### Implementation

Two CloudFormation templates in `enterprise/iam/`:

- **Infra role** (`infra-role.yaml`):
  - `cloudformation:*` on `idp-*` stacks
  - `iam:PassRole` for the CloudFormation service role
  - `secretsmanager:*` for registry secrets rotation
  - `ec2:*` for VPC/endpoint management
  - Used by: infra team deploying/updating the stack directly

- **CI/pipeline service role** (`pipeline-role.yaml`):
  - `s3:PutObject` on the pipeline source bucket (only CI holds this — not humans)
  - The pipeline's CodeBuild uses a **service role** with full deploy permissions
  - Dev team pushes to repo → CI validates (lint, test, security scan) → CI drops zip to S3 → pipeline deploys
  - No human bypasses CI to deploy directly
  - Used by: CI system (Bitbucket/GitHub/GitLab service account)

- **API consumer role** (`api-consumer-role.yaml`):
  - `execute-api:Invoke` on the integration API Gateway only
  - No S3, no DynamoDB, no Lambda, no CloudFormation
  - Used by: external systems calling the REST API

## Phase 6: AI Gateway Support (Future)

### Overview

Allow customers to route all LLM/AI calls through their corporate AI Gateway instead of calling Amazon Bedrock directly. The AI Gateway sits between the IDP Lambda functions and the model provider, giving the enterprise centralized control over AI usage.

### Why

Enterprise customers deploy AI Gateways to enforce:
- **Token usage tracking & chargeback** — attribute AI costs to specific teams/projects
- **Content filtering & guardrails** — additional content safety beyond Bedrock Guardrails
- **Model routing** — switch between providers/models without code changes
- **Rate limiting** — per-team or per-application quotas
- **Audit logging** — full prompt/response logging for compliance
- **Approved model allow-listing** — only specific models can be invoked

### How it works today (direct Bedrock)

```
Lambda (OCR/Classification/Extraction/Assessment/Summarization)
  │
  ▼
Amazon Bedrock (InvokeModel / InvokeModelWithResponseStream)
  │
  ▼
Foundation Model (Claude, Nova, etc.)
```

### How it would work with AI Gateway

```
Lambda (OCR/Classification/Extraction/Assessment/Summarization)
  │
  │  Instead of calling Bedrock directly,
  │  call the AI Gateway endpoint (same API contract)
  ▼
Customer's AI Gateway (e.g., LiteLLM, MLflow AI Gateway, custom proxy)
  │
  │  Gateway handles: auth, logging, rate limiting, routing
  ▼
Amazon Bedrock (or other providers)
  │
  ▼
Foundation Model
```

### Scope (placeholder — requires investigation)

**What needs to change:**
- `idp_common/bedrock/client.py` — the `BedrockClient` needs to support an alternative endpoint URL
- Either:
  - Option A: `BEDROCK_ENDPOINT_URL` override (if the gateway implements the Bedrock Converse API)
  - Option B: Custom HTTP client that translates to the gateway's API format (if gateway uses OpenAI-compatible API)
- IAM/auth — the gateway may use a different auth mechanism (API key, mTLS, IAM) than Bedrock's SigV4

**What stays the same:**
- All prompt construction, response parsing, tool use logic
- The processing pipeline (Step Functions, S3, DynamoDB)
- Configuration system (model IDs, temperature, etc. — the gateway may remap these)

### Key decisions (TBD)

1. **Gateway API contract** — Does the customer's AI Gateway implement:
   - Bedrock Converse API (drop-in, just change endpoint URL)?
   - OpenAI-compatible API (need translation layer)?
   - Custom API (need adapter)?

2. **Configuration** — How to tell IDP to use the gateway:
   - `AIGatewayEndpointUrl` parameter (simplest — just override the Bedrock endpoint)?
   - `AIGatewayApiKeySecretArn` for auth?
   - Per-service override (e.g., extraction uses gateway, OCR uses Bedrock directly)?

3. **VPC routing** — The AI Gateway is likely internal (within the VPC). Lambda functions already run in VPC (Phase 1). Just need the security group to allow outbound to the gateway.

4. **Upstream vs fork** — Could go upstream if:
   - The implementation is just an endpoint URL override (minimal, backward-compatible)
   - If it requires a major client rewrite, better in the fork initially

### What we need from the customer

- What AI Gateway product/solution are they using?
- What API does it expose (Bedrock-compatible, OpenAI-compatible, custom)?
- How does it authenticate requests (API key, mTLS, IAM)?
- Is it deployed within the VPC or external?

### Timeline

Not in the initial enterprise fork scope. Depends on customer's AI Gateway choice. Estimated 1-2 weeks once requirements are clear (if Bedrock-compatible endpoint, it's mostly just an endpoint URL override).

---

## Merge Conflict Expectations

| File | Conflict frequency | Resolution effort |
|------|-------------------|-------------------|
| `CHANGELOG.md` | Every sync | Trivial (additive) |
| `template.yaml` params section | Monthly | Low (our params at bottom) |
| `Dockerfile.optimized` | Rare | Medium (check build args preserved) |
| `patterns/unified/buildspec.yml` | Rare | Medium (check guards preserved) |
| `enterprise/` directory | Never | N/A (ours only) |
| Lambda code, UI, config library | Never | N/A (we don't modify) |

## Customer Delivery

Customer clones the fork (enterprise/develop branch) and deploys:

```bash
# Standard deployment (identical to upstream)
idp-cli deploy --stack-name IDP --admin-email admin@example.com

# Enterprise deployment (private registry + API)
idp-cli deploy --stack-name IDP --admin-email admin@example.com \
  --parameters "DeployInVPC=true,\
VpcId=vpc-xxx,\
PrivateSubnetIds=subnet-a,subnet-b,\
LambdaSecurityGroupId=sg-xxx,\
DockerConfigSecretArn=arn:...,\
UvConfigSecretArn=arn:...,\
PipConfigSecretArn=arn:...,\
NpmConfigSecretArn=arn:...,\
UvImage=jfrog.company.com/docker/uv:0.9.6,\
LambdaBaseImage=jfrog.company.com/docker/lambda/python,\
EnableEnterpriseAPI=true"
```

## Timeline

| Week | Deliverable |
|------|-------------|
| 1 | Fork structure + sync workflow + private registry (Dockerfile/buildspec) |
| 2 | Private registry (template params + IAM) + testing + SDLC pipeline |
| 3 | Integration API design + Lambda handlers |
| 4 | Integration API (API Gateway template + wiring) |
| 5 | IAM separation + documentation + customer handoff |

## Success Criteria

- [ ] `make dep-manifest` produces complete manifest from fork
- [ ] Deploy with private registry params → build pulls from Secrets Manager configs → succeeds
- [ ] Deploy without enterprise params → identical to upstream (regression test)
- [ ] Weekly upstream sync merges cleanly (or conflicts resolved within 1 day)
- [ ] Integration API handles submit → process → retrieve flow end-to-end
- [ ] Three IAM roles deployed and tested with correct permission boundaries
