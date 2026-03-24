# Deploying with ALB for Private Network (Instead of CloudFront)

> **Scope:** This is the end-to-end runbook for deploying the GenAI IDP Accelerator in a **fully private / enterprise network** environment. It covers all the steps needed to go from a standard deployment to a private-network-compliant one.
>
> As additional private network requirements are implemented (e.g., private AppSync API, SSO integration), this document will be expanded. For the technical reference on the ALB hosting feature alone, see [ALB Hosting Guide](./alb-hosting.md).

This guide covers deploying the GenAI IDP Accelerator using an Application Load Balancer (ALB) instead of CloudFront, using the **Publish Templates + Deploy Separately** approach.

> **Note**: For standard deployments, CloudFront hosting (the default) is recommended. Use ALB hosting only when your environment has specific requirements that prevent using CloudFront (e.g., private network requirements, regulated environments, air-gapped VPCs).

## Prerequisites

### 1. Build Tools

- bash shell (Linux, macOS, Windows-WSL)
- AWS CLI (`aws`)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) — install via Homebrew on macOS:
  ```bash
  brew tap aws/tap && brew install aws-sam-cli
  sam --version  # verify: SAM CLI, version 1.x
  ```
- Python 3.12 or later with required packages:
  ```bash
  pip install boto3 rich typer PyYAML botocore setuptools ruff build cfn-lint
  ```
  > **macOS tip**: Use your conda or virtual environment Python, not `/usr/bin/python3` (system Python 3.9 on macOS lacks packages). Use `python` or the full path e.g. `/opt/anaconda3/bin/python`.
- Docker (must be running during publish)
- **Node.js 22.12+ and npm 10+** — required for UI build. Install via Homebrew on macOS:
  ```bash
  brew install node@22
  export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
  node --version  # verify: v22.x
  ```

### 2. VPC Requirements

You need an existing VPC with the following:

- **At least 2 subnets in different Availability Zones** — required by ALB
  - **Private subnets** (recommended for internal ALBs)
  - **Public subnets** (for internet-facing ALBs)
- **DNS resolution enabled** — the VPC must have `enableDnsSupport` and `enableDnsHostnames` set to `true`
- **Sufficient IP space** — the S3 VPC Interface Endpoint creates ENIs in each subnet

> **Don't have a VPC?** Use the provided CloudFormation template to create a test VPC with 2 private subnets and a self-signed ACM certificate in one step — see [Creating a Test VPC](#optional-creating-a-test-vpc-via-cloudformation) below.

### 3. ACM Certificate

An ACM certificate is required for the ALB HTTPS listener. Options:

- **ACM-issued certificate** (recommended for production) — request via ACM with DNS or email validation
- **Imported certificate** — import your organization's CA-signed certificate into ACM
- **Self-signed certificate** (for testing only):

```bash
# Generate and import a self-signed certificate
CERT_ARN=$(./scripts/generate_self_signed_cert.sh --region us-east-1 --domain myapp.internal)
echo "Certificate ARN: $CERT_ARN"

# Options:
#   --region   AWS region for ACM import (default: from AWS config)
#   --domain   Domain name for the certificate CN/SAN (default: self-signed.internal)
#   --days     Certificate validity in days (default: 365)
```

### 4. Network Connectivity

Users must be able to reach the ALB:

- **Internal ALB**: Users need VPN, Direct Connect, or access from within the VPC (e.g., WorkSpaces, Cloud9, SSM port forwarding)
- **Internet-facing ALB**: Users can access directly, but the ALB security group controls which source IPs are allowed

---

## Optional: Creating a Test VPC via CloudFormation

If you don't have a VPC yet, use the provided template to create one with 2 private subnets and a self-signed ACM certificate:

```bash
aws cloudformation deploy \
  --stack-name IDP-ALB-TestVPC \
  --template-file scripts/alb-test-vpc.yaml \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

When complete, get the outputs to use in the IDP deployment:

```bash
aws cloudformation describe-stacks \
  --stack-name IDP-ALB-TestVPC \
  --region us-east-1 \
  --query 'Stacks[0].Outputs[*].{Key:OutputKey,Value:OutputValue}' \
  --output table
```

The stack outputs `VpcId`, `SubnetIds`, `CertificateArn`, and a ready-to-use `IDPDeployCommand`.

---

## Step 1: Build and Publish with publish.py

> **Important**: Make sure Node.js 22.12+ is in your PATH before running publish.py, otherwise the UI validation step will fail.

```bash
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"  # macOS with brew node@22
node --version  # must be v22.x or later

