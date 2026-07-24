# Merge Rules

Rules for merging upstream into `enterprise/develop`. See also
`enterprise/.ai/skills/upstream-sync.md` for the full checklist.

## Classification of files

| Category | Files | Merge approach |
|----------|-------|----------------|
| Pure upstream (application) | `patterns/unified/template.yaml` (schema/logic), `src/lambda/*`, `src/ui/*`, `nested/api-resolvers/*` | Take upstream entirely |
| Upstream + enterprise additions | `template.yaml`, `patterns/unified/buildspec.yml`, `patterns/unified/template.yaml` (params/IAM/env), `scripts/sdlc/cfn/codepipeline-s3.yml`, `nested/multi-doc-discovery/template.yaml`, `Dockerfile.optimized` | Take upstream, re-apply enterprise additions |
| Enterprise-owned | `enterprise/*`, `enterprise/sdlc/codebuild_deployment.py` | Ours — never overwritten by upstream |
| Upstream-owned (don't touch) | `scripts/sdlc/codebuild_deployment.py` | Upstream's — our enterprise script overrides it at runtime |

## CRITICAL: Re-apply after every merge

These enterprise additions get lost when taking upstream's version. ALWAYS verify:

### `patterns/unified/buildspec.yml`
- Install phase (CA cert, Docker, pip, uv config from env vars)
- NO `docker buildx create --driver docker-container`
- NO `INSTALL_GIT=true`
- `docker --config /root/.config/docker` on all docker commands
- `SECRET_ARGS` block + `${SECRET_ARGS}` on docker build command
- `BASE_IMAGE_ARGS` logic with `LAMBDA_BASE_IMAGE` support

### `patterns/unified/template.yaml`
- Registry params: DockerConfigSecretArn, UvConfigSecretArn, PipConfigSecretArn, UvImage, LambdaBaseImage, CACertBundleS3Uri
- Conditions: HasDockerConfigSecret, HasUvConfigSecret, HasPipConfigSecret, HasCACertBundle
- DockerBuildProject env vars: DOCKER_CONF, PIP_CONF, UV_CONF, CA_CERT_S3_URI, LAMBDA_BASE_IMAGE
- DockerBuildRole IAM: secretsmanager:GetSecretValue on registry secrets, s3:GetObject on CA cert bucket

### `scripts/sdlc/cfn/codepipeline-s3.yml`
- Registry params + conditions
- CodeBuildPermissionsBoundaryArn
- PipelineConfigKey, NodeDistUrl
- Enterprise build.sh chmod + execution in install phase
- Enterprise deployment script fallback in build phase

### `Dockerfile.optimized`
- ARG BASE_IMAGE (full image:tag support)
- `--mount=type=secret` for pip/uv/cacert
- uv installed via pip (not ghcr.io image)

### `nested/multi-doc-discovery/template.yaml`
- Registry params, conditions
- docker --config in buildspec
- LAMBDA_BASE_IMAGE in Dockerfile template
- Secret mounts in docker build

## Verification commands

Run these after EVERY merge (copy-paste):

```bash
# Buildspec — no external pulls
grep "docker buildx create\|moby/buildkit" patterns/unified/buildspec.yml && echo "❌ REMOVE" || echo "✅ No multiarch"
grep "INSTALL_GIT=true" patterns/unified/buildspec.yml && echo "❌ REMOVE" || echo "✅ No INSTALL_GIT"

# Buildspec — enterprise additions present
grep -c "docker --config /root/.config/docker" patterns/unified/buildspec.yml | xargs -I{} test {} -ge 2 && echo "✅ docker --config" || echo "❌ MISSING"
grep -q "LAMBDA_BASE_IMAGE" patterns/unified/buildspec.yml && echo "✅ BASE_IMAGE_ARGS" || echo "❌ MISSING"
grep -q "SECRET_ARGS" patterns/unified/buildspec.yml && echo "✅ SECRET_ARGS" || echo "❌ MISSING"

# Template — env vars and IAM
grep -q "Name: LAMBDA_BASE_IMAGE" patterns/unified/template.yaml && echo "✅ env var" || echo "❌ MISSING"
grep -q "Name: CA_CERT_S3_URI" patterns/unified/template.yaml && echo "✅ CA cert env" || echo "❌ MISSING"
grep -q "secretsmanager:GetSecretValue" patterns/unified/template.yaml && echo "✅ secrets IAM" || echo "❌ MISSING"

# Dockerfile
grep -q "ARG BASE_IMAGE=" Dockerfile.optimized && echo "✅ BASE_IMAGE ARG" || echo "❌ MISSING"
grep -q "mount=type=secret" Dockerfile.optimized && echo "✅ secret mounts" || echo "❌ MISSING"

# Multi-doc-discovery
grep -q "docker --config" nested/multi-doc-discovery/template.yaml && echo "✅ multi-doc docker --config" || echo "❌ MISSING"
grep -q "LAMBDA_BASE_IMAGE" nested/multi-doc-discovery/template.yaml && echo "✅ multi-doc base image" || echo "❌ MISSING"
```
