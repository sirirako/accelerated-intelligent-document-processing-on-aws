# 2026-07-21: Pipeline Fixes for Customer Deploy

## What was done
- Fixed `chmod +x enterprise/build.sh` (zip strips execute bit)
- Added `--no-lint` to idp-cli publish (Node 18 in CodeBuild, v0.6.1 needs 22)
- Created enterprise-owned deployment script (`enterprise/sdlc/codebuild_deployment.py`)
- Removed `docker buildx create --driver docker-container` (pulls moby/buildkit)
- Removed `INSTALL_GIT=true` (dnf reaches cdn.amazonlinux.com)
- Restored `LAMBDA_BASE_IMAGE` env var + BASE_IMAGE_ARGS in buildspec
- Restored `docker --config /root/.config/docker` on docker commands
- Added DockerBuildRole S3 access to CA cert bucket
- Aligned env var to `CA_CERT_S3_URI` everywhere
- Fixed VPC endpoint URL format for private API (`HttpApiEndpoint` output)

## Errors encountered (all at customer)
1. `Permission denied: ./enterprise/build.sh` — zip strips execute bit
2. `npm ci` fails Node engine check — v0.6.1 requires Node 22
3. `moby/buildkit` pull denied — air-gapped, no Docker Hub
4. `dnf install git` fails — cdn.amazonlinux.com blocked by TLS inspection
5. `public.ecr.aws/lambda/python:3.12-x86_64` 403 — air-gapped, needs LAMBDA_BASE_IMAGE
6. `CA_CERT_S3_URI` 403 from DockerBuildRole — only had ArtifactPrefix access
7. Browser DNS error — API URL using standard domain, not VPC endpoint format
8. Pipeline template orphan resources — hardcoded names don't clean up on stack delete
9. `uuid@11.1.1` not in JFrog — new transitive dep, customer changed to uuid@14.0.0
10. BDA SSL cert error — needed bedrock-data-automation VPC endpoint

## Lessons learned
- NEVER trust test account results for air-gapped compatibility
- The same mistakes (buildx, INSTALL_GIT) were made 3 times because merge took upstream
- Enterprise deployment script eliminates merge conflicts on the 3700-line upstream file
- `patterns/unified/buildspec.yml` and template are NOT pure upstream — they have enterprise additions

## Published
- Multiple commits pushed to origin/enterprise/develop
- Customer received release zip, pipeline deployed successfully after all fixes
