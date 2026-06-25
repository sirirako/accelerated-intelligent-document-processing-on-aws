# Enterprise Integration — Deployment Guide

The enterprise integration deploys using the same `idp-cli` workflow as standard IDP. The only addition is one build script that installs layer dependencies before you publish.

## What's different from a standard deployment

| Step | Standard IDP | With enterprise integration |
|---|---|---|
| Setup | `make setup-venv && source .venv/bin/activate` | Same |
| **Build layers** | — | **`./enterprise-addon/build.sh`** (new, one-time) |
| Publish | `idp-cli publish ...` | Same (enterprise code is packaged automatically) |
| Deploy | `idp-cli deploy ... --parameters "..."` | Same, with additional enterprise parameters |

That's it. One extra script before publish, then the same commands you already use.

---

## Prerequisites

### From your identity team (PingFederate)

| What | Example |
|---|---|
| Ping issuer URL | `https://sso.corp.example.com` |
| Ping JWKS endpoint | `https://sso.corp.example.com/pf/JWKS` |
| Ping audience (client ID for the API) | `idp-api` |
| Ping OAuth2 client for the API | configured with `client_credentials` grant + `jobs.read`/`jobs.write` scopes |

### Additional for completion hook (from identity + messaging teams)

| What | Example |
|---|---|
| Ping token endpoint | `https://sso.corp.example.com/as/token` |
| Ping client ID for the hook | `idp-completion-hook` |
| Ping client secret | stored in Secrets Manager |
| RabbitMQ broker hostname | `b-xxxx.mq.us-east-1.amazonaws.com` |
| RabbitMQ OAuth2 backend | configured with Ping as issuer |

### Networking

- Lambda security group must allow outbound HTTPS to PingFederate (JWKS + token endpoints)
- Lambda security group must allow outbound to RabbitMQ broker port 5671 (if using completion hook)

---

## Deploy

### 1. Build enterprise layers (one-time, before publish)

```bash
./enterprise-addon/build.sh
```

This installs PyJWT and pika into the layer directories so SAM can package them.

### 2. Publish and deploy

Use whichever method you normally use:

**Option A — One-shot (build + publish + deploy):**

```bash
idp-cli deploy \
  --stack-name IDP \
  --from-code . \
  --admin-email admin@example.com \
  --region us-east-1 \
  --wait \
  --parameters "<ALL PARAMETERS>"
```

**Option B — Two-step (publish first, deploy separately):**

```bash
# Publish
idp-cli publish --source-dir . --region us-east-1

# Deploy (using the template URL printed by publish)
idp-cli deploy \
  --stack-name IDP \
  --template-url <TEMPLATE_URL> \
  --admin-email admin@example.com \
  --region us-east-1 \
  --wait \
  --parameters "<ALL PARAMETERS>"
```

### Enterprise parameters

Append these to your existing `--parameters` string (alongside your VPC/headless params):

**Ping auth:**
```
EnablePingAuth=true,PingIssuer=https://sso.corp.example.com,PingJwksUri=https://sso.corp.example.com/pf/JWKS,PingAudience=idp-api
```

**Completion hook (add to the above if needed):**
```
EnableCompletionHook=true,CompletionHookMQHost=b-xxxx.mq.us-east-1.amazonaws.com,CompletionHookMQExchange=idp-events,CompletionHookMQRoutingKey=idp.document.completed,CompletionHookMQOAuthScope=idp-mq.write:%2F/idp-events,CompletionHookPingTokenUrl=https://sso.corp.example.com/as/token,CompletionHookPingClientId=idp-completion-hook,CompletionHookPingClientSecretArn=arn:aws:secretsmanager:us-east-1:123456789012:secret:ping/mq-client
```

**Full example (VPC + headless + Ping auth + hook):**

