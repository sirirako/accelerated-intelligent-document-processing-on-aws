# Plan: CodeBuild Pipeline with Internal Artifact Repository Support

## Context

Customer has a Bitbucket repo, no Bitbucket Pipelines. They handle zipping code and uploading to S3 themselves. We need to make the AWS-side pipeline (CodeBuild) work with their internal JFrog Artifactory — pulling npm, pip, and Docker base images from JFrog instead of public internet.

## Scope

Starting from: code.zip lands in S3
Ending at: IDP stack deployed/updated

## What CodeBuild needs to do

1. **Get credentials** — authenticate to JFrog (npm + pip + docker)
2. **Publish** — `idp-cli publish` (builds templates, Lambda layers, Docker images)
   - `npm ci` → pulls from internal npm registry
   - `pip install` / `uv pip install` → pulls from internal PyPI registry
   - `docker build` → pulls base image from internal Docker registry
3. **Deploy** — `idp-cli deploy` (creates/updates CloudFormation stack)

## Parameters to add

| Parameter | Purpose | Example |
|-----------|---------|---------|
| `NpmRegistryUrl` | Internal npm registry | `https://jfrog.company.com/artifactory/api/npm/npm-virtual/` |
| `PipIndexUrl` | Internal PyPI registry | `https://jfrog.company.com/artifactory/api/pypi/pypi-virtual/simple` |
| `DockerRegistryUrl` | Internal Docker registry for base images | `jfrog.company.com/docker-virtual` |
| `JfrogCredentialArn` | Secrets Manager ARN with JFrog username/token | `arn:aws:secretsmanager:...:secret:jfrog-creds` |

## Changes needed

### 1. Pipeline template (`scripts/sdlc/cfn/codepipeline-s3.yml`)
- Add parameters: `NpmRegistryUrl`, `PipIndexUrl`, `DockerRegistryUrl`, `JfrogCredentialArn`
- Pass them as CodeBuild environment variables
- Add Secrets Manager read permission to CodeBuild role

### 2. Buildspec (pre-build phase)
```bash
# Get JFrog credentials from Secrets Manager
CREDS=$(aws secretsmanager get-secret-value --secret-id $JFROG_CREDENTIAL_ARN --query SecretString --output text)
JFROG_USER=$(echo $CREDS | jq -r .username)
JFROG_TOKEN=$(echo $CREDS | jq -r .token)

# Configure npm
echo "registry=${NPM_REGISTRY_URL}" > .npmrc
echo "//${NPM_REGISTRY_URL#https://}:_authToken=${JFROG_TOKEN}" >> .npmrc

# Configure pip/uv
export UV_INDEX_URL="${PIP_INDEX_URL}"
export UV_EXTRA_INDEX_URL=""  # block fallback to public PyPI

# Docker login to internal registry
echo $JFROG_TOKEN | docker login $DOCKER_REGISTRY_URL -u $JFROG_USER --password-stdin
```

### 3. Dockerfile.optimized
- Accept `BASE_IMAGE_REGISTRY` build arg to override `public.ecr.aws`
- `FROM ${BASE_IMAGE_REGISTRY}/lambda/python:3.12-${BASE_IMAGE_SUFFIX}`

### 4. Unified pattern buildspec (`patterns/unified/buildspec.yml`)
- Pass `--build-arg BASE_IMAGE_REGISTRY=$DOCKER_REGISTRY_URL` in docker build

### 5. Main template (`template.yaml`)
- Add `NpmRegistryUrl`, `PipIndexUrl`, `DockerRegistryUrl` parameters
- Pass to PATTERNSTACK as CodeBuild env vars (for the nested Docker build)

## Flow

```
S3: code.zip uploaded (by customer)
  │
  ▼
CodePipeline triggered
  │
  ▼
CodeBuild pre_build:
  - Read JFrog creds from Secrets Manager
  - Configure .npmrc → internal npm
  - Configure UV_INDEX_URL → internal PyPI
  - docker login → internal Docker registry
  │
  ▼
CodeBuild build (idp-cli publish):
  - npm ci → JFrog npm
  - uv pip install → JFrog PyPI
  - Artifacts → S3
  │
  ▼
CodeBuild build (idp-cli deploy):
  - CloudFormation create/update
  - Nested CodeBuild (Docker images) → JFrog Docker for base images
  │
  ▼
Stack deployed ✅
```

## Open questions for customer

1. How are JFrog credentials stored? (Secrets Manager? SSM? IAM role-based?)
2. Is the JFrog base image path mirrored from public ECR? (e.g., `jfrog.company.com/lambda/python:3.12-arm64`)
3. Does JFrog need auth for reads, or open within VPC?
4. Deploy automatically after publish, or publish-only (deploy via CloudFormation console)?

## Dependencies

- Requires: `feature/codebuild-vpc-support` merged (CodeBuild must be in VPC to reach JFrog)
- Requires: `feature/lambda-architecture-param` merged (customer needs x86_64 if JFrog only has AMD64 images)
