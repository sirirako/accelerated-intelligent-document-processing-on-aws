# Upstream Sync — Conflict Resolution Guide

When syncing this enterprise fork with upstream (`git merge upstream/develop`), use this guide to resolve conflicts and verify nothing broke silently. This guide is designed for both humans and AI coding assistants.

## Our enterprise modifications (what we carry)

### 1. Private registry (`template.yaml`, `Dockerfile.optimized`, `buildspec.yml`)

| File | What we changed |
|------|----------------|
| `template.yaml` (params) | `DockerConfigSecretArn`, `UvConfigSecretArn`, `PipConfigSecretArn`, `NpmConfigSecretArn`, `CACertBundleS3Uri`, `UvImage`, `LambdaBaseImage` |
| `template.yaml` (conditions) | `HasDockerConfigSecret`, `HasUvConfigSecret`, `HasPipConfigSecret`, `HasNpmConfigSecret` |
| `template.yaml` (nested stack pass-through) | Registry params passed to PATTERNSTACK |
| `patterns/unified/template.yaml` | Registry secret params + CodeBuild env vars |
| `patterns/unified/buildspec.yml` | Config file guards in install phase (`if [ -n "${PIP_CONF:-}" ]`) |
| `Dockerfile.optimized` | Parameterized `UV_IMAGE`, `BASE_IMAGE_REGISTRY`, `BASE_IMAGE_SUFFIX` ARGs + secret mounts |
| `nested/multi-doc-discovery/template.yaml` | Same registry pattern |
| `scripts/sdlc/cfn/codepipeline-s3.yml` | Registry params, conditions, env vars, IAM policies |

### 2. Ping API authorizer + completion hook (`template.yaml`, `enterprise/`)

| File | What we changed |
|------|----------------|
| `template.yaml` (params) | `PingIssuer1`, `PingJwksUri1`, `PingIssuer2`, `PingJwksUri2`, `PingRequiredRoles`, `EnableCompletionHook`, `CompletionHookMQ*` params |
| `template.yaml` (conditions) | `DeployCompletionHook` |
| `template.yaml` (conditions) | `ShouldEnablePostProcessingLambdaHook` expanded with `!Or` to include `EnableCompletionHook` |
| `template.yaml` (API Gateway) | `ApiGateway` uses `PingAuthorizer` (Cognito resources removed) |
| `template.yaml` (resources) | `EnterprisePingVerifierLayer`, `EnterprisePikaLayer`, `EnterprisePingAuthorizerFunction`, `EnterpriseCompletionHookFunction` |
| `template.yaml` (decompressor) | `CUSTOM_POST_PROCESSOR_ARN` uses `!If [DeployCompletionHook, ...]` |
| `enterprise/` directory | All enterprise code (auth, hook, layers, docs) — never conflicts |

### 3. Pipeline hooks / feature platform (SFN, config schema, UI)

| File | What we changed |
|------|----------------|
| `patterns/unified/statemachine/workflow.asl.json` | 6 hook states inserted between upstream states |
| `patterns/unified/template.yaml` | `postHook` schema fields, `PipelineHooksDispatcherLambdaArn` in `DefinitionSubstitutions` |
| `src/ui/src/routes/AuthRoutes.tsx` | `settingsLoaded` wrapper, `/features/*` route |
| `src/ui/src/components/genaiidp-layout/navigation.tsx` | Dynamic features navigation section |

### 4. Per-job configurationVersion (`src/lambda/api_handler/`, `src/lambda/batch_pre_processor/`)

| File | What we changed |
|------|----------------|
| `src/lambda/api_handler/models.py` | `configurationVersion` field on `PostJobRequest` + `GetJobResponse` |
| `src/lambda/api_handler/index.py` | Presigned POST metadata + job record storage + GET response |
| `src/lambda/batch_pre_processor/index.py` | Reads `ConfigurationVersion` from job record, propagates as S3 metadata |
| `lib/idp_common_pkg/idp_common/dynamodb/job_service.py` | `configuration_version` parameter on `create_job_record` |

---

## Conflict resolution rules

