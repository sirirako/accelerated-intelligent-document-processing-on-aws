# Completion Hook — ActiveMQ with Ping OAuth2 (ROPC)

## Overview

The completion hook Lambda publishes document processing results to ActiveMQ after
each document completes. Authentication uses PingFederate ROPC grant (AD credentials)
to get a JWT, which is passed as the STOMP passcode to the broker's OAuth2 backend.

## Flow

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  Lambda Function │         │  Secrets Manager │         │  PingFederate   │
│  (Completion     │────1───▶│  (AD user/pass + │         │  (Token Server) │
│   Hook)          │◀───────│   client secret) │         │                 │
│                  │────2──────────────────────────────▶│                 │
│                  │◀───────────────────────────────────│  JWT            │
│                  │                                     └─────────────────┘
│                  │────3───▶┌─────────────────┐
│                  │         │  ActiveMQ        │
└─────────────────┘         │  (STOMP+SSL      │
                            │   port 61617)    │
                            └─────────────────┘

1. Read AD username, password, client secret from Secrets Manager
2. POST /as/token.oauth2 (grant_type=password, client_id, client_secret, username, password)
3. STOMP CONNECT (login="", passcode=JWT) → SEND message
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `EnableCompletionHook` | Yes | `false` | Enable the hook |
| `CompletionHookMQHost` | Yes | — | ActiveMQ broker hostname |
| `CompletionHookMQPort` | No | `61617` | SSL port |
| `CompletionHookMQDestination` | No | `/queue/idp.document.completed` | Queue or topic |
| `CompletionHookPingTokenUrl` | Yes | — | Ping token endpoint |
| `CompletionHookPingClientId` | Yes | — | OAuth2 client ID |
| `CompletionHookPingClientSecretArn` | Yes | — | Secrets Manager ARN: client secret |
| `CompletionHookPingUsernameSecretArn` | Yes | — | Secrets Manager ARN: AD username |
| `CompletionHookPingPasswordSecretArn` | Yes | — | Secrets Manager ARN: AD password |
| `CompletionHookPingScope` | No | — | OAuth2 scope (optional) |
| `CompletionHookPingValidatorId` | No | — | Ping password validator ID (optional) |

## Secrets Manager setup

```bash
# Client secret
aws secretsmanager create-secret \
  --name "idp/completion-hook/client-secret" \
  --secret-string '<client-secret-value>'

# AD username
aws secretsmanager create-secret \
  --name "idp/completion-hook/username" \
  --secret-string '<ad-service-account-username>'

# AD password
aws secretsmanager create-secret \
  --name "idp/completion-hook/password" \
  --secret-string '<ad-service-account-password>'
```

## Pipeline config example

```yaml
parameters:
  EnableCompletionHook: "true"
  CompletionHookPingTokenUrl: https://ping.example.com/as/token.oauth2
  CompletionHookPingClientId: idp-mq-client
  CompletionHookPingClientSecretArn: arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:idp/completion-hook/client-secret-xxx
  CompletionHookPingUsernameSecretArn: arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:idp/completion-hook/username-xxx
  CompletionHookPingPasswordSecretArn: arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:idp/completion-hook/password-xxx
  CompletionHookPingScope: edit
  CompletionHookPingValidatorId: FHLMCPCV
  CompletionHookMQHost: amq-broker.internal.example.com
  CompletionHookMQPort: "61617"
  CompletionHookMQDestination: /queue/idp.document.completed
```

## Testing (without deploying)

```bash
# Install deps
pip install stomp.py boto3

# Copy config
cp enterprise/test-jobs-api/env_activemq.example enterprise/test-jobs-api/.env_activemq
# Edit with real values

# Run test
python enterprise/test-jobs-api/test_activemq.py

# Or with pre-fetched token
python enterprise/test-jobs-api/test_activemq.py --token <jwt> --host amq-broker.example.com
```

## Lambda layer

The completion hook uses the `EnterprisePikaLayer` (name is legacy — actually contains `stomp.py`).
Layer requirements: `enterprise/layers/pika/requirements.txt` → `stomp.py==8.2.0`

## TLS / CA cert

- Ping token endpoint: uses `CA_CERT_PATH` env var (same as Ping authorizer)
- ActiveMQ broker: uses `MQ_CA_CERT_PATH` env var
- Set `MQ_DISABLE_HOST_VERIFY=true` if broker hostname doesn't match cert (e.g. `verifyHostName=false` in their connection URL)

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `401` from Ping token endpoint | Invalid credentials | Check all 4 secrets in Secrets Manager |
| STOMP connection refused | Wrong port or protocol | Verify broker supports STOMP on 61617 (auto-detect) |
| `CERTIFICATE_VERIFY_FAILED` on token | TLS inspection | Set CA_CERT_PATH to corporate CA bundle |
| `CERTIFICATE_VERIFY_FAILED` on broker | TLS inspection | Set MQ_CA_CERT_PATH or MQ_DISABLE_HOST_VERIFY=true |
| Message not appearing in queue | Wrong destination | Check destination format: `/queue/name` or `/topic/name` |
| Lambda timeout | Broker unreachable | Check VPC security group allows outbound to port 61617 |
| Password expiry | AD password rotated | Update Secrets Manager value |
