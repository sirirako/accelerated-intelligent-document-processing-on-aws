# Private AppSync API — Implementation Plan (Req #2)

## Branch: `feature/private-appsync-api`

## Goal
Make the AppSync GraphQL API only accessible from within the VPC (not the internet) when `AppSyncVisibility=PRIVATE`. All traffic stays on the AWS backbone via VPC endpoints.

## Architecture

```
VPC
├── Public/Accessible Subnets  (ALBSubnetIds) — ALB lives here
└── Private Subnets (LambdaSubnetIds) — Lambda + VPC endpoints live here
      Lambda → VPC Endpoints → AppSync / Bedrock / DynamoDB / etc.
```

## Parameters Added
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `AppSyncVisibility` | String | `GLOBAL` | `GLOBAL` or `PRIVATE` |
| `LambdaSubnetIds` | CommaDelimitedList | `""` | Private subnet IDs for Lambda (can be same as ALBSubnetIds) |

## Condition Added
```yaml
UsePrivateAppSync: !Equals [ !Ref AppSyncVisibility, "PRIVATE" ]
```

## Completed Steps ✅

### Step 1 — Parameters (commit ca6d0f2f)
- `AppSyncVisibility` parameter
- `LambdaSubnetIds` parameter
- `UsePrivateAppSync` condition

### Step 2 — GraphQLApi + Security Group (commit de2d12f2)
- `Visibility: !If [UsePrivateAppSync, PRIVATE, GLOBAL]` on `GraphQLApi`
- `LambdaVpcSecurityGroup` (conditional `AWS::EC2::SecurityGroup` in `ALBVpcId`, allows HTTPS egress only)

---

## Remaining Steps 🔲

### Step 3 — AppSync VPC Endpoints (in `template.yaml`)

Add 2 conditional `AWS::EC2::VPCEndpoint` resources in `LambdaSubnetIds`:

```yaml
AppSyncApiVpcEndpoint:
  Type: AWS::EC2::VPCEndpoint
  Condition: UsePrivateAppSync
  Properties:
    VpcId: !Ref ALBVpcId
    ServiceName: !Sub "com.amazonaws.${AWS::Region}.appsync-api"
    VpcEndpointType: Interface
    SubnetIds: !Ref LambdaSubnetIds
    SecurityGroupIds:
      - !Ref LambdaVpcSecurityGroup
    PrivateDnsEnabled: true

AppSyncControlVpcEndpoint:
  Type: AWS::EC2::VPCEndpoint
  Condition: UsePrivateAppSync
  Properties:
    VpcId: !Ref ALBVpcId
    ServiceName: !Sub "com.amazonaws.${AWS::Region}.appsync"
    VpcEndpointType: Interface
    SubnetIds: !Ref LambdaSubnetIds
    SecurityGroupIds:
      - !Ref LambdaVpcSecurityGroup
    PrivateDnsEnabled: true
```

### Step 4 — Service VPC Endpoints (in `template.yaml`)

Add conditional Interface and Gateway endpoints so Lambdas can reach AWS services:

**Gateway Endpoints (free, no hourly cost):**
```yaml
S3VpcEndpoint:
  Type: AWS::EC2::VPCEndpoint
  Condition: UsePrivateAppSync
  Properties:
    VpcId: !Ref ALBVpcId
    ServiceName: !Sub "com.amazonaws.${AWS::Region}.s3"
    VpcEndpointType: Gateway
    RouteTableIds: []  # TODO: need route table IDs — may need new parameter

DynamoDbVpcEndpoint:
  Type: AWS::EC2::VPCEndpoint
  Condition: UsePrivateAppSync
  Properties:
    VpcId: !Ref ALBVpcId
    ServiceName: !Sub "com.amazonaws.${AWS::Region}.dynamodb"
    VpcEndpointType: Gateway
    RouteTableIds: []  # TODO: need route table IDs — may need new parameter
```

**Interface Endpoints (hourly cost, needed for Lambda → AWS service calls):**
- `sqs`
- `states` (Step Functions)
- `kms`
- `logs`
- `bedrock-runtime`
- `ssm`
- `secretsmanager`
- `lambda`
- `events`
- `athena`

```yaml
# Example for one — replicate for each service
SqsVpcEndpoint:
  Type: AWS::EC2::VPCEndpoint
  Condition: UsePrivateAppSync
  Properties:
    VpcId: !Ref ALBVpcId
    ServiceName: !Sub "com.amazonaws.${AWS::Region}.sqs"
    VpcEndpointType: Interface
    SubnetIds: !Ref LambdaSubnetIds
    SecurityGroupIds:
      - !Ref LambdaVpcSecurityGroup
    PrivateDnsEnabled: true
```