python publish.py <cfn_bucket_basename> <cfn_prefix> <region>
```

**Parameters:**

- `cfn_bucket_basename`: Base name for the S3 bucket (e.g., `idp-<account-id>` for global uniqueness). The script creates bucket `<basename>-<region>` automatically if it doesn't exist.
- `cfn_prefix`: S3 prefix for artifacts (e.g., `idp`)
- `region`: AWS region (e.g., `us-east-1`)

**Example:**

```bash
python publish.py idp-549366490058 idp us-east-1
```

> **macOS note**: Use `python` (conda/venv) instead of `python3` (system Python 3.9) to ensure boto3 and other dependencies are available.

This will:

- Create the S3 bucket if it doesn't exist
- Build and cache Lambda layers
- Build SAM templates for all nested stacks and patterns concurrently
- Validate and build the UI (Node 22+ required)
- Package and upload all artifacts to S3

When complete, the script outputs:

- The **CloudFormation template S3 URL**
- A **1-Click Launch URL** for the CloudFormation console

If the build fails, use the `--verbose` flag for debugging:

```bash
python publish.py idp-549366490058 idp us-east-1 --verbose
```

---

## Step 2: Deploy via CloudFormation with ALB Parameters

### Option A: AWS CLI — New Stack

Use `aws cloudformation create-stack` with `--template-url` (note: `aws cloudformation deploy` does **not** support `--template-url`, only `--template-file`):

```bash
aws cloudformation create-stack \
  --region us-east-1 \
  --stack-name my-idp-stack \
  --template-url https://s3.us-east-1.amazonaws.com/<bucket>/idp/idp-main.yaml \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
  --parameters \
    ParameterKey=AdminEmail,ParameterValue=your.email@example.com \
    ParameterKey=WebUIHosting,ParameterValue=ALB \
    ParameterKey=ALBVpcId,ParameterValue=vpc-xxxxx \
    'ParameterKey=ALBSubnetIds,ParameterValue=subnet-aaaa\,subnet-bbbb' \
    ParameterKey=ALBCertificateArn,ParameterValue=arn:aws:acm:us-east-1:123456789012:certificate/xxxxx \
    ParameterKey=ALBScheme,ParameterValue=internal
```

> **Important**: For `ALBSubnetIds`, escape the comma with a backslash inside single quotes: `'ParameterKey=ALBSubnetIds,ParameterValue=subnet-aaaa\,subnet-bbbb'`. Without escaping, the AWS CLI splits the value into a list and fails validation.

### Option B: AWS CLI — Update Existing Stack

```bash
aws cloudformation update-stack \
  --stack-name my-idp-stack \
  --template-url https://s3.us-east-1.amazonaws.com/<bucket>/idp/idp-main.yaml \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
  --region us-east-1 \
  --parameters \
    ParameterKey=AdminEmail,ParameterValue=your.email@example.com \
    ParameterKey=WebUIHosting,ParameterValue=ALB \
    ParameterKey=ALBVpcId,ParameterValue=vpc-xxxxx \
    'ParameterKey=ALBSubnetIds,ParameterValue=subnet-aaaa\,subnet-bbbb' \
    ParameterKey=ALBCertificateArn,ParameterValue=arn:aws:acm:us-east-1:123456789012:certificate/xxxxx \
    ParameterKey=ALBScheme,ParameterValue=internal
```

### Option C: CloudFormation Console

1. Use the **1-Click Launch URL** from the publish script output, or navigate to **CloudFormation → Create Stack** and paste the template S3 URL.
2. In the parameter form, set the following values:

| Parameter | Value | Description |
|-----------|-------|-------------|
| `AdminEmail` | `your.email@example.com` | Admin email for notifications |
| `WebUIHosting` | `ALB` | Switches from CloudFront to ALB hosting |
| `ALBVpcId` | `vpc-xxxxx` | VPC for the ALB and S3 VPC endpoint |
| `ALBSubnetIds` | `subnet-aaaa,subnet-bbbb` | Min 2 subnets in different AZs |
| `ALBCertificateArn` | `arn:aws:acm:...` | ACM certificate ARN for HTTPS |
| `ALBScheme` | `internal` or `internet-facing` | ALB accessibility |
| `ALBAllowedCIDRs` | *(optional)* | CIDRs for ALB ingress; empty = VPC CIDR |

3. Acknowledge IAM capabilities and click **Create stack** (or **Update stack**).
4. Wait for the stack to reach `CREATE_COMPLETE` (10–15 minutes).

### Monitor Deployment Progress

```bash
# Check stack status
aws cloudformation describe-stacks --stack-name my-idp-stack --region us-east-1 \
  --query 'Stacks[0].StackStatus' --output text

