# Enterprise Feature Testing

## When to use

Use this skill when:
- Testing private registry support after changes
- Verifying a deployment with enterprise parameters
- Running end-to-end validation of the enterprise fork
- Debugging build failures related to private registries

## Testing approach

Enterprise features are tested by deploying with **public registry URLs stored in Secrets Manager**. This proves the mechanism works (secrets are read, config files are written, builds use them) without needing an actual private registry.

## Prerequisites

- AWS account with permissions to deploy CloudFormation stacks
- `idp-cli` installed (`make setup`)
- AWS CLI v2 at `/usr/local/bin/aws` (avoid anaconda version)
- `uv`, `jq`, Docker running
- A VPC with NAT gateway (for CodeBuild internet access during test)

## Test 1: Private Registry Mechanism (public URLs in secrets)

Proves the plumbing works — secrets are read, config files are written, builds succeed.

```bash
# Create test secrets with public registry configs
aws secretsmanager create-secret --name idp-test/pip \
  --secret-string '[global]
index-url = https://pypi.org/simple'

aws secretsmanager create-secret --name idp-test/uv \
  --secret-string 'index-url = "https://pypi.org/simple"'

aws secretsmanager create-secret --name idp-test/docker \
  --secret-string '{}'

aws secretsmanager create-secret --name idp-test/npm \
  --secret-string 'registry=https://registry.npmjs.org/'

# Deploy with enterprise params
idp-cli deploy --stack-name IDP-ENTERPRISE-TEST \
  --admin-email test@example.com \
  --region us-east-1 \
  --wait \
  --parameters "DeployInVPC=true,\
VpcId=<vpc-id>,\
PrivateSubnetIds=<subnet-a> <subnet-b>,\
LambdaSubnetIds=<subnet-a> <subnet-b>,\
LambdaSecurityGroupId=<sg-id>,\
AppSyncVisibility=PRIVATE,\
WebUIHosting=ALB,\
ALBVpcId=<vpc-id>,\
ALBSubnetIds=<subnet-a> <subnet-b>,\
ALBCertificateArn=<cert-arn>,\
ALBScheme=internal,\
EnableMCP=false,\
DocumentKnowledgeBase=DISABLED,\
PipConfigSecretArn=arn:aws:secretsmanager:<region>:<account>:secret:idp-test/pip-XXXXXX,\
UvConfigSecretArn=arn:aws:secretsmanager:<region>:<account>:secret:idp-test/uv-XXXXXX,\
DockerConfigSecretArn=arn:aws:secretsmanager:<region>:<account>:secret:idp-test/docker-XXXXXX,\
NpmConfigSecretArn=arn:aws:secretsmanager:<region>:<account>:secret:idp-test/npm-XXXXXX"
```

### What to verify

```bash
# 1. Stack deployed successfully
aws cloudformation describe-stacks --stack-name IDP-ENTERPRISE-TEST \
  --query 'Stacks[0].StackStatus'
# Expected: CREATE_COMPLETE or UPDATE_COMPLETE

# 2. CodeBuild projects have VPC config
aws codebuild batch-get-projects \
  --names "$(aws codebuild list-projects --query 'projects[?contains(@, `IDP-ENTERPRISE-TEST`)]' --output text)" \
  --query 'projects[*].[name,vpcConfig.vpcId]'
# Expected: all show vpc-id (not null)

# 3. Docker build succeeded (check most recent build)
PROJECT=$(aws codebuild list-projects --query 'projects[?contains(@, `docker-build`) && contains(@, `ENTERPRISE`)]' --output text)
BUILD_ID=$(aws codebuild list-builds-for-project --project-name "$PROJECT" --query 'ids[0]' --output text)
aws codebuild batch-get-builds --ids "$BUILD_ID" --query 'builds[0].buildStatus'
# Expected: SUCCEEDED

# 4. Lambda functions have correct architecture
aws lambda list-functions \
  --query 'Functions[?starts_with(FunctionName, `IDP-ENTERPRISE-TEST-PATTERNSTACK`)].{Name:FunctionName,Arch:Architectures[0]}' \
  --output table
# Expected: all show arm64 (or x86_64 if LambdaArchitecture=x86_64)

# 5. End-to-end: upload a document and verify processing
idp-cli run-inference --stack-name IDP-ENTERPRISE-TEST --dir ./samples/ --monitor
# Expected: documents process successfully
```

## Test 2: Default deployment (no enterprise params)

Proves enterprise changes don't break standard deployments.

```bash
idp-cli deploy --stack-name IDP-STANDARD-TEST \
  --admin-email test@example.com \
  --region us-east-1 \
  --wait \
  --parameters "EnableMCP=false,DocumentKnowledgeBase=DISABLED"
```