```bash
idp-cli deploy \
  --stack-name IDP \
  --from-code . \
  --admin-email admin@example.com \
  --region us-east-1 \
  --wait \
  --parameters "DeployInVPC=true,VpcId=vpc-xxx,PrivateSubnetIds=subnet-a,subnet-b,LambdaSecurityGroupId=sg-xxx,EnableHeadless=true,ApiGatewayVpcEndpointId=vpce-xxx,EnablePingAuth=true,PingIssuer=https://sso.corp.example.com,PingJwksUri=https://sso.corp.example.com/pf/JWKS,PingAudience=idp-api,EnableCompletionHook=true,CompletionHookMQHost=b-xxxx.mq.us-east-1.amazonaws.com,CompletionHookMQExchange=idp-events,CompletionHookMQRoutingKey=idp.document.completed,CompletionHookMQOAuthScope=idp-mq.write:%2F/idp-events,CompletionHookPingTokenUrl=https://sso.corp.example.com/as/token,CompletionHookPingClientId=idp-completion-hook,CompletionHookPingClientSecretArn=arn:aws:secretsmanager:us-east-1:123456789012:secret:ping/mq-client"
```

> **Note:** The `--parameters` value must be a single unbroken line. No backslash `\` inside the quotes.

---

## Verify

### Ping auth

```bash
# Get a token from Ping
TOKEN=$(curl -s -X POST https://sso.corp.example.com/as/token \
  -d "grant_type=client_credentials&scope=jobs.read jobs.write" \
  -u "my-client-id:my-client-secret" | jq -r .access_token)

# Call the Jobs API
curl -s https://<api-id>-<vpce-id>.execute-api.us-east-1.amazonaws.com/beta/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"fileName": "test-document.zip"}'
```

Expected: 200 with `jobId` and presigned upload URL.

### Completion hook

1. Submit a document (API or Web UI)
2. Wait for processing to complete
3. Check your RabbitMQ consumer received the notification message

---

## Updating or disabling

**Enable on an existing stack:**
```bash
idp-cli deploy --stack-name IDP --region us-east-1 --wait \
  --parameters "EnablePingAuth=true,PingIssuer=...,PingJwksUri=...,PingAudience=..."
```

**Disable:**
```bash
idp-cli deploy --stack-name IDP --region us-east-1 --wait \
  --parameters "EnablePingAuth=false,EnableCompletionHook=false"
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| 401 on all API calls | Ping JWKS unreachable from Lambda | Check Lambda SG allows outbound HTTPS to Ping |
| 401 with valid token | Audience mismatch | Ensure `PingAudience` matches `aud`/`azp`/`client_id` in the token |
| 403 on POST /jobs | Token missing `jobs.write` scope | Request token with `jobs.write` scope |
| Hook timeout | Lambda can't reach MQ broker | Check Lambda SG allows outbound to port 5671 |
| Hook "access refused" | RabbitMQ OAuth2 rejects Ping token | Verify broker's OAuth2 backend has correct issuer/JWKS + scope mapping |
| No hook fires | No document processed yet | Submit a document and wait for completion |

---

## Parameters reference

### Ping auth

| Parameter | Required | Description |
|---|---|---|
| `EnablePingAuth` | Yes | `true` to enable |
| `PingIssuer` | Yes | Ping OIDC issuer URL |
| `PingJwksUri` | Yes | Ping JWKS endpoint |
| `PingAudience` | Yes | Expected audience in Ping tokens |

### Completion hook

| Parameter | Required | Description |
|---|---|---|
| `EnableCompletionHook` | Yes | `true` to enable |
| `CompletionHookMQHost` | Yes | RabbitMQ broker hostname |
| `CompletionHookMQPort` | No | Default: `5671` |
| `CompletionHookMQVhost` | No | Default: `/` |
| `CompletionHookMQExchange` | No | Default: empty (default exchange) |
| `CompletionHookMQRoutingKey` | No | Default: `idp.document.completed` |
| `CompletionHookMQOAuthScope` | No | OAuth2 scope for broker auth |
| `CompletionHookPingTokenUrl` | Yes | Ping token endpoint |
| `CompletionHookPingClientId` | Yes | Ping client ID |
| `CompletionHookPingClientSecretArn` | Yes | Secrets Manager ARN with client secret |
