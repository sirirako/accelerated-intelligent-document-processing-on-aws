# Deploying IDP in a Private Network

This runbook deploys the GenAI IDP Accelerator in a **fully private / air-gapped environment**:

- Web UI served via an **internal ALB** (no CloudFront)
- AppSync API accessible **only from inside the VPC** (no public endpoint)
- All Lambda → AWS service traffic routed through **VPC Interface Endpoints**
- Internet-facing features (MCP Gateway, Knowledge Base) **disabled**

> For standard public deployments, see [Deployment Guide](./deployment.md).

---

## Prerequisites

### 1. Build Tools

See [Deployment Guide → Dependencies](./deployment.md#dependencies) for the full list of required build tools and installation instructions (AWS CLI, SAM CLI, Python 3.12+, Docker, Node.js 22+).

### 2. VPC Requirements

You need an existing VPC with:

- **At least 2 subnets in different Availability Zones** — required by ALB
- **DNS resolution enabled** — `enableDnsSupport` and `enableDnsHostnames` must be `true`
- **Subnet IDs** for the ALB (can be the same or different from Lambda subnets)

> **Don't have a VPC?** Use the provided template to create one:
> ```bash
> aws cloudformation deploy \
>   --stack-name IDP-TestVPC \
>   --template-file scripts/alb-test-vpc.yaml \
>   --capabilities CAPABILITY_IAM \
>   --region us-east-1
>
> # Get outputs (VpcId, SubnetIds, CertificateArn)
> aws cloudformation describe-stacks \
>   --stack-name IDP-TestVPC \
>   --query 'Stacks[0].Outputs[*].{Key:OutputKey,Value:OutputValue}' \
>   --output table
> ```

### 3. ACM Certificate

An ACM certificate is required for the ALB HTTPS listener:

- **ACM-issued** (production): request via ACM console with DNS/email validation
- **Imported**: import your organization's CA-signed cert into ACM
- **Self-signed** (testing only):
  ```bash
  CERT_ARN=$(./scripts/generate_self_signed_cert.sh --region us-east-1 --domain myapp.internal)
  ```

### 4. Network Connectivity

Users must reach the internal ALB via VPN, Direct Connect, WorkSpaces, or SSM port forwarding.

---

## Step 1: Build and Publish Artifacts

> **Node.js 22.12+ must be in your PATH** before running publish.py.

```bash
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"  # macOS with brew node@22
node --version  # must be v22.x or later

python publish.py <bucket-basename> idp <region>
# Example: python publish.py idp-<account-id> idp us-east-1
```

The script creates an S3 bucket (`<bucket-basename>-<region>`) if needed, builds all Lambda layers and templates, and uploads artifacts. When done, it prints the **Template URL** to use in Step 2.

---

## Step 2: Deploy the IDP Stack

Replace the placeholder values and run:

```bash
aws cloudformation create-stack \
  --stack-name IDP-PRIVATE \
  --template-url https://s3.<region>.amazonaws.com/<bucket>/idp/idp-main.yaml \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
  --region <region> \
  --parameters \
    ParameterKey=AdminEmail,ParameterValue=admin@example.com \
    ParameterKey=WebUIHosting,ParameterValue=ALB \
    ParameterKey=ALBVpcId,ParameterValue=<vpc-id> \
    'ParameterKey=ALBSubnetIds,ParameterValue=<subnet-1>\,<subnet-2>' \
    ParameterKey=ALBCertificateArn,ParameterValue=<cert-arn> \
    ParameterKey=ALBScheme,ParameterValue=internal \
    ParameterKey=AppSyncVisibility,ParameterValue=PRIVATE \
    'ParameterKey=LambdaSubnetIds,ParameterValue=<subnet-1>\,<subnet-2>' \
    ParameterKey=EnableMCP,ParameterValue=false \
    ParameterKey=DocumentKnowledgeBase,ParameterValue=DISABLED
```

**Key parameters:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `WebUIHosting` | `ALB` | Serve UI via internal ALB instead of CloudFront |
| `ALBScheme` | `internal` | ALB not reachable from internet |
| `AppSyncVisibility` | `PRIVATE` | AppSync API only accessible inside the VPC |
| `LambdaSubnetIds` | subnet IDs | Subnets where Lambda functions run (can match ALBSubnetIds) |
| `EnableMCP` | `false` | Disable Bedrock AgentCore Gateway (requires public endpoint) |
| `DocumentKnowledgeBase` | `DISABLED` | Disable Knowledge Base (avoids extra VPC endpoints) |

> **`AppSyncVisibility` is immutable** — it cannot be changed after the stack is created. To switch between GLOBAL and PRIVATE, delete and recreate the stack.

> **Comma escaping**: always escape commas in `ALBSubnetIds` and `LambdaSubnetIds` with a backslash inside single quotes: `'ParameterKey=...,ParameterValue=subnet-a\,subnet-b'`

Wait for the stack to reach `CREATE_COMPLETE` (~15 minutes):

```bash
aws cloudformation describe-stacks --stack-name IDP-PRIVATE --region <region> \
  --query 'Stacks[0].StackStatus' --output text
```

---

## Step 3: Deploy VPC Endpoints

Lambda functions need VPC Interface Endpoints to reach AWS services (AppSync, Bedrock, SQS, etc.) without leaving the AWS backbone.

Run the deployment script — it automatically detects which of the 12 required endpoints already exist in your VPC and deploys only the missing ones:

```bash
python scripts/deploy-vpc-endpoints.py \
  --vpc-id <vpc-id> \
  --stack-name IDP-PRIVATE \
  --region <region>
```

**Windows (PowerShell):**
```powershell
python scripts/deploy-vpc-endpoints.py `
  --vpc-id <vpc-id> `
  --stack-name IDP-PRIVATE `
  --region <region>
```

The script:
1. Reads `LambdaSubnetIds` and `LambdaVpcSecurityGroupId` from the IDP stack automatically
2. Checks each of the 12 required endpoints against the VPC
3. Deploys only the missing ones (skips any that already exist to avoid DNS conflicts)
4. Waits for `CREATE_COMPLETE` and reports the result

Example output:
```
🔍 Reading IDP stack outputs from: IDP-PRIVATE
   Lambda SG: sg-0e7f3764a5b908021
   Subnets:   subnet-0ae7c007a67c0a483,subnet-00b39e8345d9f0ff2

🔍 Checking existing VPC endpoints in vpc-0f42ddb124c806ba1 (region: us-east-1)...

   ✅ com.amazonaws.us-east-1.ssm              already exists — will skip
   ➕ com.amazonaws.us-east-1.appsync-api      missing — will create
   ➕ com.amazonaws.us-east-1.sqs              missing — will create
   ...

📊 Summary: 11 to create, 1 already exist

🚀 Deploying VPC endpoints stack: IDP-PRIVATE-VPCEndpoints
⏳ Waiting for stack 'IDP-PRIVATE-VPCEndpoints' to reach CREATE_COMPLETE...
✅ VPC endpoints deployed successfully!
```

> **Optional `--dry-run`**: add `--dry-run` to see what would be deployed without making any changes.

---

## Step 4: Access the UI

### Get the UI URL

```bash
aws cloudformation describe-stacks --stack-name IDP-PRIVATE \
  --query 'Stacks[0].Outputs[?OutputKey==`ApplicationWebURL`].OutputValue' \
  --output text
```

The URL will look like `https://internal-IDP-PRIVATE-webui-alb-<id>.<region>.elb.amazonaws.com`.

### Accessing via VPN or Direct Connect (production)

Connect to the VPC through your organization's VPN or Direct Connect — the ALB DNS name resolves and routes automatically.

### Accessing via SSM port forwarding (testing)

1. Create a small EC2 instance in the VPC for SSM tunneling:

   ```bash
   # Create an IAM role and instance profile for SSM access
   aws iam create-role --role-name IDP-SSMInstanceRole \
     --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
   aws iam attach-role-policy --role-name IDP-SSMInstanceRole \
     --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
   aws iam create-instance-profile --instance-profile-name IDP-SSMInstanceProfile
   aws iam add-role-to-instance-profile \
     --instance-profile-name IDP-SSMInstanceProfile \
     --role-name IDP-SSMInstanceRole

   # Launch a t3.nano in the private subnet (no public IP needed)
   INSTANCE_ID=$(aws ec2 run-instances \
     --image-id resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
     --instance-type t3.nano \
     --subnet-id <subnet-id> \
     --iam-instance-profile Name=IDP-SSMInstanceProfile \
     --no-associate-public-ip-address \
     --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=IDP-SSM-Bastion}]' \
     --query 'Instances[0].InstanceId' --output text)
   echo "Instance ID: $INSTANCE_ID"

   # Wait ~60 seconds for the SSM agent to register, then verify
   aws ssm describe-instance-information \
     --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
     --query 'InstanceInformationList[0].PingStatus' --output text
   # Should return: Online
   ```

   > **Note**: The SSM endpoints (`ssm`, `ssmmessages`, `ec2messages`) must be present in the VPC — these were deployed by `scripts/deploy-vpc-endpoints.py` in Step 3.

2. In **Terminal 1** — forward the ALB:
   ```bash
   aws ssm start-session \
     --target <ec2-instance-id> \
     --document-name AWS-StartPortForwardingSessionToRemoteHost \
     --parameters '{"host":["<ALB_DNS_NAME>"],"portNumber":["443"],"localPortNumber":["8443"]}'
   ```

3. In **Terminal 2** — forward AppSync (required for private AppSync):
   ```bash
   # Get the AppSync VPC endpoint DNS
   APPSYNC_VPCE=$(aws ec2 describe-vpc-endpoints \
     --filters "Name=vpc-id,Values=<vpc-id>" "Name=service-name,Values=com.amazonaws.<region>.appsync-api" \
     --query 'VpcEndpoints[0].DnsEntries[0].DnsName' --output text)

   # Get the AppSync API hostname from the IDP stack
   APPSYNC_URL=$(aws cloudformation describe-stacks --stack-name IDP-PRIVATE \
     --query 'Stacks[0].Outputs[?OutputKey==`ApplicationWebURL`].OutputValue' \
     --output text)
   # The AppSync hostname is shown in the browser network tab when you open the UI

   sudo aws ssm start-session \
     --target <ec2-instance-id> \
     --document-name AWS-StartPortForwardingSessionToRemoteHost \
     --parameters "{\"host\":[\"$APPSYNC_VPCE\"],\"portNumber\":[\"443\"],\"localPortNumber\":[\"443\"]}"
   ```

4. In **Terminal 3** — add a hosts entry for AppSync:
   ```bash
   # Get AppSync hostname (e.g. xxxxx.appsync-api.us-east-1.amazonaws.com)
   # from the browser network tab or from: aws appsync list-graphql-apis --query 'graphqlApis[?name==`IDP-PRIVATE-api`].uris.GRAPHQL'
   echo "127.0.0.1 <appsync-hostname>.appsync-api.<region>.amazonaws.com" | sudo tee -a /etc/hosts
   ```

5. Open `https://<ALB_DNS_NAME>:8443/` in your browser (accept the self-signed cert warning).

6. **Clean up when done**:
   ```bash
   sudo sed -i '' '/<appsync-hostname>/d' /etc/hosts
   # Ctrl+C in both SSM terminal sessions
   ```

> **In production**: users on VPN/Direct Connect don't need any of steps 2–6. DNS resolves automatically inside the VPC.

---

## What Gets Automatically Configured

When `WebUIHosting=ALB` and `AppSyncVisibility=PRIVATE`, the following are handled automatically:

- **S3 CORS origins** → ALB URL
- **Cognito callback/logout URLs** → ALB URL
- **UI build** → `VITE_CLOUDFRONT_DOMAIN` set to ALB URL
- **S3 bucket policy** → `aws:sourceVpce` condition (VPC endpoint access only)
- **21 Lambda functions** → placed in VPC subnets with HTTPS-only egress

---

## Troubleshooting

| Issue | Resolution |
|-------|------------|
| **`ModuleNotFoundError: No module named 'boto3'`** | Use conda/venv Python, not system Python 3.9. Run `python publish.py ...` not `python3`. |
| **`npm error engine Unsupported engine`** | Node.js 22.12+ required. `brew install node@22 && export PATH="/opt/homebrew/opt/node@22/bin:$PATH"` |
| **Stack fails with `conflicting DNS domain`** | A VPC endpoint already exists for that service. Re-run `check-vpc-endpoints.sh` — it will detect this and set the right `Create*=false` flags. |
| **UI loads but shows "network error"** | AppSync API is PRIVATE. From outside the VPC you need an SSM tunnel + `/etc/hosts` entry. From inside VPN/VPC it works automatically. |
| **`aws: error: the following arguments are required: --template-file`** | `aws cloudformation deploy` only supports `--template-file`. Use `create-stack` or `update-stack` with `--template-url`. |
| **`Invalid type for parameter Parameters[N].ParameterValue`** | Escape commas: `'ParameterKey=ALBSubnetIds,ParameterValue=subnet-a\,subnet-b'` |
| **403 Forbidden on ALB** | Check ALB target group health checks (expected: 200, 307, 405). Verify S3 bucket policy has the correct VPC endpoint ID. |
| **Target Group Unhealthy** | VPC endpoint ENIs may be stale. Check the endpoint SG allows HTTPS (443) from the ALB. |
