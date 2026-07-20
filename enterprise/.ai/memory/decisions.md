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

## xlsx tarball URL parameterized (not hardcoded in package.json)

**Decision:** `package.json` uses the default SheetJS CDN URL (`https://cdn.sheetjs.com/xlsx-0.20.2/xlsx-0.20.2.tgz`).
A CloudFormation parameter `XlsxTarballUrl` allows air-gapped deployments to override it. The
WebUI buildspec `install` phase runs `sed` to replace the CDN URL before `npm ci`.

**Why:** SheetJS `xlsx` is not on the npm registry — it's distributed as a direct tarball URL.
Air-gapped builds can't reach `cdn.sheetjs.com`. The customer must host the tarball in their
JFrog instance. Parameterizing avoids hardcoding customer-specific URLs in the codebase and
avoids requiring the customer to manually edit `package.json` on every code update.

**Alternatives rejected:**
- Hardcode customer URL in package.json — leaks customer info, breaks internet-connected builds
- Publish xlsx to JFrog's local npm repo as a proper package — SheetJS pulled it from npm years
  ago, no standard registry metadata exists, would require manual `npm publish` setup
- Remove xlsx dependency — it's actively used in `download-func.ts` for Excel export

## WebUI buildspec: rely on CodeBuild's built-in Node (no `n` install)

**Decision:** Remove `n 22.14.0` and `npm install -g npm@11.1.0` from the WebUI buildspec.
Rely on the Node.js version pre-installed in the CodeBuild image (`aws/codebuild/amazonlinux2-x86_64-standard:5.0`).

**Why:** In the air-gapped customer environment, `n` cannot reach `nodejs.org` to download
Node binaries. The customer confirmed their CodeBuild image already has a compatible Node
version. Their working buildspec omits the `n` install entirely.

**Alternatives rejected:**
- `N_NODE_MIRROR` env var pointing to JFrog mirror — customer's JFrog doesn't replicate
  nodejs.org's `/vX.Y.Z/` directory structure (flat path instead)
- Direct tarball download from internal registry — adds complexity for a version that's
  already in the image
- `--engine-strict=false` with Node 18 — fragile long-term

## WebUI .npmrc written from Secrets Manager at build time

**Decision:** The WebUI CodeBuild `install` phase writes `~/.npmrc` from the `NpmConfigSecretArn`
secret before `npm ci` runs. This was missing — `NpmConfigSecretArn` parameter existed but was
never wired into the WebUI CodeBuild project.

**Why:** Air-gapped builds need `.npmrc` to point npm at the internal JFrog registry. Without
it, `npm ci` tries to reach `registry.npmjs.org` and fails. The parameter was already in the
template but never connected to the WebUI build (it was only passed to the pattern stack for
Docker builds).

## Layer dependencies not committed to git

**Decision:** `enterprise/layers/*/python/` (PyJWT, pika, cryptography) are gitignored.
`enterprise/build.sh` installs them before publish.

**Why:** Binary `.so` files waste git storage, can't be diffed, and are platform-specific
(arm64 vs x86_64). The pipeline runs `build.sh` automatically. Only `requirements.txt` and
our own `ping_verifier.py` are tracked.

## Minimal buildspec diff from upstream (v0.6.1+)

**Decision:** `patterns/unified/buildspec.yml` should be upstream's file exactly, with only
two additive changes: (1) an `install` phase for registry config, (2) `SECRET_ARGS` for
Docker build `--secret` mounts.

**Why:** Previous divergence (removing buildx multiarch builder, adding `--config` flags,
custom base image args in the build loop) caused deploy failures. The `docker buildx create
--driver docker-container` was accidentally removed, breaking arm64 builds. Less diff from
upstream = fewer merge conflicts and subtle breakages.

**Implication:** The customer's x86_64 native builds work fine with the multiarch builder
present (it's a no-op for same-arch builds). The `docker-container` driver pulls
`moby/buildkit` from Docker Hub — this works in our test account but will fail in the
customer's air-gapped environment. Since the customer uses x86_64, the builder is created
but cross-compilation is never triggered. If they switch to arm64, they'd need `moby/buildkit`
in their internal registry.

## Take upstream for application code (v0.6.1+)

**Decision:** Always take upstream's version for application code — patterns/unified/template.yaml
schema, extraction logic, assessment, classification, UI components. Don't modify their
application behavior.

**Why:** Upstream's code evolves (retiring granular assessment, adding validation/escalation,
sharding). Our previous merge incorrectly kept our old sampling params and postHook alongside
upstream's restructured code, causing duplicates. Upstream now includes postHook and sampling
params in their own schema.

**Enterprise changes are limited to:**
- Parameters/conditions/IAM in nested templates (registry secrets pass-through)
- Buildspec install phase (registry config)
- Main template enterprise block (Ping auth, completion hook, registry params)
- Configuration (environment params, pipeline config)
