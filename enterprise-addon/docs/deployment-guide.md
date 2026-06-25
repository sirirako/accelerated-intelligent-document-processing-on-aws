# Enterprise Integration — Deployment Guide

This guide covers deploying IDP with the enterprise integration add-on (Ping API auth + Amazon MQ completion hook). It builds on the standard IDP deployment — you deploy exactly the same way, with additional parameters.

## Prerequisites

### Standard IDP prerequisites

- AWS CLI v2
- Python 3.12+ with boto3
- Node.js 22.12+
- SAM CLI
- `make setup-venv && source .venv/bin/activate`

### Enterprise-specific prerequisites

| Prerequisite | What you need | Who provides it |
|---|---|---|
| **PingFederate** | Issuer URL, JWKS endpoint URL, audience/client_id | Your identity team |
| **Ping OAuth2 client (API)** | A client configured with `client_credentials` grant and `jobs.read`/`jobs.write` scopes | Your identity team |
| **Amazon MQ broker** (if using completion hook) | RabbitMQ broker hostname, OAuth2 backend configured with Ping as issuer | Your messaging/infra team |
| **Ping OAuth2 client (MQ)** (if using completion hook) | A client with scopes that map to RabbitMQ publish permissions; client secret in Secrets Manager | Your identity team |
| **VPC networking** | Ping and MQ must be reachable from the Lambda security group (in-VPC) | Your network team |

### Build the enterprise layers

Before publishing, install the Python dependencies into the layer directories:

```bash
./enterprise-addon/build.sh
```

This installs PyJWT (for the authorizer) and pika (for the MQ hook) so SAM can package them.

---

## Step 1 — Publish artifacts to S3

Same as standard IDP:

```bash
idp-cli publish \
  --source-dir . \
  --bucket-basename idp-<ACCOUNT_ID> \
  --prefix idp \
  --region <REGION>
```

Or one-shot:

```bash
idp-cli deploy --from-code . --stack-name <STACK_NAME> --admin-email <EMAIL> --region <REGION> --wait --parameters "<PARAMS>"
```

The enterprise Lambda code and layers are packaged automatically — SAM sees the `CodeUri`/`ContentUri` references in `template.yaml` and uploads them alongside all other artifacts.

---

## Step 2 — Deploy

### Minimal enterprise deployment (Ping auth only)

```bash
idp-cli deploy \
  --stack-name IDP \
  --template-url <TEMPLATE_URL> \
  --admin-email admin@example.com \
  --region us-east-1 \
  --wait \
  --parameters "DeployInVPC=true,VpcId=vpc-xxx,PrivateSubnetIds=subnet-a,subnet-b,LambdaSecurityGroupId=sg-xxx,EnableHeadless=true,ApiGatewayVpcEndpointId=vpce-xxx,EnablePingAuth=true,PingIssuer=https://sso.corp.example.com,PingJwksUri=https://sso.corp.example.com/pf/JWKS,PingAudience=idp-api"
```

### Full enterprise deployment (Ping auth + completion hook)

```bash
idp-cli deploy \
  --stack-name IDP \
  --template-url <TEMPLATE_URL> \
  --admin-email admin@example.com \
  --region us-east-1 \
  --wait \
  --parameters "DeployInVPC=true,VpcId=vpc-xxx,PrivateSubnetIds=subnet-a,subnet-b,LambdaSecurityGroupId=sg-xxx,EnableHeadless=true,ApiGatewayVpcEndpointId=vpce-xxx,EnablePingAuth=true,PingIssuer=https://sso.corp.example.com,PingJwksUri=https://sso.corp.example.com/pf/JWKS,PingAudience=idp-api,EnableCompletionHook=true,CompletionHookMQHost=b-xxxx.mq.us-east-1.amazonaws.com,CompletionHookMQExchange=idp-events,CompletionHookMQRoutingKey=idp.document.completed,CompletionHookMQOAuthScope=idp-mq.write:%2F/idp-events,CompletionHookPingTokenUrl=https://sso.corp.example.com/as/token,CompletionHookPingClientId=idp-completion-hook,CompletionHookPingClientSecretArn=arn:aws:secretsmanager:us-east-1:123456789012:secret:ping/mq-client"
```

> **Important:** The `--parameters` value must be a single unbroken string. Do NOT use backslash `\` line-continuation inside it.

---

## Step 3 — Verify

### Verify Ping auth is working

```bash
# 1. Get a token from PingFederate
TOKEN=$(curl -s -X POST https://sso.corp.example.com/as/token \
  -d "grant_type=client_credentials&scope=jobs.read jobs.write" \
  -u "my-client-id:my-client-secret" | jq -r .access_token)

