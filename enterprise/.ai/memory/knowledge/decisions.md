# Key Decisions

Decisions made during this project. Each entry explains what was decided, why,
and what the alternatives were.

## Fork over CDK wrapper

**Decision:** Use a fork with an `enterprise/` directory, not a CDK `CfnInclude` wrapper.

**Why:** The wrapper approach was too complex. CfnInclude has quirks (conditions can't
reference new resources), drift guard is manual maintenance, debugging synth failures
is harder than resolving merge conflicts.

## Always Ping auth on Jobs API (no toggle)

**Decision:** When `EnableHeadless=true`, Jobs API always uses PingAuthorizer. No
conditional switching.

**Why:** SAM validates `Auth.DefaultAuthorizer` as a literal string at transform time.
`!If` conditionals fail with "DefaultAuthorizer is not a string." Cognito M2M resources
removed entirely from the fork.

## Multi-issuer + role-based auth

**Decision:** Ping authorizer supports multiple issuers and checks `userRoles`/`memberOf`
claims rather than OAuth2 scopes per method.

**Why:** Matches customer's existing authorizer pattern. Their Ping clients issue tokens
with group memberships, not API-specific scopes.

## Enterprise-owned deployment script

**Decision:** `enterprise/sdlc/codebuild_deployment.py` is a complete replacement for
upstream's `scripts/sdlc/codebuild_deployment.py`. Pipeline uses ours if present.

**Why:** Upstream's script (3700+ lines) gets rewritten every release — 24 merge conflicts
in v0.6.1. We lost critical enterprise logic (`--no-lint`, `skip_tests`, `role_arn`,
config params) THREE times during the merge. Our script is ~170 lines, focused on CD.

## Pipeline template stays shared (not enterprise-owned)

**Decision:** Keep `scripts/sdlc/cfn/codepipeline-s3.yml` as upstream's file with our
additions. Do NOT create a separate enterprise pipeline template.

**Why:** Pipeline template conflicts are additive (params, conditions, env vars) and
resolve cleanly with "keep both sides." Deployment script has logic rewrites.

## Buildspec: no external pulls

**Decision:** Remove `docker buildx create --driver docker-container`, `INSTALL_GIT=true`,
and any other commands that reach external endpoints.

**Why:** Customer's air-gapped environment blocks Docker Hub, cdn.amazonlinux.com, etc.
This mistake was made THREE times during v0.6.1 merge because upstream has these and they
pass in our test account. Do NOT trust test account results for air-gapped compatibility.

## VPC endpoint URL format for private API

**Decision:** `HttpApiEndpoint` output uses `{api-id}-{vpce-id}.execute-api...` format
when `IsPrivateApi` is true.

**Why:** Users on routable networks can reach the VPC endpoint but can't resolve the
standard API Gateway domain. Standard domain only works with private DNS inside the VPC.

## Per-job configurationVersion via S3 metadata

**Decision:** `configurationVersion` field on `POST /jobs` is set as S3 object metadata.
The pipeline reads it from the object — no pipeline changes needed.

## Enterprise version tracked separately from upstream

**Decision:** The fork's version lives in `enterprise/VERSION`, distinct from the root
`VERSION` (which mirrors the upstream application release we've merged). Format is
`<upstream-base>-ent.<n>`, e.g. `0.6.1-ent.1` — "upstream 0.6.1 base, enterprise
iteration 1." The enterprise counter increments each time we ship enterprise changes to
the customer; on an upstream merge the base rolls to the new upstream version and the
counter resets to 1 (e.g. `0.6.2-ent.1`). Git tags for enterprise releases are
`enterprise-v<enterprise-version>`, e.g. `enterprise-v0.6.1-ent.1`.

**Why:** Root `VERSION` and `CHANGELOG.md` track *upstream* — reusing that number for
enterprise builds collides with upstream's real releases (our "0.6.2" vs upstream's
0.6.2) and conflates two clocks that move independently: which AWS release we've merged
vs. how many times we've shipped on top of it. `enterprise/*` is enterprise-owned
(never overwritten by upstream per merge-rules), so `enterprise/VERSION` is merge-safe.
Each bump pairs with an activity log entry under `enterprise/.ai/memory/activities/`,
which serves as the per-iteration changelog.

**Alternatives:** `0.6.1+ent.1` (SemVer build-metadata — most correct, but `+` is awkward
in git tags and stripped by some tooling); a fully independent enterprise number like
`1.0.0` (loses the at-a-glance upstream base in the string).

## Separate config pipeline from deployment pipeline

**Decision:** Document configuration promotion runs in its own pipeline, separate from
infrastructure deployment.

**Why:** Configs change weekly vs code monthly. Different approvers. Config upload is
seconds vs 20+ minutes for a full deploy.

## Customer repo sync via zip + branch merge

**Decision:** Customer receives zip releases. They create a branch from zip, merge main
into it (resolve conflicts), test, then merge to their main.

**Why:** Air-gapped — no git clone from our repo. Branch-then-merge lets them test before
touching main, and preserves their local commits.
