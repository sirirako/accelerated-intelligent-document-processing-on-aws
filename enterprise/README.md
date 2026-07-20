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

All actionable guides live in `.ai/skills/` — usable by both humans and AI agents.

### For downstream developers

| Guide | What it covers |
|---|---|
| [API.md](API.md) | Jobs API endpoint reference, authentication, request/response examples |
| [test-jobs-api/README.md](test-jobs-api/README.md) | How to run the end-to-end API test scripts |

### For operations / deployment

| Guide | What it covers |
|---|---|
| [.ai/skills/deploy.md](.ai/skills/deploy.md) | Build, publish, deploy with enterprise params |
| [.ai/skills/new-environment.md](.ai/skills/new-environment.md) | Set up a new environment from scratch |
| [.ai/skills/pipeline-setup.md](.ai/skills/pipeline-setup.md) | SDLC/CD pipeline setup (CodePipeline + CodeBuild) |
| [.ai/skills/private-registry.md](.ai/skills/private-registry.md) | Private artifact registry (JFrog, CodeArtifact, Nexus) |
| [.ai/skills/completion-hook.md](.ai/skills/completion-hook.md) | Completion hook MQ auth (Ping OAuth2 + RabbitMQ) |
| [environments/README.md](environments/README.md) | Per-environment parameter management |
| [config-pipeline/README.md](config-pipeline/README.md) | Document configuration promotion pipeline |
| [docs/deployment-guide.md](docs/deployment-guide.md) | Full AI-guided deployment walkthrough (interactive prompt template) |

### For maintainers / fork management

| Guide | What it covers |
|---|---|
| [.ai/skills/upstream-sync.md](.ai/skills/upstream-sync.md) | Conflict resolution rules, silent-breakage checks, post-merge checklist |
| [.ai/skills/code-review.md](.ai/skills/code-review.md) | Design and code review checklist |
| [docs/enterprise-fork-proposal.md](docs/enterprise-fork-proposal.md) | Original proposal (historical context) |

### AI agent knowledge base

| Path | What it covers |
|---|---|
| [.ai/README.md](.ai/README.md) | How to use the knowledge base |
| [.ai/memory/](.ai/memory/) | Project state, decisions, architecture — read on every session start |
| [.ai/skills/](.ai/skills/) | All guides above + test-api, new-environment |
