# Enterprise Integration — Design & Code Review Guide

This document is a self-contained review checklist for the enterprise
integration feature (Ping API auth, Amazon MQ completion hook, pipeline hooks
framework). It is **tool-agnostic** — include it in the context of any AI
coding assistant (Claude Code, Cline, Cursor, Copilot, Aider, etc.) or use it
as a human review reference.

## How to Use

1. **Include this file in context** when asking your AI assistant to review
   enterprise-related code or design decisions.
2. Ask it to run **Phase 1** (design review) before implementation, or
   **Phase 2** (code review) after implementation — or both.
3. The assistant should produce findings using the output format at the bottom.

---

## Architecture Context

```
External System
  │  1. POST /token (client_credentials) → PingFederate (in-VPC)
  │  2. Authorization: Bearer <Ping JWT>
  ▼
Private API Gateway
  │  Ping REQUEST authorizer (validates JWT, enforces scopes)
  ▼
Jobs API Handler (unchanged)
  POST /jobs → submit documents (requires jobs.write scope)
  GET  /jobs/{id} → retrieve results (requires jobs.read scope)
  │
  ▼
Processing Pipeline (OCR → Classification → Extraction → Assessment)
  │  At each step: PipelineHooksDispatcher invokes registered postHook Lambdas
  │
  ▼
On SUCCEEDED: CompletionHook Lambda
  → fetches Ping client-credentials token
  → publishes notification to Amazon MQ (RabbitMQ) via AMQPS
```

**Key files:**
- `enterprise-addon/ping_authorizer/app.py` — REQUEST authorizer handler
- `enterprise-addon/ping_authorizer/scopes.py` — scope enforcement logic
- `enterprise-addon/layers/ping_verifier/python/ping_verifier.py` — shared JWT validation
- `enterprise-addon/completion_hook/app.py` — completion hook handler
- `enterprise-addon/completion_hook/ping_token.py` — Ping client-credentials token fetcher
- `enterprise-addon/completion_hook/mq_rabbitmq.py` — AMQPS publisher
- `enterprise-addon/completion_hook/event.py` — EventBridge event → message payload
- `patterns/unified/src/pipeline_hooks_function/index.py` — pipeline hooks dispatcher

---

## Phase 1 — Design Review

Ask these questions of the proposed approach. If reviewing your own plan,
answer them before writing code.

### 1.1 Ping Auth Design

| Question | What "good" looks like |
|----------|----------------------|
| Does it preserve Cognito as a fallback? | Cognito resources remain in the stack, untouched. Only the API authorizer reference switches. |
| Is the authorizer stateless? | No DynamoDB, no session store. Validation is JWT signature + claims only. |
| Is JWKS resolution cacheable? | `PyJWKClient(lifespan=600)` or equivalent. No per-request JWKS fetch. |
| Are scopes the sole authorization mechanism? | Method → scope mapping is declarative (`GET→read`, mutating→`write`). No role-based or group-based logic in the authorizer. |
| Is audience matching flexible? | Must check `aud` OR `azp` OR `client_id` — Ping tokens vary by configuration. |
| Is the layer shared correctly? | `ping_verifier` layer used by both the authorizer AND the completion hook (single source of truth for validation logic). |
| Is the feature toggleable? | `EnablePingAuth=true/false` — no side effects when disabled; same template, same deploy command. |

### 1.2 Amazon MQ Completion Hook Design

| Question | What "good" looks like |
|----------|----------------------|
| Is auth M2M via Ping? | Hook fetches its own client-credentials token. Does NOT reuse the inbound API token. |
| Is the broker connection short-lived? | Open → publish → close. No persistent connections or connection pools in Lambda. |
| Is TLS mandatory? | AMQPS (port 5671) only. No plaintext AMQP fallback. |
| Is the message idempotent? | `message_id` = Step Functions execution ARN (unique, deterministic). Consumer-side dedup possible. |
| Is the message contract minimal? | Only: `document_id`, `status`, `num_pages`, `results_location`, `execution_arn`, `completed_at`. No raw extraction results, no PII. |
| Is the secret fetch pattern correct? | Client secret in Secrets Manager, fetched via boto3 at runtime, never in env vars. |
| Is token caching safe? | Cache per warm container, refresh 30s before expiry. No cross-invocation leakage risk. |
| Does it use the existing hook mechanism? | Wired via `PostProcessingLambdaHookFunctionArn` (EventBridge → Decompressor → hook). Not a custom integration. |

### 1.3 Pipeline Hooks Framework Design

