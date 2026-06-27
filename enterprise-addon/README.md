# Enterprise Integration Add-on

This add-on enables external systems to integrate with the IDP accelerator programmatically — submitting documents, receiving completion notifications, and retrieving results — all within a private network, authenticated via your corporate identity provider (PingFederate).

## What it provides

1. **API authorization via PingFederate** — External systems (e.g. loan origination, claims management, case management) authenticate with your existing PingFederate using standard OAuth2 client-credentials, then call the IDP Jobs API with the resulting token. No separate credential management needed — you use the same identity infrastructure you already have.

2. **Completion notifications via Amazon MQ** — When a document finishes processing, IDP automatically publishes a message to your RabbitMQ broker. Your downstream systems subscribe and react immediately — no polling required.

## How it fits together

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Your Environment                                 │
│                                                                     │
│  ┌──────────────┐         ┌──────────────┐         ┌────────────┐  │
│  │ Your App     │         │ PingFederate │         │ Amazon MQ  │  │
│  │ (API client) │         │ (IdP)        │         │ (RabbitMQ) │  │
│  └──────┬───────┘         └──────┬───────┘         └─────▲──────┘  │
│         │                        │                       │          │
│         │  1. Get token          │                       │          │
│         │───────────────────────▶│                       │          │
│         │◀───────────────────────│                       │          │
│         │     JWT                │                       │          │
│         │                        │                       │          │
└─────────┼────────────────────────┼───────────────────────┼──────────┘
          │                        │                       │
          │  2. POST /jobs         │                       │
          │     (Bearer JWT)       │                       │
          ▼                        │                       │
┌─────────────────────────────────────────────────────────────────────┐
│                     IDP Accelerator (AWS)                            │
│                                                                     │
│  ┌──────────────┐    ┌───────────┐    ┌──────────────────────────┐  │
│  │ API Gateway  │───▶│ Jobs API  │───▶│ Processing Pipeline      │  │
│  │ (Ping auth)  │    │ Handler   │    │ OCR → Classify → Extract │  │
│  └──────────────┘    └───────────┘    └────────────┬─────────────┘  │
│                                                    │                │
│                                                    │ 3. On complete │
│                                                    ▼                │
│                                        ┌──────────────────┐        │
│                                        │ Completion Hook  │────────────▶ MQ
│                                        │ (Ping OAuth2)    │   4. Publish
│                                        └──────────────────┘        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

1. Your application gets a token from PingFederate (standard OAuth2 client-credentials)
2. Calls the IDP Jobs API with that token to submit documents
3. IDP processes the documents (OCR, classification, extraction, assessment)
4. On completion, IDP publishes a notification to your RabbitMQ broker
5. Your application receives the notification and retrieves results via `GET /jobs/{id}`

## Solution

### 1. Ping JWT API Authorization (automatic with `EnableHeadless=true`)

When the headless Jobs API is enabled, it uses a **PingFederate Lambda authorizer** — no Cognito OAuth domain is involved (which doesn't work over PrivateLink). External systems authenticate with PingFederate and call the Jobs API with the resulting JWT.

The authorizer supports:
- **Multiple issuers** — configure up to two Ping environments (e.g. dev + prod, or two separate Ping instances)
- **Role/group-based access** — validates that the token's `userRoles` or `memberOf` claim contains at least one of the required roles
- **Multiple token formats** — accepts `Authorization: Bearer`, `Fhlmcjwt` header, or `x-jwt-token` header
- **RS256, ES256, HS256** signing algorithms

```
External System
  │  1. Authenticate with PingFederate (client_credentials or user login)
  │  2. Receives Ping JWT (with userRoles/memberOf claims)
  │
  │  Authorization: Bearer <Ping JWT>
  ▼
Private API Gateway
  │  Lambda authorizer:
  │    • Resolves signing key from JWKS (tries each configured issuer)
  │    • Validates JWT signature + issuer
  │    • Checks required roles in userRoles/memberOf claims
  │    • Returns Allow for all API methods if valid
  ▼
Jobs API Handler (unchanged)
  POST /jobs        → submit documents
  GET  /jobs/{id}   → check status / retrieve results
```

**What changes:** Only the authorizer. The Jobs API handler, DynamoDB tracking, S3 buckets, and processing pipeline are untouched.

**Authorization model:** If the token is valid (signature, issuer) and the user has at least one of the required roles → full access to all Jobs API methods. If `PingRequiredRoles` is left empty, any valid token is allowed (role check is skipped).

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
