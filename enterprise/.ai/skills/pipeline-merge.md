# Skill: Pipeline Template Merge

## When to use
When merging upstream changes that touch `scripts/sdlc/cfn/codepipeline-s3.yml`.

## Key principle
The pipeline template is shared — upstream's file plus our enterprise additions.
Conflicts are additive (keep both sides). Never take only upstream's version.

## Our enterprise additions (must survive every merge)

### Parameters (keep between our markers or at end of Parameters section)
- `DockerConfigSecretArn`, `UvConfigSecretArn`, `PipConfigSecretArn`, `NpmConfigSecretArn`
- `CACertBundleS3Uri`
- `PipelineConfigKey` (default: `deploy/pipeline-config.yaml`)
- `NodeDistUrl`
- `CodeBuildPermissionsBoundaryArn`

### Conditions
- `HasDockerConfigSecret`, `HasUvConfigSecret`, `HasPipConfigSecret`, `HasNpmConfigSecret`
- `HasCACertBundle`, `HasCodeBuildPermissionsBoundary`, `HasNodeDistUrl`
- `HasAnyRegistrySecret` (OR of all four registry secrets)

### IAM (CodeBuild role)
- `PermissionsBoundary: !If [HasCodeBuildPermissionsBoundary, ...]` on both roles
- Wider IAM resource scopes (`arn:...:role/*` not `arn:...:role/idp-*`) for customer environment

### CodeBuild environment variables
- `PIPELINE_CONFIG_KEY`
- `CA_CERT_BUNDLE_S3_URI` (conditional)
- `DOCKER_CONF`, `PIP_CONF`, `UV_CONF`, `NPM_CONF` (type: SECRETS_MANAGER, conditional)
- `NODE_DIST_URL` (conditional)

### Buildspec install phase
- `chmod +x ./enterprise/build.sh` before running it
- Enterprise layers build (`./enterprise/build.sh`)
- `LAMBDA_ARCHITECTURE` read from pipeline config

### Buildspec build phase
- Enterprise script fallback:
  ```yaml
  if [ -f "enterprise/sdlc/codebuild_deployment.py" ]; then
      python3 enterprise/sdlc/codebuild_deployment.py
  else
      python3 scripts/sdlc/codebuild_deployment.py
  fi
  ```

## What NOT to keep (upstream-only CI features)
- `CreateTestVpc` / `TestVpcCidr` — upstream's params, keep them (default true for upstream CI)
- `FailureNotificationEmail` — upstream's param, keep it
- Test VPC resources — gated by condition, no harm keeping them
- Customer sets `CreateTestVpc=false` at deploy time

## Merge checklist
After resolving conflicts, verify:
```bash
# Enterprise params exist
grep -q "DockerConfigSecretArn" scripts/sdlc/cfn/codepipeline-s3.yml
grep -q "PipelineConfigKey" scripts/sdlc/cfn/codepipeline-s3.yml
grep -q "CodeBuildPermissionsBoundaryArn" scripts/sdlc/cfn/codepipeline-s3.yml

# Enterprise conditions exist
grep -q "HasDockerConfigSecret" scripts/sdlc/cfn/codepipeline-s3.yml
grep -q "HasCodeBuildPermissionsBoundary" scripts/sdlc/cfn/codepipeline-s3.yml

# Buildspec has enterprise logic
grep -q "chmod.*enterprise/build.sh" scripts/sdlc/cfn/codepipeline-s3.yml
grep -q "enterprise/sdlc/codebuild_deployment.py" scripts/sdlc/cfn/codepipeline-s3.yml

# YAML valid
python3 -c "import yaml; yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None); yaml.safe_load(open('scripts/sdlc/cfn/codepipeline-s3.yml')); print('✅ valid')"
```

## Known issues with this template
- **Hardcoded resource names** that orphan on stack delete:
  - CodeBuild project: `app-sdlc`
  - CodePipeline: `{PipelineName}` param value
  - KMS alias: `alias/{PipelineName}-key`
  - IAM role: `genaiic-sdlc-pipeline-trigger-role`
  - EventBridge rule: `genaiic-sdlc-pipeline-trigger`
  - SNS topic: `{PipelineName}-failures`
- If redeploying with same PipelineName after a failed delete, manually remove these first
- `CreateTestVpc=false` required at customer (no NAT Gateway cost, no VPC quota issues)

## Deployment script is NOT merged
`scripts/sdlc/codebuild_deployment.py` is upstream's file — do NOT add enterprise changes
to it. Our enterprise logic lives in `enterprise/sdlc/codebuild_deployment.py` which is
used automatically when present in the code zip.
