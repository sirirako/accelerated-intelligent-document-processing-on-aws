# Constraints (Air-Gapped / Customer Environment)

Things that are BLOCKED or MUST NOT be done. Violating these causes deploy failures.

## Network — what's unreachable

| Endpoint | Why blocked | What breaks |
|----------|-------------|-------------|
| Docker Hub (`moby/buildkit`) | Air-gapped | `docker buildx create --driver docker-container` |
| `ghcr.io` (uv image) | Air-gapped | `FROM ghcr.io/astral-sh/uv` |
| `cdn.sheetjs.com` | Air-gapped | xlsx tarball download in npm install |
| `public.ecr.aws` | Air-gapped | Lambda base image pull |
| `cdn.amazonlinux.com` | TLS inspection | `dnf install git` (or any dnf package) |
| `registry.npmjs.org` | Air-gapped | npm packages not in JFrog |
| `pypi.org` | Air-gapped | pip/uv packages not in JFrog |
| `nodejs.org` | Air-gapped | Node.js binary download (`n 22.14.0`) |

## Buildspec — NEVER include

These will pass in our test account but FAIL at customer:

1. `docker buildx create --use --driver docker-container` — pulls moby/buildkit
2. `INSTALL_GIT=true` — runs `dnf install git` which reaches cdn.amazonlinux.com
3. `n 22.14.0` or any Node.js download — uses nodejs.org
4. `npm install -g npm@11` — may reach registry.npmjs.org

## Buildspec — MUST include

1. Install phase: CA cert, Docker config, pip config, uv config from env vars
2. `docker --config /root/.config/docker` on ALL docker commands
3. `BASE_IMAGE_ARGS` with `LAMBDA_BASE_IMAGE` support (full image:tag from internal registry)
4. `SECRET_ARGS` for `--secret id=pipconf,cacert,uvconf` mounts
5. Env var `CA_CERT_S3_URI` (not `CA_CERT_BUNDLE_S3_URI`)

## Template — PATTERNSTACK requirements

- `LAMBDA_BASE_IMAGE` env var on DockerBuildProject
- `DOCKER_CONF`, `PIP_CONF`, `UV_CONF` env vars (SECRETS_MANAGER type)
- `CA_CERT_S3_URI` env var
- DockerBuildRole: S3 access to CA cert bucket (not just ArtifactPrefix)
- DockerBuildRole: secretsmanager:GetSecretValue on registry secrets
- Registry params: DockerConfigSecretArn, UvConfigSecretArn, PipConfigSecretArn, LambdaBaseImage, CACertBundleS3Uri

## Customer infrastructure

- `LambdaArchitecture=x86_64` (native builds, no cross-compilation)
- VPC endpoint required for private API access (vpce-id format URL)
- TLS inspection on outbound traffic (requires CA cert injection)
- Permissions boundary on all IAM roles (`EnterprisePermissionsBoundary`)
- Bedrock deny on `anthropic.*` models — must use Amazon Nova
- `WebUIHosting=APIGateway` (ALB removed in v0.6.1)
- `CreateTestVpc=false` on pipeline (no NAT Gateway, no VPC quota usage)

## Pipeline template — hardcoded names that orphan on delete

If redeploying pipeline with same PipelineName after a failed delete, manually remove:
- CodeBuild project: `app-sdlc`
- CodePipeline: `{PipelineName}`
- KMS alias: `alias/{PipelineName}-key`
- IAM role: `genaiic-sdlc-pipeline-trigger-role`
- EventBridge rule: `genaiic-sdlc-pipeline-trigger`
- SNS topic: `{PipelineName}-failures`

## JFrog (customer's private registry)

- Remote npm repo may 404 on newer packages — admin must "Zap Caches" or wait for TTL
- First-time fetches trigger Xray scanning (can timeout) — retry after a few hours
- 401 errors: token may only access local repos, not remote
- `xlsx` is NOT on npm registry — must be manually uploaded as tarball
- Python warming must run on Linux for correct manylinux wheels
