# Skill: Deploy

## When to use
Publishing and deploying the IDP stack to an environment.

## Steps

1. Build enterprise layers:
   ```bash
   ./enterprise/build.sh
   ```

2. Publish:
   ```bash
   idp-cli publish --source-dir . --bucket-basename <bucket> --prefix <prefix> --region <region>
   ```

3. Deploy:
   ```bash
   idp-cli deploy --stack-name <name> --template-url <url> --region <region> --wait \
     --parameters "<params from enterprise/environments/*.yaml>"
   ```

## Required parameters for private VPC + headless

```
WebUIHosting=ALB
ALBScheme=internal
ALBVpcId=<vpc>
ALBSubnetIds=<subnets>
ALBCertificateArn=<cert>
ApiGatewayVisibility=PRIVATE
ApiGatewayVpcEndpointId=<vpce>
LambdaSubnetIds=<subnets>
EnableHeadless=true
DeployInVPC=true
VpcId=<vpc>
PrivateSubnetIds=<subnets>
LambdaSecurityGroupId=<sg>
PingIssuer1=<issuer>
PingJwksUri1=<jwks>
ArtifactsBucketKmsKeyArn=<key>  (if S3 uses KMS)
```

## Known issues
- Stack names must be **lowercase** (ApiUserPoolDomain in Cognito requires it)
- `ArtifactsBucketKmsKeyArn` required if publish bucket uses KMS encryption
- CodeBuild Docker builds can timeout on first deploy in VPC (NAT required, be patient)
- `ruff.toml` must exclude `enterprise/layers/*/python` to pass publish linting
- v0.5 → v0.6 upgrade fails on old stacks with `custom:idp_groups` schema constraint mismatch

## Pipeline deploy (automated)
The SDLC pipeline handles publish + deploy automatically:
1. Pipeline reads `deploy/pipeline-config.yaml` from S3
2. Runs `enterprise/build.sh` (install layers)
3. Runs `idp-cli publish`
4. Runs `idp-cli deploy` with params from config
