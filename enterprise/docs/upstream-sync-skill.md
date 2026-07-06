# Upstream Sync & Conflict Resolution

## When to use

Use this skill when:
- Merging `upstream/develop` into the enterprise fork
- Resolving merge conflicts after an upstream sync
- Reviewing what upstream changed vs what our fork modifies

## Enterprise fork context

This repo is an enterprise fork of `aws-solutions-library-samples/accelerated-intelligent-document-processing-on-aws`. We maintain additional features on top of upstream:

- **Private registry support** — Secrets Manager configs for pip/uv/npm/docker
- **Integration REST API** — API Gateway for system-to-system document submission
- **IAM team separation** — Infra/dev/API consumer role boundaries
- **AI Gateway support** — Route LLM calls through corporate proxy

## Files we modify (conflict-prone)

These upstream files have enterprise modifications. During sync, conflicts here are expected:

| File | What we changed | Resolution guidance |
|------|----------------|---------------------|
| `template.yaml` (params section, ~line 560-630) | Added `DockerConfigSecretArn`, `UvConfigSecretArn`, `PipConfigSecretArn`, `NpmConfigSecretArn`, `CACertBundleS3Uri`, `UvImage`, `LambdaBaseImage` params | Keep both — our params go after upstream's. Accept any new upstream params above ours. |
| `template.yaml` (conditions, ~line 680-690) | Added `HasDockerConfigSecret`, `HasUvConfigSecret`, `HasPipConfigSecret`, `HasNpmConfigSecret` | Keep both — our conditions are additive. |
| `template.yaml` (PATTERNSTACK pass-through) | Pass registry params to nested stack | Keep our lines — they reference our params. If upstream adds new pass-throughs nearby, keep both. |
| `patterns/unified/template.yaml` (params) | Added registry secret params + conditions | Same as main template — additive. |
| `patterns/unified/template.yaml` (DockerBuildProject env vars) | Added `PIP_CONF`, `UV_CONF`, `DOCKER_CONF` with `Type: SECRETS_MANAGER` | Keep ours. If upstream adds new env vars, keep both. |
| `patterns/unified/buildspec.yml` (install phase) | Added config file guards (`if [ -n "${PIP_CONF:-}" ]`) | Keep ours at the end of install phase. If upstream modifies install commands, keep both — ours are independent. |
| `Dockerfile.optimized` (FROM lines + RUN) | Parameterized `UV_IMAGE`, `BASE_IMAGE_REGISTRY`, `BASE_IMAGE_SUFFIX` build args + `--mount=type=secret` | Keep ours. If upstream changes the FROM image tag or adds stages, update our ARG defaults to match. |
| `nested/multi-doc-discovery/template.yaml` | Same registry pattern as unified | Same resolution approach. |
| `scripts/sdlc/codebuild_deployment.py` (`publish_templates()`) | Changed bucket derivation from hardcoded account ID to `SOURCE_BUCKET` env var | Keep ours — upstream may still have the hardcoded default. If upstream fixes this too, accept theirs (same intent). |
| `scripts/sdlc/cfn/codepipeline-s3.yml` (params) | Added `DockerConfigSecretArn`, `UvConfigSecretArn`, `PipConfigSecretArn`, `NpmConfigSecretArn`, `CACertBundleS3Uri` params | Keep both — our params are grouped under `# ── Air-gapped / private registry parameters ──`. Accept any new upstream params above ours. |
| `scripts/sdlc/cfn/codepipeline-s3.yml` (conditions) | Added `HasDockerConfigSecret`, `HasUvConfigSecret`, `HasPipConfigSecret`, `HasNpmConfigSecret`, `HasCACertBundle` | Keep both — our conditions are additive. |
| `scripts/sdlc/cfn/codepipeline-s3.yml` (CodeBuild env vars) | Added `DOCKER_CONF`, `PIP_CONF`, `UV_CONF`, `NPM_CONF`, `CA_CERT_BUNDLE_S3_URI` with `Type: SECRETS_MANAGER` conditionals | Keep ours. If upstream adds new env vars, keep both. |
| `scripts/sdlc/cfn/codepipeline-s3.yml` (buildspec install) | Added private registry config-writing guards before standard installs | Keep ours at the start of install phase. If upstream modifies install commands, keep both — ours are independent guards. |
| `scripts/sdlc/cfn/codepipeline-s3.yml` (IAM policies) | Added `CodeBuildSecretsManagerPolicy` and `CodeBuildCACertPolicy` resources | Keep ours — they are standalone resources that don't conflict with upstream policies. |
| `CHANGELOG.md` | Our entries under `[Unreleased]` | Keep both — our entries + upstream's entries, both under `[Unreleased]` or appropriate version. |

