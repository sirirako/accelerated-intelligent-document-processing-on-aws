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

### Step 3 + 4 — VPC Endpoints (commits 86ab955f → refactored in 141cd3f8)

**Original**: Added 12 Interface + 2 Gateway VPC endpoints directly in `template.yaml`.

**Refactored** (commit `141cd3f8`) per enterprise networking separation:
- **Removed** all VPC endpoint resources from `template.yaml` (app team owns application, not networking)
- **Removed** `LambdaRouteTableIds` parameter and `UsePrivateAppSyncWithRouteTables` condition
- **Added** `LambdaVpcSecurityGroupId` Output to `template.yaml` — networking team uses this as input
- **Created** `scripts/vpc-endpoints.yaml` — standalone CFN template owned by the networking team:
  - Parameters: `VpcId`, `SubnetIds`, `LambdaSecurityGroupId` (from IDP Output), optional `RouteTableIds`
  - Creates `VpcEndpointSecurityGroup` (inbound 443 from Lambda SG)
  - 12 Interface endpoints: AppSync API + control, SQS, Step Functions, KMS, CloudWatch Logs, Bedrock Runtime, SSM, Secrets Manager, Lambda, EventBridge, Athena
  - 2 Gateway endpoints (optional, free): S3, DynamoDB
  - All resources tagged with `IDPStack` and `Environment`

**Deploy order**:
1. App team: `aws cloudformation deploy --template-file template.yaml ... --parameter-overrides AppSyncVisibility=PRIVATE LambdaSubnetIds=...`
2. Get SG: `aws cloudformation describe-stacks --stack-name <NAME> --query "Stacks[0].Outputs[?OutputKey=='LambdaVpcSecurityGroupId'].OutputValue" --output text`
3. Networking team: `aws cloudformation deploy --template-file scripts/vpc-endpoints.yaml ... --parameter-overrides IDPStackName=<NAME> VpcId=<VPC> SubnetIds=<SUBNETS> LambdaSecurityGroupId=<SG>`

### Step 5 — Lambda VpcConfig in `template.yaml` (commit 7c962a2a)
Added conditional `VpcConfig` to all 7 Lambdas that call AppSync:
- `QueueSender` — after `Tracing: Active`, before `DeadLetterQueue`
- `QueueProcessor` — after `Tracing: Active`, before `LoggingConfig`
- `WorkflowTracker` — after `Tracing: Active`, before `DeadLetterQueue`
- `SaveReportingDataFunctionV2` — after `Tracing: Active`, before `LoggingConfig`
- `AgentChatProcessorFunction` — after `MemorySize: 1024 # Increase memory...`, before `Environment`
- `AgentProcessorFunction` — after `MemorySize: 1024`, before `Environment`
- `DiscoveryProcessorFunction` — after `Layers: IDPCommonBaseLayer`, before `Environment`

Pattern used (identical for all 7):
```yaml
VpcConfig: !If
  - UsePrivateAppSync
  - SubnetIds: !Ref LambdaSubnetIds
    SecurityGroupIds:
      - !Ref LambdaVpcSecurityGroup
  - !Ref AWS::NoValue
```

---

## All Steps Complete ✅

> All 8 steps are implemented. The sections below are retained as reference documentation.

### Step 3 — AppSync VPC Endpoints — Refactored ✅ (commit 141cd3f8)

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

### Step 5 — Lambda VpcConfig in `template.yaml` ✅ (commit 7c962a2a)

Added VpcConfig to 7 Lambdas: `QueueSender`, `QueueProcessor`, `WorkflowTracker`, `SaveReportingDataFunctionV2`, `AgentChatProcessorFunction`, `AgentProcessorFunction`, `DiscoveryProcessorFunction`.

### Step 6 — Update `nested/appsync/template.yaml` ✅ (commit 6997cddc)

Added `UsePrivateAppSync`, `LambdaSubnetIds`, `LambdaSecurityGroupId` params + `IsPrivateAppSync` condition + VpcConfig to 4 resolver Lambdas: `AbortWorkflowResolverFunction`, `CopyToBaselineResolverFunction`, `ProcessChangesResolverFunction`, `ReprocessDocumentResolverFunction`.

### Step 7 — Update `patterns/unified/template.yaml` ✅ (commit 68c853e7)

Added `UsePrivateAppSync`, `LambdaSubnetIds`, `LambdaSecurityGroupId` params + `IsPrivateAppSync` condition + VpcConfig to 10 processing Lambdas:
`BDAProcessResultsFunction`, `OCRFunction`, `ClassificationFunction`, `ExtractionFunction`, `AssessmentFunction`, `ProcessResultsFunction`, `SummarizationFunction`, `EvaluationFunction`, `RuleValidationFunction`, `RuleValidationOrchestrationFunction`.

### Step 8 — Update `docs/deployment-private-network.md` ✅ (commit 7220d9b9)

Added "Private AppSync API (`AppSyncVisibility=PRIVATE`)" section with full two-step deployment runbook, VPC endpoint details, and test VPC commands.

---

## Full Deployment Command

See [deployment-private-network.md — Private AppSync API section](./deployment-private-network.md#private-appsync-api-appsynvisibilityprivate) for complete deploy commands.

## Test VPC
Pre-deployed as `IDP-ALB-TestVPC` stack with:
- VPC: `vpc-0f42ddb124c806ba1`
- Public/ALB subnets: `subnet-0ae7c007a67c0a483`, `subnet-00b39e8345d9f0ff2`
- Use same subnets for Lambda in testing (no separate private subnets in test VPC)
- Cert: see `IDP-ALB-TestVPC` stack output `CertificateArn`
