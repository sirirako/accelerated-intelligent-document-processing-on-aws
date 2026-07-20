# Skill: Deploy

## When to use
Publishing and deploying the IDP stack to an environment.

## Full guide
**Read `enterprise/docs/deployment-guide.md`** — it's the full AI-guided
deployment walkthrough with all parameters, paths, and troubleshooting.

## Quick steps

1. `./enterprise/build.sh` (install enterprise layer deps)
2. `idp-cli publish --source-dir . --region <region>` (or `--from-code .` for one-shot)
3. `idp-cli deploy --stack-name <name> --template-url <url> --parameters "..."` 

## Key parameters (private VPC + headless)

```
WebUIHosting=ALB,ALBScheme=internal,ALBVpcId=<vpc>,ALBSubnetIds=<subnets>,
ALBCertificateArn=<cert>,ApiGatewayVisibility=PRIVATE,
ApiGatewayVpcEndpointId=<vpce>,LambdaSubnetIds=<subnets>,
EnableHeadless=true,DeployInVPC=true,VpcId=<vpc>,PrivateSubnetIds=<subnets>,
LambdaSecurityGroupId=<sg>,PingIssuer1=<issuer>,PingJwksUri1=<jwks>,
ArtifactsBucketKmsKeyArn=<key>
```

## Known issues
- Stack names must be lowercase (Cognito domain requirement)
- `ArtifactsBucketKmsKeyArn` required if S3 uses KMS
- CodeBuild Docker builds need NAT for image pulls
- `enterprise/build.sh` runs automatically in the SDLC pipeline
