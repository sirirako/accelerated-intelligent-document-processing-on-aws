# Completion Hook Authentication Guide

## Overview

The completion hook Lambda publishes document processing results to a message broker (Amazon MQ / RabbitMQ) after each document completes. To connect to the broker, it needs an OAuth2 access token from PingFederate (or your organization's identity provider).

This document explains the available OAuth2 grant types, why **client_credentials** is the recommended approach, and how to configure it.

---

## OAuth2 Grant Types Explained

| Grant Type | Use Case | Credentials Involved | Security Level |
|------------|----------|---------------------|----------------|
| **Client Credentials** | Service-to-service (M2M) | Client ID + Client Secret only | Highest for M2M |
| **Resource Owner Password (ROPC)** | Legacy apps that can't redirect | Client ID + Secret + Username + Password | Low (deprecated) |
| **Authorization Code** | User-facing web/mobile apps | Browser redirect + user consent | Highest for users |
| **Authorization Code + PKCE** | Public clients (SPAs, mobile) | Browser redirect + code verifier | Highest for public clients |

---

## Why Client Credentials is the Right Choice

The completion hook is a **backend Lambda function** — it has no user, no browser, and no interactive session. It's a machine talking to another machine. Client Credentials is designed exactly for this:

### How Client Credentials Works

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  Lambda Function │────1───▶│  PingFederate   │         │   RabbitMQ      │
│  (Completion     │◀───2────│  (Token Server) │         │   (Message      │
│   Hook)          │────3──────────────────────────────▶│    Broker)      │
└─────────────────┘         └─────────────────┘         └─────────────────┘

1. POST /as/token.oauth2
   grant_type=client_credentials
   Authorization: Basic base64(client_id:client_secret)
   scope=mq:publish

2. Response: { "access_token": "eyJ...", "expires_in": 300 }

3. AMQP connect with token as password
```

**The Lambda identifies itself** — not a user. The token represents "this service is allowed to publish messages" rather than "this user is performing an action."

### Benefits

- **No user credentials stored** — only a service identity (client_id + secret)
- **Short-lived tokens** — automatically expire (typically 5 minutes)
- **Auditable** — every token issuance is logged with the client identity
- **MFA-compatible** — doesn't bypass any user security policies
- **Rotatable** — client secret can be rotated without affecting any user
- **Scoped** — token can be limited to only `mq:publish` (no broader access)

---

## Why NOT Resource Owner Password Credentials (ROPC)

ROPC requires sending a real user's username and password:

```
POST /as/token.oauth2
grant_type=password
client_id=xxx
client_secret=xxx
username=svc_account@company.com
password=P@ssw0rd123
```

### Problems

| Issue | Impact |
|-------|--------|
| **Deprecated in OAuth 2.1** | Will be removed from the standard; no future support guaranteed |
| **User password in Lambda** | Password stored in Secrets Manager and loaded into memory — wider blast radius if compromised |
| **No MFA** | Bypasses multi-factor authentication policies |
| **Password expiry** | User passwords expire per policy (90 days?) — Lambda breaks silently |
| **Account lockout** | Failed attempts can lock the service account, blocking all document processing |
| **Shared credential** | If the same service account is used elsewhere, rotating the password breaks multiple systems |
| **Audit confusion** | Token appears to be "user X doing action" when it's actually a Lambda — misleading audit trails |
| **Compliance risk** | Many security frameworks (SOC2, FedRAMP, NIST) flag ROPC as a finding |

---

## Configuration: Client Credentials (Recommended)

### Step 1: Request a Client from Your IdP Team

Ask your PingFederate administrator to create an OAuth2 client with:

- **Grant Type**: Client Credentials
- **Client Authentication**: Client Secret (Basic or Post)
- **Scopes**: Whatever your RabbitMQ OAuth2 plugin requires (e.g., `rabbitmq.write:*/<vhost>/<exchange>`)
- **Token Lifetime**: 300 seconds (5 minutes) is sufficient

You'll receive:
- **Client ID**: e.g., `idp-completion-hook`
- **Client Secret**: e.g., `a1b2c3d4-...`
- **Token Endpoint**: e.g., `https://auth.company.com/as/token.oauth2`

### Step 2: Store the Secret in AWS Secrets Manager

```bash
aws secretsmanager create-secret \
  --name "idp/completion-hook/ping-client" \
  --description "Ping OAuth2 client secret for IDP completion hook" \
  --secret-string '{"client_secret": "a1b2c3d4-..."}'
```

### Step 3: Deploy with Completion Hook Parameters

```yaml
parameters:
  EnableCompletionHook: "true"
  CompletionHookPingTokenUrl: https://auth.company.com/as/token.oauth2
  CompletionHookPingClientId: idp-completion-hook
  CompletionHookPingClientSecretArn: arn:aws:secretsmanager:us-east-1:123456789012:secret:idp/completion-hook/ping-client-AbCdEf
  CompletionHookMQOAuthScope: "rabbitmq.write:*/%2F/idp-exchange"
  CompletionHookMQHost: b-1234-5678.mq.us-east-1.amazonaws.com
  CompletionHookMQPort: "5671"
  CompletionHookMQVhost: /
  CompletionHookMQExchange: idp-exchange
  CompletionHookMQRoutingKey: idp.document.completed
```

### How the Token is Used

1. Lambda calls PingFederate token endpoint with `grant_type=client_credentials`
2. PingFederate validates the client and returns a JWT access token
3. Lambda connects to RabbitMQ using the JWT as the AMQP password
4. RabbitMQ's OAuth2 plugin validates the JWT and authorizes the publish
5. Token is cached in the Lambda container (reused until 30s before expiry)

---

## If Your Organization Requires ROPC

If your Ping/IAM team cannot provide a client_credentials grant (e.g., RabbitMQ requires user-scoped tokens for authorization), the completion hook can be configured for ROPC. However, we strongly recommend:

1. **Document the exception** — note why client_credentials was not possible
2. **Use a dedicated service account** — never a real person's credentials
3. **Disable password expiry** on the service account (or automate rotation)
4. **Monitor for lockouts** — alert if the service account gets locked
5. **Plan migration** — treat ROPC as temporary until the IdP supports M2M for this use case

### ROPC Configuration (Not Recommended)

This would require two secrets:
- Client credentials (client_id + client_secret)
- User credentials (username + password)

And an additional environment variable for the grant type override.

Contact the IDP accelerator team if you need ROPC support — it's not enabled by default.

---

## Comparison with Customer Sample Code

| Aspect | Customer Sample (ROPC) | Our Implementation (Client Credentials) |
|--------|----------------------|----------------------------------------|
| Grant type | `password` | `client_credentials` |
| Credentials | 4 values (client_id, client_secret, username, password) | 2 values (client_id, client_secret) |
| Secrets needed | 2 (pingcred.json + authcred.json) | 1 (client secret only) |
| Password encoding | Base64 in secret, decoded at runtime | N/A |
| Auth header | Credentials in POST body | Basic auth header |
| TLS verification | `verify=False` in sample (insecure) | System CA bundle (secure) |
| Token caching | None in sample | Cached with TTL |
| Error handling | `.raise_for_status()` only | Cached + timeout + structured errors |

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `401 Unauthorized` from token endpoint | Invalid client_id or secret | Verify the secret in Secrets Manager matches what Ping has |
| `403 Forbidden` from RabbitMQ | Token missing required scope | Check `CompletionHookMQOAuthScope` matches RabbitMQ's OAuth2 plugin config |
| `Connection refused` to MQ | Lambda not in VPC or security group blocks 5671 | Ensure `DeployInVPC=true` and SG allows outbound to MQ port |
| Token expired errors | Token not cached properly | Check Lambda cold start frequency — should auto-cache |
| `CERTIFICATE_VERIFY_FAILED` | Corporate CA not in Lambda trust store | This shouldn't happen with Amazon MQ; for self-hosted MQ, add CA cert |