### General principles

1. **Keep both sides** for additive changes (parameters, conditions, resources)
2. **Enterprise params stay grouped** under comment markers
3. **Never delete enterprise resources** — if unsure, keep and flag
4. **Never resolve by deleting upstream changes** — keep both and test
5. **A failing build is easier to debug than silently lost functionality**

### By file

#### `template.yaml`

| Section | Resolution |
|---|---|
| Parameters (ours are between `# === Enterprise Integration ===` markers) | Keep both — order doesn't matter |
| Conditions (`DeployCompletionHook`) | Keep ours alongside upstream's |
| `ShouldEnablePostProcessingLambdaHook` | Keep our `!Or` wrapper; put upstream's logic as the first branch |
| API Gateway (Jobs API) | Ours uses `PingAuthorizer` only (no Cognito). If upstream changes the Jobs API structure, adapt our Ping authorizer reference to the new structure |
| Decompressor `CUSTOM_POST_PROCESSOR_ARN` | Keep our `!If [DeployCompletionHook, ...]`; put upstream's value in the false branch |
| Enterprise Resources block | Ours — upstream won't touch it. If conflict appears here, investigate |
| Registry params/conditions/pass-throughs | Additive — keep both sets |

#### `Dockerfile.optimized`

- Keep our `ARG` lines at the top and `--mount=type=secret` on RUN
- If upstream changes the base image version, update our ARG defaults to match
- If upstream adds new stages, ensure our ARGs are accessible in the new stages

#### `patterns/unified/buildspec.yml`

- Our config-writing block is self-contained (`if [ -n "${VAR:-}" ]` guards)
- Keep upstream's install commands AND our block
- Order: upstream's installs first, then our config writes

#### `patterns/unified/statemachine/workflow.asl.json` (HIGH RISK)

This is the most dangerous file. Upstream can silently break our hooks even without a git conflict.

**What breaks (no git conflict):**

| Upstream action | What breaks |
|---|---|
| Rename a state | Hook's `"Next"` points to nonexistent state → SFN validation fails |
| Add a state between two existing ones | New state skips the hook → hook never fires (silent) |
| Remove a state a hook targets | Hook's `"Next"` invalid → SFN validation fails |
| Change state output path | Hook receives wrong payload → may silently no-op |

**After every merge, re-apply hooks if needed:**

Each hook state:
1. Changes the preceding state's `"Next"` to point to the hook
2. Sets its own `"Next"` to the following state
3. Has `"Catch"` fallback that skips to the following state on error

#### `src/lambda/api_handler/` and `batch_pre_processor/`

- Our changes are small (one field + metadata propagation)
- If upstream refactors these handlers, re-apply the `configurationVersion` logic

---

## Sync workflow

```bash
# 1. Fetch upstream
git fetch upstream develop

# 2. Merge
git merge upstream/develop

# 3. Resolve conflicts using the rules above

# 4. Run silent-breakage checks (next section)

# 5. Validate
make lint
make test
./enterprise/build.sh
sam build --template-file template.yaml
```

---

## Silent-breakage checks (run even when merge is clean)

### SFN chain integrity

```bash
python3 -c "
import json
with open('patterns/unified/statemachine/workflow.asl.json') as f:
    asl = json.load(f)

def check_states(states, path=''):
    for name, state in states.items():
        nxt = state.get('Next')
        if nxt and nxt not in states:
            print(f'BROKEN: {path}{name} -> Next: {nxt} (not found)')
        for c in state.get('Catch', []):
            if c.get('Next') and c['Next'] not in states:
                print(f'BROKEN: {path}{name} -> Catch Next: {c[\"Next\"]} (not found)')
        iterator = state.get('Iterator', {}).get('States')
        if iterator:
            check_states(iterator, path=f'{path}{name}/')
        for branch in state.get('Branches', []):
            check_states(branch.get('States', {}), path=f'{path}{name}/')

check_states(asl['States'])
print('SFN chain check complete.')
"
```

### Hook dispatch wiring

