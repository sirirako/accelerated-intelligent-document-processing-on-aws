# IDP Enterprise Extensions

Enterprise deployment features for the GenAI IDP Accelerator. These extend the upstream with support for:

- **Private artifact registries** — Pull all dependencies from internal registries (JFrog, CodeArtifact, Nexus) instead of public sources
- **PingFederate API authorization** — External systems call the Jobs API authenticated via Ping JWT (replaces Cognito in VPC-only deployments)
- **Completion notifications** — Publishes to Amazon MQ (RabbitMQ) when document processing completes
- **Per-job configuration** — Callers specify which processing config version to use per submission

All features are optional and default-off. Deploying without enterprise parameters behaves identically to upstream.

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
│                                        │ Completion Hook  │───────────▶ MQ
│                                        │ (Ping OAuth2)    │   4. Publish
│                                        └──────────────────┘        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Deploy

```bash
# 1. Build enterprise layers (one-time before publish)
./enterprise/build.sh

# 2. Publish and deploy (same as upstream, with additional parameters)
idp-cli publish --source-dir . --region us-east-1
idp-cli deploy --stack-name IDP --template-url <URL> --parameters "..."
```

See [docs/deployment-guide.md](docs/deployment-guide.md) for the full walkthrough.

## Structure

```
enterprise/
├── ping_authorizer/        # Ping JWT Lambda authorizer (multi-issuer, role-based)
├── completion_hook/        # Amazon MQ publisher (Ping OAuth2 for broker auth)
├── layers/
│   ├── ping_verifier/      # PyJWT + shared JWT verification
│   └── pika/               # AMQP client for RabbitMQ
├── registry/               # Private registry config (secrets setup + examples)
├── docs/
│   ├── deployment-guide.md # Full AI-guided deployment walkthrough
│   └── upstream-sync-guide.md  # Conflict resolution when syncing from upstream
├── API.md                  # Jobs API reference for downstream consumers
├── build.sh                # Layer dependency installer
└── README.md               # This file
```

## Documentation

| Document | Audience |
|---|---|
| [API.md](API.md) | Downstream developers — endpoint reference, auth, examples |
| [docs/deployment-guide.md](docs/deployment-guide.md) | Operations — build, publish, deploy, verify |
| [docs/upstream-sync-guide.md](docs/upstream-sync-guide.md) | Maintainers — conflict resolution on upstream sync |
| [registry/README.md](registry/README.md) | Operations — private registry setup |
