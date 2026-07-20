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
├── layers/                 # Lambda layer deps (built by build.sh)
├── registry/               # Private registry config (secrets setup + examples)
├── config-pipeline/        # Lightweight pipeline for document config promotion
├── environments/           # Per-environment deploy params (templates + .gitignored locals)
├── test-jobs-api/          # End-to-end Jobs API test scripts (PowerShell + Python)
├── docs/                   # Detailed guides (human + AI readable)
├── .ai/                    # AI agent knowledge base (memory + skills)
├── API.md                  # Jobs API reference for downstream consumers
├── REVIEW_GUIDE.md         # Code review checklist
├── build.sh                # Layer dependency installer
└── README.md               # This file
```

## Documentation

### For downstream developers

| Document | What it covers |
|---|---|
| [API.md](API.md) | Jobs API endpoint reference, authentication, request/response examples |
| [test-jobs-api/README.md](test-jobs-api/README.md) | How to run the end-to-end API test scripts |

### For operations / deployment

| Document | What it covers |
|---|---|
| [docs/deployment-guide.md](docs/deployment-guide.md) | Full AI-guided deployment walkthrough (publish, deploy, verify) |
| [docs/sdlc-pipeline-setup.md](docs/sdlc-pipeline-setup.md) | SDLC/CD pipeline setup (CodePipeline + CodeBuild) |
| [docs/private-registry-setup.md](docs/private-registry-setup.md) | Private artifact registry configuration (JFrog, CodeArtifact, Nexus) |
| [docs/completion-hook-auth.md](docs/completion-hook-auth.md) | Completion hook MQ auth setup (Ping OAuth2 + RabbitMQ) |
| [environments/README.md](environments/README.md) | Per-environment parameter management |
| [config-pipeline/README.md](config-pipeline/README.md) | Document configuration promotion pipeline |
| [registry/README.md](registry/README.md) | Private registry secrets + examples |

### For maintainers / fork management

| Document | What it covers |
|---|---|
| [docs/upstream-sync-guide.md](docs/upstream-sync-guide.md) | Conflict resolution rules, silent-breakage checks, post-merge checklist |
| [docs/enterprise-fork-proposal.md](docs/enterprise-fork-proposal.md) | Original proposal (historical context — decisions captured in `.ai/memory/`) |
| [REVIEW_GUIDE.md](REVIEW_GUIDE.md) | Design and code review checklist for enterprise features |

### For AI agents

| Path | What it covers |
|---|---|
| [.ai/README.md](.ai/README.md) | How to use the AI knowledge base |
| [.ai/memory/](,.ai/memory/) | Project state, decisions, architecture — read on every session start |
| [.ai/skills/](.ai/skills/) | Step-by-step task guides (upstream sync, deploy, test, new environment) |
