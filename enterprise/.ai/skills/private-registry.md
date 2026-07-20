# Private Registry Setup

Configure the IDP build pipeline to pull all dependencies from your internal artifact repository instead of public registries.

## Prerequisites

- AWS Secrets Manager secrets containing registry config files
- (Optional) CA certificate bundle in S3 for corporate TLS
- CodeBuild must be in VPC with network access to your internal registry (`DeployInVPC=true`)

## Step 1: Create Secrets

Store your registry configuration files in Secrets Manager. Each secret contains the full config file content.

### Docker Registry (for base images)

```bash
aws secretsmanager create-secret \
  --name idp/registry/docker \
  --secret-string '{
  "auths": {
    "your-registry.company.com": {
      "auth": "BASE64_ENCODED_USER:TOKEN"
    }
  }
}'
```

### pip.conf (Python packages)

```bash
aws secretsmanager create-secret \
  --name idp/registry/pip \
  --secret-string '[global]
index-url = https://your-registry.company.com/artifactory/api/pypi/pypi-virtual/simple
trusted-host = your-registry.company.com'
```

### uv.toml (Python packages — used by Dockerfile.optimized)

```bash
aws secretsmanager create-secret \
  --name idp/registry/uv \
  --secret-string 'index-url = "https://your-registry.company.com/artifactory/api/pypi/pypi-virtual/simple"'
```

### .npmrc (Node packages — WebUI build)

```bash
aws secretsmanager create-secret \
  --name idp/registry/npm \
  --secret-string 'registry=https://your-registry.company.com/artifactory/api/npm/npm-virtual/
//your-registry.company.com/artifactory/api/npm/npm-virtual/:_authToken=YOUR_TOKEN'
```

## Step 2: Upload CA Certificate (if needed)

If your internal registry uses a corporate CA certificate not trusted by default:

```bash
# Create a tar.gz with your CA cert(s)
tar czf ca-bundle.tar.gz -C /path/to/certs .

# Upload to S3
aws s3 cp ca-bundle.tar.gz s3://your-bucket/certs/ca-bundle.tar.gz
```

## Step 3: Deploy with Registry Parameters

```bash
idp-cli deploy \
  --stack-name IDP-PRIVATE \
  --admin-email admin@example.com \
  --region us-east-1 \
  --wait \
  --parameters "DeployInVPC=true,\
VpcId=vpc-xxx,\
PrivateSubnetIds=subnet-a,subnet-b,\
LambdaSecurityGroupId=sg-xxx,\
DockerConfigSecretArn=arn:aws:secretsmanager:us-east-1:123456789012:secret:idp/registry/docker-AbCdEf,\
UvConfigSecretArn=arn:aws:secretsmanager:us-east-1:123456789012:secret:idp/registry/uv-GhIjKl,\
PipConfigSecretArn=arn:aws:secretsmanager:us-east-1:123456789012:secret:idp/registry/pip-MnOpQr,\
NpmConfigSecretArn=arn:aws:secretsmanager:us-east-1:123456789012:secret:idp/registry/npm-StUvWx,\
UvImage=your-registry.company.com/docker/astral-sh/uv:0.9.6,\
LambdaBaseImage=your-registry.company.com/docker/lambda/python,\
CACertBundleS3Uri=s3://your-bucket/certs/ca-bundle.tar.gz"
```

## What Happens During Build

1. **Install phase** — CodeBuild downloads CA cert from S3, installs to OS trust store, writes config files from Secrets Manager env vars
2. **Pre-build** — Docker login using config.json (authenticates to internal registry)
3. **Build** — Docker pulls base images from internal registry, pip/uv install uses internal PyPI via `--secret` mounts
4. **Post-build** — Images pushed to ECR (within the same account)

## Parameters Reference

| Parameter | Required | Description |
|-----------|----------|-------------|
| `DockerConfigSecretArn` | For Docker pulls | Secrets Manager ARN for Docker config.json |
| `UvConfigSecretArn` | For unified pattern builds | Secrets Manager ARN for uv.toml |
| `PipConfigSecretArn` | For multi-doc-discovery builds | Secrets Manager ARN for pip.conf |
| `NpmConfigSecretArn` | For WebUI builds | Secrets Manager ARN for .npmrc |
| `UvImage` | If ghcr.io blocked | Internal mirror of `ghcr.io/astral-sh/uv:0.9.6` |
| `LambdaBaseImage` | If public ECR blocked | Internal mirror of `public.ecr.aws/lambda/python` |
| `CACertBundleS3Uri` | If internal registry uses corporate CA | S3 URI of CA cert bundle (tar.gz) |

## Troubleshooting

| Issue | Resolution |
|-------|-----------|
| CodeBuild fails: `unauthorized` on docker pull | Check `DockerConfigSecretArn` is set and the secret contains valid auth for your registry |
| CodeBuild fails: `Could not find a version that satisfies` | Check `PipConfigSecretArn`/`UvConfigSecretArn` — pip.conf must point to your internal PyPI with the packages pre-mirrored |
| CodeBuild fails: `certificate verify failed` | Set `CACertBundleS3Uri` — your internal registry's TLS cert isn't trusted by the default OS trust store |
| CodeBuild fails: `SECRETS_MANAGER error` | Check that the CodeBuild IAM role has `secretsmanager:GetSecretValue` on the secret ARNs |
| WebUI build fails: `npm ERR! 404` | Check `NpmConfigSecretArn` — .npmrc must point to your internal npm registry with all packages mirrored. Use `make dep-manifest` to get the full list. |
| Multi-doc-discovery build fails | Check `PipConfigSecretArn` and `LambdaBaseImage` — this build uses pip (not uv) and needs the base image available internally |

## Generating the Dependency Manifest

To know which packages to mirror into your internal registry:

```bash
make dep-manifest
# Outputs:
#   dist/manifests/python-packages.txt (all Python deps with versions)
#   dist/manifests/node-packages.txt (all Node deps with versions)
```

Feed these manifests to your artifact repository to pre-fetch and scan all packages before builds run. See [Dependency Mirroring](../../docs/dependency-mirroring.md) for details.