```bash
# Verify all 6 hook states exist
grep -c "PipelineHooksDispatcherLambdaArn" patterns/unified/statemachine/workflow.asl.json
# Expected: 6

# Verify hook points
grep "hookPoint" patterns/unified/statemachine/workflow.asl.json
# Expected: postOcr, postClassification, postExtraction, postAssessment, postRuleValidation, postSummarization
```

### Enterprise template markers

```bash
# Verify enterprise params exist
grep -n "Enterprise Integration" template.yaml

# Verify conditions
grep -n "DeployCompletionHook" template.yaml

# Verify completion hook wiring
grep -n "EnterpriseCompletionHookFunction" template.yaml

# Verify Ping authorizer
grep -n "EnterprisePingAuthorizerFunction" template.yaml

# Verify registry params
grep -n "DockerConfigSecretArn\|UvConfigSecretArn\|PipConfigSecretArn" template.yaml
```

### Config schema alignment

```bash
# Verify postHook appears under each step
grep -c "postHook" patterns/unified/template.yaml
# Expected: 6

# Verify step keys match dispatcher
grep "HOOK_TO_STEP" patterns/unified/src/pipeline_hooks_function/index.py
```

### UI feature platform

```bash
grep "FEATURES_PATH_PREFIX" src/ui/src/routes/AuthRoutes.tsx
grep "FeaturesRoutes" src/ui/src/routes/AuthRoutes.tsx
```

### YAML validity

```bash
python3 -c "
import yaml
yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None)
yaml.safe_load(open('template.yaml'))
print('YAML valid')
"
```

---

## Post-merge checklist