# Watch latest events
aws cloudformation describe-stack-events --stack-name my-idp-stack --region us-east-1 \
  --query 'StackEvents[0:10].{Resource:LogicalResourceId,Status:ResourceStatus,Reason:ResourceStatusReason}' \
  --output table
```

---

## Step 3: Access the UI

### Get the ALB URL

```bash
aws cloudformation describe-stacks --stack-name IDP-ALB \
  --query 'Stacks[0].Outputs[?OutputKey==`ApplicationWebURL`].OutputValue' \
  --output text
```

### Internet-Facing ALB

Access the ALB DNS name directly from the URL above.

### Internal ALB

For internal ALBs, you need network connectivity to the VPC. Common approaches:

**VPN or Direct Connect** (recommended for production):

Access the ALB DNS name directly through your organization's private network connection.

**SSM Port Forwarding** (recommended for testing):

1. Launch a small EC2 instance (e.g., `t3.micro`) in the same VPC with an IAM role that includes `AmazonSSMManagedInstanceCore`.
2. Start a port forwarding session:

   ```bash
   aws ssm start-session \
     --target INSTANCE_ID \
     --document-name AWS-StartPortForwardingSessionToRemoteHost \
     --parameters '{"host":["ALB_DNS_NAME"],"portNumber":["443"],"localPortNumber":["8443"]}'
   ```

3. Add a local hosts file entry so the browser sends the correct Host header:

   ```bash
   echo "127.0.0.1 ALB_DNS_NAME" | sudo tee -a /etc/hosts
   ```

4. Open `https://ALB_DNS_NAME:8443/` in your browser (accept the certificate warning for self-signed certs).
5. Remove the hosts entry when done testing.

---

## What Gets Automatically Configured

When you set `WebUIHosting=ALB`, the following are automatically handled — no manual configuration needed:

- **S3 CORS origins** — resolve to the ALB URL
- **Cognito callback/logout URLs** — OAuth redirect URLs point to the ALB URL
- **UI build configuration** — `VITE_CLOUDFRONT_DOMAIN` resolves to the ALB URL
- **CodeBuild post-deploy** — CloudFront cache invalidation is skipped
- **Stack outputs** — `ApplicationWebURL` returns the ALB URL
- **S3 bucket policy** — uses `aws:sourceVpce` condition instead of CloudFront OAI

---

## Switching Between CloudFront and ALB

You can switch an existing CloudFront-hosted stack to ALB hosting (or vice versa) by updating the stack with the new `WebUIHosting` parameter value and providing the required ALB parameters. CloudFormation will conditionally create or remove the appropriate resources.

---

## Troubleshooting

| Issue | Resolution |
|-------|------------|
| **`ModuleNotFoundError: No module named 'boto3'`** | Use your conda/venv Python, not system Python 3.9. Run `python publish.py ...` instead of `python3 publish.py ...`, or use the full path e.g. `/opt/anaconda3/bin/python publish.py ...` |
| **`npm error engine Unsupported engine`** | Node.js 22.12+ is required. Install via `brew install node@22` and add to PATH: `export PATH="/opt/homebrew/opt/node@22/bin:$PATH"` |
| **`aws: error: the following arguments are required: --template-file`** | `aws cloudformation deploy` only supports `--template-file`. Use `aws cloudformation create-stack` or `update-stack` with `--template-url` instead. |
| **`Invalid type for parameter Parameters[N].ParameterValue`** | When passing comma-separated subnet IDs, escape the comma: `'ParameterKey=ALBSubnetIds,ParameterValue=subnet-aaaa\,subnet-bbbb'` |
| **403 Forbidden** | Verify ALB target group health checks pass (expected: 200, 307, 405). Check S3 bucket policy has correct VPC endpoint ID. |
| **404 Not Found** | Ensure request path matches a listener rule (`/` or `/*`). Verify the WebUI bucket contains `index.html`. |
| **Target Group Unhealthy** | VPC endpoint ENI IPs may be stale if the endpoint was recreated. Check VPC endpoint security group allows HTTPS from ALB. |
| **UI Not Loading** | Check CodeBuild logs. Verify `VITE_CLOUDFRONT_DOMAIN` resolves to ALB URL, not a CloudFront domain. |

---

## Security Notes

- ALB security group restricts ingress to port 443 from the VPC CIDR (or specified CIDRs)
- S3 bucket policy uses `aws:sourceVpce` condition — only requests through the VPC endpoint are allowed
- ALB enforces TLS 1.3 (`ELBSecurityPolicy-TLS13-1-2-2021-06`)
- ALB access logs are written to the logging bucket under `alb-access-logs/`
- All traffic between ALB and S3 traverses the VPC endpoint (no internet path)

---

For full details, see [ALB Hosting Guide](./alb-hosting.md) and [Deployment Guide](./deployment.md).
