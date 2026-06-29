# IDP Enterprise Extensions

Enterprise deployment features for the GenAI IDP Accelerator. These extend the upstream community version with support for:

- **Private artifact registries** — Pull dependencies from internal JFrog, CodeArtifact, or Nexus instead of public registries
- **Integration REST API** — Programmatic document submission and result retrieval (planned)
- **IAM team separation** — Distinct roles for infra, dev, and API consumers (planned)

## Quick Start

If you don't need enterprise features, deploy exactly as documented in the upstream [Deployment Guide](../docs/deployment.md) — all enterprise parameters are optional and default to off.

### Private Registry Deployment

```bash
# 1. Create secrets with your registry configs (one-time)
aws cloudformation deploy --stack-name IDP-Registry-Secrets \
  --template-file enterprise/registry/secrets-setup.yaml \
  --parameter-overrides \
    PipConfig="$(cat enterprise/registry/examples/jfrog-pip.conf)" \
    UvConfig="$(cat enterprise/registry/examples/jfrog-uv.toml)" \
    NpmConfig="$(cat enterprise/registry/examples/jfrog-npmrc)" \
    DockerConfig="$(cat enterprise/registry/examples/jfrog-docker-config.json)"

# 2. Deploy IDP with registry params
idp-cli deploy --stack-name IDP-PROD \
  --admin-email admin@example.com \
  --parameters "DockerConfigSecretArn=$(aws cloudformation describe-stacks --stack-name IDP-Registry-Secrets --query 'Stacks[0].Outputs[?OutputKey==`DockerConfigSecretArn`].OutputValue' --output text),\
UvConfigSecretArn=$(aws cloudformation describe-stacks --stack-name IDP-Registry-Secrets --query 'Stacks[0].Outputs[?OutputKey==`UvConfigSecretArn`].OutputValue' --output text),\
PipConfigSecretArn=$(aws cloudformation describe-stacks --stack-name IDP-Registry-Secrets --query 'Stacks[0].Outputs[?OutputKey==`PipConfigSecretArn`].OutputValue' --output text),\
NpmConfigSecretArn=$(aws cloudformation describe-stacks --stack-name IDP-Registry-Secrets --query 'Stacks[0].Outputs[?OutputKey==`NpmConfigSecretArn`].OutputValue' --output text),\
UvImage=your-registry.com/docker/uv:0.9.6,\
LambdaBaseImage=your-registry.com/docker/lambda/python"
```

## Staying in Sync with Upstream

This fork syncs weekly from [upstream](https://github.com/aws-solutions-library-samples/accelerated-intelligent-document-processing-on-aws). Enterprise features are additive — core IDP processing (OCR, classification, extraction, evaluation) is unchanged.

See `.github/workflows/sync-upstream.yml` for the automated merge workflow.
