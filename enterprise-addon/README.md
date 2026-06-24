# Enterprise Integration Add-on

Enterprise extensions for the IDP accelerator that enable VPC-only system integration without modifying upstream core logic.

## What it solves

In a fully private (no-internet-egress) VPC deployment, two things break:

1. **Jobs API authorization** — The upstream Jobs API uses Cognito M2M (client-credentials via `ApiUserPoolDomain`'s `/oauth2/token`). Cognito's OAuth domain **does not work over PrivateLink**. External systems cannot obtain tokens.

2. **Completion notification** — There is no built-in mechanism to notify external systems when a document workflow completes. Customers need to know when results are ready so they can retrieve them programmatically.

## Solution

### 1. Ping JWT API Authorization (`EnablePingAuth=true`)

Replaces the Cognito authorizer on the Jobs API with a **PingFederate REQUEST Lambda authorizer**. External systems authenticate directly with PingFederate (deployed in-VPC, privately reachable) using OAuth2 client-credentials, then call the Jobs API with the resulting JWT.

```
External System
  │  1. POST /token (client_credentials) → PingFederate (in-VPC)
  │  2. Receives Ping JWT
  │
  │  Authorization: Bearer <Ping JWT>
  ▼
Private API Gateway
  │  Ping REQUEST authorizer validates JWT (signature, issuer, audience, scopes)
  │  Enforces jobs.read / jobs.write by HTTP method
  ▼
Jobs API Handler (unchanged)
  POST /jobs        → submit documents (requires jobs.write)
  GET  /jobs/{id}   → check status / retrieve results (requires jobs.read)
```

**What changes:** Only the authorizer. The Jobs API handler, DynamoDB tracking, S3 buckets, and processing pipeline are untouched.

**Scope enforcement:** GET requests require `jobs.read`; POST/PUT/PATCH/DELETE require `jobs.write`. A token with `jobs.write` also satisfies `jobs.read`. Scopes can be plain (`jobs.read`) or namespaced (`idp-api/jobs.read`).

### 2. Completion Hook → Amazon MQ (`EnableCompletionHook=true`)

Deploys a Lambda that fires after each document workflow completes and publishes a notification to **Amazon MQ for RabbitMQ**. Auth to the broker is M2M via PingFederate — the hook presents a Ping client-credentials JWT that RabbitMQ's OAuth2 backend validates.

```
Step Functions SUCCEEDED
  └─ EventBridge rule
       └─ PostProcessingDecompressor (upstream, decompresses document)
            └─ CompletionHook Lambda (this add-on)
                 1. POST Ping /token (client_credentials) → Ping JWT
                 2. AMQPS connect to RabbitMQ (JWT as AMQP password)
                 3. Publish message to configured exchange/routing key
```

**Message shape:**
```json
{
  "document_id": "loan-app-123",
  "status": "SUCCEEDED",
  "num_pages": 4,
  "results_location": "s3://output-bucket/loan-app-123/results.json",
  "execution_arn": "arn:aws:states:us-east-1:123456789:execution:...",
  "completed_at": "2026-06-24T10:00:00Z"
}
```

**Idempotency:** `message_id` on the AMQP message = the Step Functions execution ARN (unique per run), so retries are de-dupable by idempotent consumers.

## Prerequisites

### For Ping Auth

- **PingFederate** deployed in-VPC (or reachable from VPC via network path)
- A Ping OAuth2 client configured with `client_credentials` grant, issuing tokens with `jobs.read` / `jobs.write` scopes
- VPC endpoint for `execute-api` (already required by `EnableHeadless=true`)
- Lambda security group must have outbound access to Ping's JWKS endpoint

### For Completion Hook

- **Amazon MQ for RabbitMQ** broker with the [OAuth 2.0 backend](https://www.rabbitmq.com/docs/oauth2) enabled:
  - `issuer` / JWKS pointing at PingFederate
  - Scopes mapped to RabbitMQ permissions (e.g. `idp-mq.write:%2F/idp-events`)
- A **Ping client** (client-credentials) for the hook, with scopes that grant publish permission on the target exchange
- Client secret stored in **Secrets Manager**
- Lambda security group must reach the broker (AMQPS port 5671) and the Ping token endpoint

## Deploy

Standard IDP deployment with additional parameters:

```bash
idp-cli deploy --stack-name IDP --admin-email admin@example.com \
  --parameters "\
EnableHeadless=true,\
DeployInVPC=true,\
VpcId=vpc-xxx,\
PrivateSubnetIds=subnet-a,subnet-b,\
LambdaSecurityGroupId=sg-xxx,\
ApiGatewayVpcEndpointId=vpce-xxx,\
EnablePingAuth=true,\
PingIssuer=https://sso.corp.example.com,\
PingJwksUri=https://sso.corp.example.com/pf/JWKS,\
PingAudience=idp-api,\
EnableCompletionHook=true,\
CompletionHookMQHost=b-xxxx.mq.us-east-1.amazonaws.com,\
CompletionHookMQExchange=idp-events,\
CompletionHookMQRoutingKey=idp.document.completed,\
CompletionHookMQOAuthScope=idp-mq.write:%2F/idp-events,\
CompletionHookPingTokenUrl=https://sso.corp.example.com/as/token,\
CompletionHookPingClientId=idp-completion-hook,\
CompletionHookPingClientSecretArn=arn:aws:secretsmanager:us-east-1:123456789:secret:ping/mq-client"
```

**One deploy, one stack.** Both features are default-off — deploying without the enterprise parameters behaves identically to upstream.

### Feature combinations

| EnablePingAuth | EnableCompletionHook | Result |
|---|---|---|
| false | false | Standard upstream behavior (Cognito M2M auth, no hook) |
| true | false | Jobs API uses Ping auth; no completion notification |
| false | true | Jobs API uses Cognito auth; hook publishes to MQ on completion |
| true | true | Full enterprise: Ping auth + MQ completion notification |

## Parameters reference

### Ping Auth

| Parameter | Required when | Description |
|---|---|---|
| `EnablePingAuth` | — | `true` to enable Ping auth on Jobs API |
| `PingIssuer` | EnablePingAuth=true | Ping OIDC issuer URL |
| `PingJwksUri` | EnablePingAuth=true | Ping JWKS endpoint |
| `PingAudience` | EnablePingAuth=true | Expected `aud`/`azp`/`client_id` in tokens |

### Completion Hook

| Parameter | Required when | Description |
|---|---|---|
| `EnableCompletionHook` | — | `true` to deploy the hook |
| `CompletionHookMQHost` | EnableCompletionHook=true | RabbitMQ broker hostname |
| `CompletionHookMQPort` | — | AMQPS port (default: 5671) |
| `CompletionHookMQVhost` | — | Virtual host (default: /) |
| `CompletionHookMQExchange` | — | Exchange name (default: empty = default exchange) |
| `CompletionHookMQRoutingKey` | — | Routing key (default: idp.document.completed) |
| `CompletionHookMQOAuthScope` | — | OAuth2 scope for broker auth |
| `CompletionHookPingTokenUrl` | EnableCompletionHook=true | Ping token endpoint |
| `CompletionHookPingClientId` | EnableCompletionHook=true | Ping client ID |
| `CompletionHookPingClientSecretArn` | EnableCompletionHook=true | Secrets Manager ARN with client secret |

## End-to-end flow (both features enabled)

```
1. External system authenticates to PingFederate (client_credentials)
   → receives a Ping JWT with jobs.write scope

2. External system calls POST /jobs with Authorization: Bearer <JWT>
   → Ping authorizer validates → Jobs API creates job → returns presigned upload URL

3. External system uploads document to S3 via presigned URL
   → IDP processing pipeline runs (OCR → Classification → Extraction → Assessment)

4. On completion, CompletionHook fires:
   → fetches Ping token → publishes to RabbitMQ
   → external system receives notification from its MQ consumer

5. External system calls GET /jobs/{id} with Authorization: Bearer <JWT>
   → retrieves extraction results
```

## Project structure

```
enterprise-addon/
├── ping_authorizer/
│   ├── app.py              # REQUEST authorizer handler
│   └── scopes.py           # Scope enforcement logic (read/write by HTTP method)
├── completion_hook/
│   ├── app.py              # Lambda handler: parse → token → publish
│   ├── event.py            # EventBridge event → message payload (pure, no deps)
│   ├── mq_rabbitmq.py      # AMQPS publish with JWT as password
│   └── ping_token.py       # Ping client-credentials token fetcher
└── layers/
    ├── ping_verifier/
    │   ├── python/ping_verifier.py   # Shared JWT validation (PyJWT)
    │   └── requirements.txt          # PyJWT[crypto]==2.9.0
    └── pika/
        └── requirements.txt          # pika==1.3.2
```

## Security notes

- **No secrets in environment variables.** The Ping client secret is stored in Secrets Manager and fetched at runtime.
- **Token caching.** Both the authorizer (JWKS keys) and completion hook (Ping access token) cache per warm container to minimize network calls. Cached access tokens are refreshed 30s before expiry.
- **Scope enforcement is per-request.** Authorizer caching is disabled (`ReauthorizeEvery: 0`) so scope checks always evaluate against the exact HTTP method.
- **TLS everywhere.** JWKS fetched over HTTPS; broker connection is AMQPS (TLS).
