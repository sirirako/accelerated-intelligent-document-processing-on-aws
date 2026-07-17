# Key Decisions

Decisions made during this project that future agents need to know. Each entry
explains what was decided, why, and what the alternatives were.

## Fork over CDK wrapper

**Decision:** Use a fork with an `enterprise/` directory, not a CDK `CfnInclude` wrapper.

**Why:** The wrapper approach (CfnInclude + drift guard + synth-time overrides) was too complex.
CfnInclude has quirks (conditions can't reference new resources, fixed-name workarounds),
the drift guard is manual contract maintenance, and debugging synth failures is harder than
resolving merge conflicts.

**Alternatives rejected:** CDK wrapper (`CfnInclude`), standalone CDK project.

## Always Ping auth on Jobs API (no toggle)

**Decision:** When `EnableHeadless=true`, the Jobs API always uses PingAuthorizer. No
`EnablePingAuth` toggle, no conditional switching.

**Why:** SAM's transform validates `Auth.DefaultAuthorizer` and per-event `Authorizer` as
literal strings at transform time, before CloudFormation resolves `!If`. You cannot use
`!If` to conditionally switch authorizers in a SAM template. We tried — it fails with
"DefaultAuthorizer is not a string."

**Implication:** The Cognito M2M resources (`ApiUserPool`, `ApiUserPoolDomain`, etc.) are
removed from the enterprise fork's template. If you need Cognito M2M back, you'd need a
separate API Gateway resource.

## Multi-issuer + role-based auth (matching customer's existing code)

**Decision:** The Ping authorizer supports multiple issuers (`ISSUER1`/`ISSUER2`) and checks
`userRoles`/`memberOf` claims rather than OAuth2 scopes per HTTP method.

**Why:** The customer already has this pattern in their other APIs. Their Ping clients issue
tokens with group memberships, not API-specific scopes. Matching their existing model means
no Ping reconfiguration needed.

**Previous design:** Single issuer, scope-per-method (`jobs.read`/`jobs.write`). Abandoned
after seeing customer's actual authorizer code.

## Cognito UserPoolDomain removed (not just unused)

**Decision:** `ApiUserPool`, `ApiUserPoolDomain`, `ApiResourceServer`, `ApiAppClient` deleted
from template.yaml.

**Why:** `ApiUserPoolDomain` fails to create in VPC-only deployments (PrivateLink
incompatible) AND fails with uppercase stack names (Cognito domains must be lowercase).
Since we always use Ping, these resources are dead weight that causes deploy failures.

## configurationVersion via S3 metadata (not a custom pipeline step)

**Decision:** The `configurationVersion` field on `POST /jobs` is set as S3 object metadata
(`x-amz-meta-config-version`) on the presigned POST. The pipeline reads it from the object.

**Why:** The upstream pipeline already reads `config-version` from S3 object metadata
(`Document.from_s3_event` in `idp_common/models.py`). No pipeline changes needed — just
set the metadata at upload time and the existing logic picks it up.

## Separate config pipeline from deployment pipeline

**Decision:** Document configuration promotion (extraction rules, classification schemas)
runs in its own lightweight pipeline, separate from the infrastructure deployment pipeline.

**Why:** Configs change more frequently than code (weekly vs. monthly). Different approvers
(document specialists vs. engineers). Config upload is seconds vs. 20+ minutes for a full
deploy. Coupling them means config changes trigger unnecessary Docker builds.

## Environment config in S3 (not in code zip)

**Decision:** Per-environment deployment parameters live in S3 (`deploy/pipeline-config.yaml`),
not in the code zip. No fallback to local files.

**Why:** Same code zip goes to every environment. The S3 config is what makes it environment-
specific. Fallback configs with test values are dangerous — they can silently deploy wrong
parameters.

## Layer dependencies not committed to git

**Decision:** `enterprise/layers/*/python/` (PyJWT, pika, cryptography) are gitignored.
`enterprise/build.sh` installs them before publish.

**Why:** Binary `.so` files waste git storage, can't be diffed, and are platform-specific
(arm64 vs x86_64). The pipeline runs `build.sh` automatically. Only `requirements.txt` and
our own `ping_verifier.py` are tracked.