# 2. Call the Jobs API
curl -s https://<api-id>-<vpce-id>.execute-api.us-east-1.amazonaws.com/beta/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"fileName": "test-document.zip"}'
```

**Expected:** 200 response with `jobId` and `upload` URL.

**If you get 401:** Check that `PingIssuer`, `PingJwksUri`, `PingAudience` match your Ping configuration and that the Lambda security group can reach Ping's JWKS endpoint.

### Verify completion hook is working

1. Submit a document through the Jobs API (or the Web UI)
2. Wait for processing to complete
3. Check your RabbitMQ consumer received a message:

```json
{
  "document_id": "jobs/a3b2c1d4-.../test-document.zip",
  "status": "SUCCEEDED",
  "results_location": "s3://...",
  "execution_arn": "arn:aws:states:...",
  "completed_at": "2026-06-24T10:05:15Z"
}
```

**If no message arrives:** Check CloudWatch Logs for the `<STACK_NAME>-CompletionHook` Lambda. Common issues:
- Lambda can't reach Ping token endpoint (security group / network)
- Lambda can't reach MQ broker (security group / port 5671)
- Wrong client secret ARN in `CompletionHookPingClientSecretArn`
- RabbitMQ OAuth2 backend misconfigured (wrong issuer/JWKS)

---

## Parameters reference

### Standard VPC + Headless parameters (required)

| Parameter | Description |
|---|---|
| `DeployInVPC` | `true` |
| `VpcId` | Your VPC ID |
| `PrivateSubnetIds` | Comma-separated private subnet IDs (≥2 AZs) |
| `LambdaSecurityGroupId` | Security group for Lambda functions |
| `EnableHeadless` | `true` (deploys the Jobs API) |
| `ApiGatewayVpcEndpointId` | `execute-api` VPC endpoint ID |

### Ping auth parameters

| Parameter | Required | Description |
|---|---|---|
| `EnablePingAuth` | Yes | `true` to switch Jobs API to Ping auth |
| `PingIssuer` | Yes | Ping OIDC issuer URL (e.g. `https://sso.corp.example.com`) |
| `PingJwksUri` | Yes | Ping JWKS endpoint (e.g. `https://sso.corp.example.com/pf/JWKS`) |
| `PingAudience` | Yes | Expected `aud`/`azp`/`client_id` in Ping tokens |

### Completion hook parameters

| Parameter | Required | Description |
|---|---|---|
| `EnableCompletionHook` | Yes | `true` to deploy the hook |
| `CompletionHookMQHost` | Yes | RabbitMQ broker hostname |
| `CompletionHookMQPort` | No | AMQPS port (default: `5671`) |
| `CompletionHookMQVhost` | No | Virtual host (default: `/`) |
| `CompletionHookMQExchange` | No | Exchange name (default: empty = default exchange) |
| `CompletionHookMQRoutingKey` | No | Routing key (default: `idp.document.completed`) |
| `CompletionHookMQOAuthScope` | No | OAuth2 scope for broker auth |
| `CompletionHookPingTokenUrl` | Yes | Ping token endpoint (e.g. `https://sso.corp.example.com/as/token`) |
| `CompletionHookPingClientId` | Yes | Ping client ID for the hook |
| `CompletionHookPingClientSecretArn` | Yes | Secrets Manager ARN containing the Ping client secret |

---

## Updating an existing deployment

To enable enterprise features on an existing IDP stack, just update with the new parameters:

```bash
idp-cli deploy \
  --stack-name IDP \
  --region us-east-1 \
  --wait \
  --parameters "EnablePingAuth=true,PingIssuer=https://sso.corp.example.com,PingJwksUri=https://sso.corp.example.com/pf/JWKS,PingAudience=idp-api"
```

CloudFormation adds the new resources (authorizer Lambda, layer) and switches the API Gateway authorizer. Existing jobs and documents are unaffected.

---

## Disabling enterprise features

Set the parameters back to `false`:

```bash
--parameters "EnablePingAuth=false,EnableCompletionHook=false"
```

The API Gateway switches back to the Cognito authorizer. The enterprise Lambda resources are removed from the stack.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| 401 on all API calls | Ping JWKS unreachable from Lambda | Check Lambda SG allows outbound HTTPS to Ping |
| 401 with valid token | Audience mismatch | Ensure `PingAudience` matches `aud` or `azp` or `client_id` in the token |
| 403 on POST /jobs | Token has `jobs.read` but not `jobs.write` | Request token with `jobs.write` scope |
| Completion hook timeout | Lambda can't reach MQ broker | Check Lambda SG allows outbound to port 5671 |
| Completion hook "access refused" | RabbitMQ OAuth2 rejects the Ping token | Verify broker's OAuth2 backend has correct `issuer`/JWKS and scope mapping |
| No hook invocation | `EnableCompletionHook=true` but no document processed | Submit a document and wait for completion; check EventBridge rule exists |