| Question | What "good" looks like |
|----------|----------------------|
| Are hooks config-driven? | Stored inline in the active config version (`<step>.postHook[]`). Changing config version atomically swaps hooks. |
| Is the dispatch order deterministic? | Sorted by `(order, featureId)`. Ties are alphabetical. |
| Are error semantics explicit? | `onError: continue` (default) / `skip-remaining` / `fail`. No silent swallowing. |
| Is the no-hooks path zero-cost? | Single DDB GetItem → empty list → immediate return. No Lambda invocations. |
| Does it support config pinning? | `document.config_version` overrides the active version scan. Per-document hook sets. |
| Are hook ARNs scoped? | IAM policy scopes `lambda:InvokeFunction` to specific ARN patterns (e.g., feature prefix). |
| Is the dispatcher generic? | Knows nothing about what hooks do. Pure dispatch + error handling. |

### 1.4 Cross-Cutting Design Questions

| Question | What "good" looks like |
|----------|----------------------|
| Can features be enabled independently? | Any combination of `EnablePingAuth` × `EnableCompletionHook` is valid. |
| Is the VPC story coherent? | Ping auth requires VPC (JWKS endpoint). MQ hook requires VPC (broker port). Both share the same `LambdaSecurityGroupId`. |
| Are there circular dependencies? | Completion hook → Ping token → Secrets Manager. No dependency on the API Gateway or authorizer. |
| Is observability preserved? | X-Ray tracing, structured logging, CloudWatch alarms for hook failures. |
| Is the feature additive? | Disabling the feature removes its resources cleanly. No orphaned references or conditions that break the base stack. |

---

## Phase 2 — Code Review

Run these checks against the implementation.

### 2.1 Ping Auth — Code Checks

- [ ] Authorizer is REQUEST type (not TOKEN) — receives full event with headers, path, method
- [ ] Bearer extraction is case-insensitive — `authorization` header lookup handles mixed case
- [ ] `verify()` raises `PingTokenError` on ALL failure paths — empty token, bad signature, expired, audience mismatch
- [ ] `verify_aud: False` in PyJWT + manual audience check — required because Ping tokens put audience in `aud`, `azp`, OR `client_id` depending on grant type
- [ ] Algorithms restricted — only `RS256` and `ES256` accepted (not `HS256`, not `none`)
- [ ] Authorizer returns IAM policy — `Allow` or `Deny` with `execute-api:Invoke`, not a boolean
- [ ] Principal = `sub` or `client_id` — never `*` or empty
- [ ] No authorizer result caching — `ReauthorizeEvery: 0` in the API Gateway config (scopes must be checked per-request)
- [ ] Scope matching allows namespace prefix — `idp-api/jobs.write` matches `jobs.write` requirement
- [ ] `write` scope implies `read` — token with `jobs.write` can also do GET
- [ ] Layer `requirements.txt` pins exact versions — `PyJWT[crypto]==2.9.0` (not `>=`)
- [ ] No secrets in env vars — only `PING_ISSUER`, `PING_JWKS_URI`, `PING_API_AUDIENCE` (public values)

### 2.2 Amazon MQ Completion Hook — Code Checks

- [ ] Token fetched per invocation (with warm-container cache) — no env-var tokens
- [ ] `_client_secret()` handles both JSON and raw string in Secrets Manager
- [ ] Connection uses `ssl.create_default_context()` — system CA bundle, no `verify=False`
- [ ] `socket_timeout` and `blocked_connection_timeout` set — no indefinite hangs
- [ ] `connection_attempts=2` with `retry_delay` — transient network errors retried
- [ ] `delivery_mode=2` — persistent messages survive broker restart
- [ ] Connection closed in `finally` block — no leaked connections on publish failure
- [ ] `parse_completion()` is pure — no boto3, no side effects, fully unit-testable
- [ ] Missing fields produce empty strings, not exceptions — graceful degradation
- [ ] No PII in the message body — only IDs, status, page count, S3 URI, timestamps
- [ ] `content_type="application/json"` set on AMQP properties
- [ ] Lambda returns success payload — `{"published": True, "document_id": ..., "message_id": ...}`

### 2.3 Pipeline Hooks Framework — Code Checks

- [ ] Unknown `hookPoint` → immediate no-op return (not an error, not a raise)
- [ ] Missing `CONFIGURATION_TABLE_NAME` → immediate no-op (no boto3 calls)
- [ ] Config decompression handles both compressed and inline — mirrors `_decompress_item` from `idp_common`
- [ ] Active version resolution: pinned > IsActive=true scan > "default" fallback
- [ ] Hooks sorted by `(order, featureId)` before dispatch
- [ ] `enabled: false` entries filtered out before dispatch
- [ ] Entries without `arn` field silently skipped (not an error)
- [ ] `onError=fail` raises `RuntimeError` — propagates to Step Functions as a FAILED state
- [ ] `onError=skip-remaining` stops the loop but does NOT raise
- [ ] `onError=continue` (default) logs and proceeds to next hook
- [ ] Invoke payload includes: `hookPoint`, `featureId`, `document`, `section`, `executionArn`
- [ ] `FunctionError` in response → treated as failure (not silently ignored)
- [ ] Return value includes `configVersion` — auditable which config drove dispatch