### What to verify

```bash
# 1. Stack deployed successfully
aws cloudformation describe-stacks --stack-name IDP-STANDARD-TEST \
  --query 'Stacks[0].StackStatus'
# Expected: CREATE_COMPLETE

# 2. CodeBuild projects have NO VPC config
aws codebuild batch-get-projects \
  --names "$(aws codebuild list-projects --query 'projects[?contains(@, `IDP-STANDARD-TEST`)]' --output text)" \
  --query 'projects[*].[name,vpcConfig]'
# Expected: all show null for vpcConfig

# 3. No secrets manager env vars on CodeBuild
PROJECT=$(aws codebuild list-projects --query 'projects[?contains(@, `docker-build`) && contains(@, `STANDARD`)]' --output text)
aws codebuild batch-get-projects --names "$PROJECT" \
  --query 'projects[0].environment.environmentVariables[?type==`SECRETS_MANAGER`]'
# Expected: empty or null

# 4. Build succeeds with public registries
BUILD_ID=$(aws codebuild list-builds-for-project --project-name "$PROJECT" --query 'ids[0]' --output text)
aws codebuild batch-get-builds --ids "$BUILD_ID" --query 'builds[0].buildStatus'
# Expected: SUCCEEDED
```

## Test 3: Architecture switch (x86_64)

Proves LambdaArchitecture parameter works.

```bash
# Update existing stack to switch architecture
idp-cli deploy --stack-name IDP-ENTERPRISE-TEST \
  --region us-east-1 \
  --wait \
  --parameters "LambdaArchitecture=x86_64"
```

### What to verify

```bash
# Lambda functions report x86_64
aws lambda list-functions \
  --query 'Functions[?starts_with(FunctionName, `IDP-ENTERPRISE-TEST-PATTERNSTACK`)].{Name:FunctionName,Arch:Architectures[0]}' \
  --output table
# Expected: all show x86_64

# Docker build used linux/amd64 platform
BUILD_ID=$(aws codebuild list-builds-for-project --project-name "$PROJECT" --query 'ids[0]' --output text)
aws codebuild batch-get-builds --ids "$BUILD_ID" --query 'builds[0].buildStatus'
# Expected: SUCCEEDED
```

## Test 4: Multi-doc-discovery with private registry

Proves the inline Dockerfile in multi-doc-discovery uses the parameterized base image and pip secret.

```bash
# Check the multi-doc-discovery CodeBuild project
DISC_PROJECT=$(aws codebuild list-projects --query 'projects[?contains(@, `MULTIDOCDISCOVERY`) && contains(@, `ENTERPRISE`)]' --output text)
aws codebuild batch-get-projects --names "$DISC_PROJECT" \
  --query 'projects[0].environment.environmentVariables[*].[name,value]'
# Expected: LAMBDA_BASE_IMAGE, PIP_CONF (SECRETS_MANAGER), DOCKER_CONF (SECRETS_MANAGER)
```

## Test 5: Dependency manifest generation

Proves the manifest script works and produces complete output.

```bash
make dep-manifest

# Verify output
wc -l dist/manifests/python-packages.txt dist/manifests/node-packages.txt
# Expected: ~259 Python, ~1500 Node

# Verify no unversioned packages
grep -v "==" dist/manifests/python-packages.txt | grep -v "^$"
# Expected: no output (all packages have versions)
```

## Cleanup

```bash
# Delete test secrets
aws secretsmanager delete-secret --secret-id idp-test/pip --force-delete-without-recovery
aws secretsmanager delete-secret --secret-id idp-test/uv --force-delete-without-recovery
aws secretsmanager delete-secret --secret-id idp-test/docker --force-delete-without-recovery
aws secretsmanager delete-secret --secret-id idp-test/npm --force-delete-without-recovery

# Delete test stacks
aws cloudformation delete-stack --stack-name IDP-ENTERPRISE-TEST
aws cloudformation delete-stack --stack-name IDP-STANDARD-TEST
```

## Common issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ExpiredToken` during deploy | Session token expired (1hr limit) | Get fresh credentials |
| `UPDATE_ROLLBACK_IN_PROGRESS` | Previous update failed mid-deploy | Wait for rollback to complete, then retry |
| CodeBuild `FAILED` but phases show `SUCCEEDED` | Custom resource timeout — build took too long | Check build duration; increase `TimeoutInMinutes` if needed |
| `No module named 'boto3'` during publish | Wrong Python/pip (anaconda conflict) | Use `PATH="/usr/local/bin:$PATH"` before running |
| Stack fails with empty VPC subnet | `CommaDelimitedList` param not parsed correctly | Use spaces not commas between subnet IDs in idp-cli params |