> **Note on Gateway Endpoints**: S3 and DynamoDB Gateway endpoints require Route Table IDs. Two options:
> 1. Add a new `LambdaRouteTableIds` parameter (CommaDelimitedList)
> 2. Use Interface endpoints for S3/DynamoDB instead (more expensive but no new parameter)
> **Recommendation**: Add `LambdaRouteTableIds` parameter (optional, empty default)

### Step 5 — Lambda VpcConfig in `template.yaml`

Add conditional `VpcConfig` to these Lambdas that call AppSync:
- `QueueSender`
- `QueueProcessor`
- `WorkflowTracker`
- `AgentProcessorFunction`
- `AgentChatProcessorFunction`
- `DiscoveryProcessorFunction`
- `SaveReportingDataFunctionV2` (calls S3/Glue)

Pattern:
```yaml
VpcConfig:
  !If
    - UsePrivateAppSync
    - SubnetIds: !Ref LambdaSubnetIds
      SecurityGroupIds:
        - !Ref LambdaVpcSecurityGroup
    - !Ref AWS::NoValue
```

Also **remove** `W89`/`CKV_AWS_117` suppression comments from these Lambdas (since they'll be in VPC when private mode is active).

### Step 6 — Update `nested/appsync/template.yaml`

Pass new parameters from main stack:

```yaml
# Add to Parameters section in nested/appsync/template.yaml
UsePrivateAppSync:
  Type: String
  Default: "false"
  AllowedValues: ["true", "false"]

LambdaSubnetIds:
  Type: CommaDelimitedList
  Default: ""

LambdaSecurityGroupId:
  Type: String
  Default: ""
```

Add condition:
```yaml
IsPrivateAppSync: !Equals [!Ref UsePrivateAppSync, "true"]
```

Add `VpcConfig` to these Lambdas:
- `AbortWorkflowResolverFunction`
- `CopyToBaselineResolverFunction`
- `ProcessChangesResolverFunction`
- `ReprocessDocumentResolverFunction`

Pass params in `APPSYNCSTACK` resource in `template.yaml`:
```yaml
UsePrivateAppSync: !If [UsePrivateAppSync, "true", "false"]
LambdaSubnetIds: !Join [",", !Ref LambdaSubnetIds]
LambdaSecurityGroupId: !If [UsePrivateAppSync, !Ref LambdaVpcSecurityGroup, ""]
```

### Step 7 — Update `patterns/unified/template.yaml`

Pass new parameters and add `VpcConfig` to all ~9 container functions that use `APPSYNC_API_URL`:
- `bda-invoke-function`
- `bda-processresults-function`
- `bda-completion-function`
- `ocr-function`
- `classification-function`
- `extraction-function`
- `assessment-function`
- `processresults-function`
- `summarization-function`

### Step 8 — Update `docs/deployment-private-network.md`

Add a new section explaining `AppSyncVisibility=PRIVATE` parameters and usage.

---

## Full Deployment Command (when complete)

```bash
aws cloudformation create-stack \
  --stack-name IDP-PRIVATE \
  --template-url https://s3.us-east-1.amazonaws.com/idp-<account-id>-us-east-1/idp/idp-main.yaml \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
  --parameters \
    ParameterKey=AdminEmail,ParameterValue=siriratk@amazon.com \
    ParameterKey=WebUIHosting,ParameterValue=ALB \
    ParameterKey=ALBVpcId,ParameterValue=vpc-xxxxx \
    'ParameterKey=ALBSubnetIds,ParameterValue=subnet-pub1\,subnet-pub2' \
    ParameterKey=ALBCertificateArn,ParameterValue=arn:aws:acm:... \
    ParameterKey=ALBScheme,ParameterValue=internal \
    ParameterKey=AppSyncVisibility,ParameterValue=PRIVATE \
    'ParameterKey=LambdaSubnetIds,ParameterValue=subnet-priv1\,subnet-priv2'
```

## Test VPC
Already deployed as `IDP-ALB-TestVPC` stack with:
- VPC: `vpc-0f42ddb124c806ba1`
- Public/ALB subnets: `subnet-0ae7c007a67c0a483`, `subnet-00b39e8345d9f0ff2`
- Use same subnets for Lambda in testing (no separate private subnets in test VPC)
- Cert: `arn:aws:acm:us-east-1:<account-id>:certificate/<cert-id>`