### 2.4 Infrastructure — Template Checks

- [ ] All new parameters have `Default: ""` or sensible defaults — optional features must not break existing deploys
- [ ] Condition resources use `!If` — enterprise resources only created when enabled
- [ ] No hardcoded `arn:aws:` — use `${AWS::Partition}` (GovCloud compatibility)
- [ ] No hardcoded `amazonaws.com` — use `${AWS::URLSuffix}`
- [ ] New Lambda functions have dedicated LogGroups with KMS encryption
- [ ] PermissionsBoundary conditional on all new IAM roles
- [ ] Lambda security group allows outbound to Ping JWKS endpoint AND MQ broker port
- [ ] Secrets Manager permission scoped to the specific secret ARN (not `*`)
- [ ] `lambda:InvokeFunction` permission scoped to hook ARN patterns (not `*`)
- [ ] Layer ARNs use `!Ref` — not hardcoded, version-locked via SAM

### 2.5 Security — Enterprise-Specific

- [ ] No JWT logged in plaintext — log `sub`/`client_id` only, never the token itself
- [ ] Token cache doesn't leak across tenants — cache key includes the token URL
- [ ] JWKS fetched over HTTPS — no HTTP fallback
- [ ] Secrets Manager secret not logged — `_client_secret()` result never in logs
- [ ] MQ credentials not in CloudFormation outputs — no exports of secret ARNs
- [ ] Authorizer denies on any validation failure — no "soft fail" path that allows access
- [ ] Completion hook message doesn't contain extraction results — only pointers (S3 URI)
- [ ] Lambda env vars contain NO secrets — only public endpoints, client IDs, table names

### 2.6 Testing — Enterprise-Specific

- [ ] Authorizer unit tests cover: valid token → Allow, expired → Deny, bad signature → Deny, wrong audience → Deny, missing scope → Deny, write-implies-read → Allow
- [ ] Scope tests cover: plain scope, namespaced scope (`prefix/scope`), `scp` claim (list format), `scope` claim (space-separated string)
- [ ] Completion hook tests cover: happy path publish, Ping token fetch failure, MQ connection failure, malformed event graceful handling
- [ ] `parse_completion()` tested with: full event, minimal event, missing fields, compressed document wrapper
- [ ] Dispatcher tests cover: unknown hookPoint, missing table env, disabled hooks filtered, order sorting, all three onError modes, config pinning from document
- [ ] No moto needed for pure modules — `event.py`, `scopes.py`, `ping_verifier.py` are pure logic; test without mocks

---

## Red Flags — Stop and Fix Immediately

Flag these in any enterprise-related diff:

| Pattern | Why it's dangerous |
|---------|-------------------|
| `token` or `access_token` in a log statement | Plaintext JWT leak |
| `verify=False` or `ssl_context` with disabled cert verification | MITM vulnerability |
| `HS256` in allowed algorithms | Symmetric key — attacker with JWKS can forge tokens |
| MQ password in env var or CFN parameter | Credential exposure in console/logs |
| `InvocationType="Event"` on hook dispatch | Async = can't detect/handle errors |
| Hook `onError` defaulting to `fail` | One broken hook kills all processing |
| `ReauthorizeEvery` > 0 on Ping authorizer | Cached authz = stale scope enforcement |
| Completion message containing raw `attributes` | PII leak to external MQ broker |
| Hardcoded `arn:aws:` in CFN templates | Breaks GovCloud deployments |
| `Resource: "*"` on SecretsManager or Lambda invoke | Over-privileged IAM |
| Missing `finally: connection.close()` in MQ publisher | Connection leak in Lambda |
| Ping token cached without expiry check | Stale/expired token reuse |

---

## Output Format

When producing a review, use this structure:

```markdown
## Enterprise Review: <component>

### Design Phase
| Question | Verdict | Notes |
|----------|---------|-------|
| ... | PASS / WARN / FAIL | ... |

### Code Phase
- BLOCKING — <file>:<line> — description + suggested fix
- SHOULD FIX — <file>:<line> — description
- NICE TO HAVE — <file>:<line> — description

### Recommendation
<Approve / Request changes / Redesign needed>

<one-paragraph rationale>
```

---

## Example Prompt for Your AI Assistant

```
Please review my enterprise integration changes using the review guide in
enterprise-addon/REVIEW_GUIDE.md. Run both Phase 1 (design) and Phase 2
(code) and produce findings in the specified output format.
```