## Files we own exclusively (never conflict)

| Path | Purpose |
|------|---------|
| `enterprise/` | All enterprise docs, examples, helper templates |
| `.github/workflows/sync-upstream.yml` | Automated sync workflow |

## Sync procedure

```bash
# 1. Fetch upstream
git fetch upstream develop

# 2. Attempt merge
git merge upstream/develop --no-edit

# 3. If conflicts:
#    - Check which files conflict (usually CHANGELOG + template params)
#    - Follow resolution guidance above
#    - Test: make lint && make test

# 4. After resolving:
git add -A
git commit  # merge commit auto-generated
git push
```

## Conflict resolution rules

1. **CHANGELOG.md** — Always keep both sides. Our entries go under `[Unreleased]`, upstream's released versions stay intact below.

2. **Template parameters** — Our params are additive. If git can't auto-merge because upstream added params near ours, manually include both sets. Our params are grouped together with a comment header: `# ── Air-gapped / private registry parameters ──`

3. **Buildspec install phase** — Our config-writing block is self-contained (wrapped in `if [ -n "${VAR:-}" ]` guards). If upstream modifies the install phase, keep their changes AND our block. Order: upstream's installs first, then our config writes.

4. **Dockerfile FROM lines** — If upstream changes the base image version (e.g., `python:3.12` → `python:3.13`), update our `ARG` defaults to match: `ARG BASE_IMAGE_SUFFIX=arm64` stays, but any version bump should be reflected.

5. **Never resolve by deleting upstream changes** — If unsure, keep both sides and test. A failing build is easier to debug than silently lost functionality.

## Verifying after sync

```bash
# Quick verification
make lint
make test

# Full verification (requires AWS credentials)
idp-cli publish --source-dir . --bucket-basename <bucket> --prefix idp --region us-east-1
# If publish succeeds, the templates and build files are consistent
```

## Common scenarios

### Upstream adds a new parameter to template.yaml
- Auto-merges cleanly 95% of the time (different section)
- If conflict: add their param in their section, keep ours in ours

### Upstream modifies Dockerfile.optimized
- Check what changed (new stage? version bump? new RUN command?)
- Keep our ARGs at the top and secret mounts on the RUN line
- Update defaults if base image version changed

### Upstream adds a new function to buildspec.yml
- Auto-merges cleanly (they add to the function list, our install phase is separate)
- If conflict: keep their function list AND our install phase

### Upstream modifies scripts/sdlc/cfn/codepipeline-s3.yml
- Check what changed (new CodeBuild env var? IAM policy update? buildspec change?)
- Keep our private registry params, conditions, and env var conditionals
- Keep our `CodeBuildSecretsManagerPolicy` and `CodeBuildCACertPolicy` resources
- Keep our buildspec install-phase guards (the `if [ -n "${VAR:-}" ]` blocks)
- If upstream adds new buildspec install commands, place them after our registry setup block

### Upstream releases a new version
- CHANGELOG conflict guaranteed
- Resolution: our `[Unreleased]` entries stay above their new `[x.y.z]` section