- [ ] YAML parses without errors
- [ ] Enterprise parameters block intact (between markers)
- [ ] `DeployCompletionHook` condition exists
- [ ] `ShouldEnablePostProcessingLambdaHook` has our `!Or` wrapper
- [ ] API Gateway uses `PingAuthorizer` (Jobs API section)
- [ ] Decompressor `CUSTOM_POST_PROCESSOR_ARN` has `!If [DeployCompletionHook, ...]`
- [ ] Enterprise Resources section exists (2 layers + 2 functions)
- [ ] SFN chain integrity script passes (no BROKEN lines)
- [ ] All 6 hook states present with correct hookPoint names
- [ ] Registry params/conditions exist in template + nested stacks
- [ ] Dockerfile ARGs present and defaults match upstream's base image version
- [ ] Buildspec install-phase guards present
- [ ] **CRITICAL: `patterns/unified/buildspec.yml` has NO `docker buildx create` or `moby/buildkit`** (air-gapped customer can't pull from Docker Hub — use default builder)
- [ ] **CRITICAL: buildspec has NO `INSTALL_GIT=true`** (dnf install reaches cdn.amazonlinux.com — blocked in air-gapped)
- [ ] Buildspec uses `docker --config /root/.config/docker` on ALL docker commands (ECR login + buildx build)
- [ ] Buildspec has `BASE_IMAGE_ARGS` logic (checks `LAMBDA_BASE_IMAGE` for full image:tag vs registry prefix)
- [ ] Buildspec has `SECRET_ARGS` for `--secret id=pipconf,cacert,uvconf` mounts
- [ ] Buildspec env var is `CA_CERT_S3_URI` (not `CA_CERT_BUNDLE_S3_URI`)
- [ ] `patterns/unified/template.yaml` DockerBuildProject has env vars: `LAMBDA_BASE_IMAGE`, `DOCKER_CONF`, `PIP_CONF`, `UV_CONF`, `CA_CERT_S3_URI`
- [ ] `patterns/unified/template.yaml` DockerBuildRole has S3 access to CA cert bucket (not just ArtifactPrefix)
- [ ] `patterns/unified/template.yaml` has registry params: `DockerConfigSecretArn`, `UvConfigSecretArn`, `PipConfigSecretArn`, `LambdaBaseImage`, `CACertBundleS3Uri`
- [ ] `nested/multi-doc-discovery/template.yaml` buildspec unchanged (docker --config, LAMBDA_BASE_IMAGE, secret mounts)
- [ ] `Dockerfile.optimized` unchanged (ARG BASE_IMAGE, secret mounts for pip/uv/cacert, uv installed via pip)
- [ ] `configurationVersion` field still in api_handler models
- [ ] `make lint` passes
- [ ] `make test` passes
- [ ] `./enterprise/build.sh` succeeds
- [ ] **root `VERSION` updated to the new upstream version** (this is upstream's clock)
- [ ] **`enterprise/VERSION` base rolled to the new upstream version and counter reset to 1** (e.g. `0.6.1-ent.N` → `0.6.2-ent.1`). The base is bumped here; the counter increments on later enterprise builds. See `release.md`.

### Build project verification commands

```bash
# PATTERNSTACK buildspec — must NOT have multiarch builder
grep "docker buildx create\|moby/buildkit" patterns/unified/buildspec.yml && echo "❌ REMOVE multiarch builder" || echo "✅ No multiarch"

# PATTERNSTACK buildspec — must have docker --config
grep -c "docker --config /root/.config/docker" patterns/unified/buildspec.yml | xargs -I{} test {} -ge 2 && echo "✅ docker --config present" || echo "❌ MISSING docker --config"

# PATTERNSTACK buildspec — must have BASE_IMAGE_ARGS
grep -q "LAMBDA_BASE_IMAGE" patterns/unified/buildspec.yml && echo "✅ BASE_IMAGE_ARGS present" || echo "❌ MISSING BASE_IMAGE_ARGS"

# PATTERNSTACK template — must have LAMBDA_BASE_IMAGE env var
grep -q "Name: LAMBDA_BASE_IMAGE" patterns/unified/template.yaml && echo "✅ LAMBDA_BASE_IMAGE env var" || echo "❌ MISSING LAMBDA_BASE_IMAGE env var"

# PATTERNSTACK template — must have CA cert S3 IAM
grep -q "HasCACertBundle" patterns/unified/template.yaml && grep -A3 "HasCACertBundle" patterns/unified/template.yaml | grep -q "s3:GetObject" && echo "✅ CA cert S3 IAM" || echo "❌ MISSING CA cert S3 access"

# Multi-doc-discovery — must be unchanged (docker --config, LAMBDA_BASE_IMAGE)
grep -q "docker --config /root/.config/docker" nested/multi-doc-discovery/template.yaml && echo "✅ multi-doc docker --config" || echo "❌ MISSING"
grep -q "LAMBDA_BASE_IMAGE" nested/multi-doc-discovery/template.yaml && echo "✅ multi-doc LAMBDA_BASE_IMAGE" || echo "❌ MISSING"

# Dockerfile — must have secret mounts and BASE_IMAGE ARG
grep -q "ARG BASE_IMAGE=" Dockerfile.optimized && echo "✅ Dockerfile BASE_IMAGE ARG" || echo "❌ MISSING"
grep -q "mount=type=secret" Dockerfile.optimized && echo "✅ Dockerfile secret mounts" || echo "❌ MISSING"
```

---

## When to escalate (don't auto-resolve)

Stop and ask a human if:

- Upstream **removed** `PostProcessingLambdaHookFunctionArn` parameter
- Upstream **restructured the SFN into parallel branches** (hooks assume sequential)
- Upstream **replaced the Jobs API Gateway entirely** (our authorizer reference breaks)
- Upstream **renamed or removed** step keys (`ocr`, `classification`, `extraction`, `assessment`, `rule_validation`, `summarization`)
- Upstream **changed the EventBridge rule pattern** for Step Functions completion
- Upstream **changed the `create_job_record` signature** in `job_service.py`
- Enterprise tests fail with errors you can't trace to a simple rename
- After a clean merge, `sam build` fails on enterprise resources

---

## AI assistant prompt template

```
I just merged upstream develop into enterprise/develop. There were
[no conflicts / conflicts in X, Y, Z]. Please:
1. Run the silent-breakage checks from enterprise/docs/upstream-sync-guide.md
2. Verify all enterprise functionality is intact (Ping auth, completion hook,
   pipeline hooks, registry, configurationVersion)
3. Report any issues found
```
