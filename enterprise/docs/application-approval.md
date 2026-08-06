# GenAI IDP — Application Architecture Document

**Application Name:** GenAI Intelligent Document Processing (GenAI IDP)
**Document Version:** 1.0
**Date:** July 2026
**Classification:** Internal
**Author:** AWS Professional Services / Customer Engineering Team

---

## Table of Contents

1. [DOCUMENT SCOPE](#1-document-scope)
   - 1.1 [Executive Summary](#11-executive-summary)
   - 1.2 [Architectural Assumptions and Constraints](#12-architectural-assumptions-and-constraints)
   - 1.3 [Architectural Decisions](#13-architectural-decisions)
   - 1.4 [Future Architecture](#14-future-architecture)
   - 1.5 [Related Applications](#15-related-applications)
   - 1.6 [Change Log](#16-change-log)
2. [MODELS](#2-models)
   - 2.1 [Information Model](#21-information-model)
   - 2.2 [Application Model](#22-application-model)
   - 2.3 [Deployment Model](#23-deployment-model)
   - 2.4 [Security Model](#24-security-model)
     - 2.4.1 [Components List](#241-components-list)
     - 2.4.2 [Connection List](#242-connection-list)
     - 2.4.3 [Description of Security](#243-description-of-security)
3. [ARCHITECTURE OBSERVATIONS](#3-architecture-observations)
4. [REFERENCES](#4-references)

---

## 1 DOCUMENT SCOPE

### 1.1 Executive Summary

**GenAI IDP** (Intelligent Document Processing) is a serverless document processing platform deployed on Amazon Web Services (AWS) that automates the extraction of structured data from unstructured documents. The system combines Optical Character Recognition (OCR) with generative AI (Amazon Bedrock large language models) to classify documents by type, extract key-value fields, assess extraction confidence, validate against business rules, and deliver structured JSON outputs.

**Business Purpose:** Enable automated straight-through processing of document-intensive workflows (e.g., loan origination, compliance review) by replacing manual data entry and document classification with AI-driven automation.

**Key Capabilities:**
- Automated multi-page document splitting and classification
- AI-powered field extraction with configurable schemas
- Confidence assessment and human-in-the-loop review for low-confidence results
- REST API (Jobs API) for machine-to-machine integration with external systems
- Event-driven completion notifications via Amazon MQ (ActiveMQ)
- Configuration versioning with per-job processing customization
- Built-in evaluation framework for accuracy measurement and regression testing

**Architecture Summary:** 100% serverless AWS deployment within a private VPC. No public endpoints. All user access (Web UI and API) via VPC Interface Endpoints. Authentication via PingFederate (federated through Amazon Cognito for the Web UI; custom Lambda authorizer for the Jobs API).

---

### 1.2 Architectural Assumptions and Constraints

| # | Assumption / Constraint | Type | Impact |
|---|------------------------|------|--------|
| A1 | Deployment is VPC-only; no public internet endpoints are permitted | Constraint | Drives API Gateway Private mode, VPC endpoint architecture |
| A2 | PingFederate is available as the enterprise identity provider and supports OIDC/SAML federation | Assumption | Required for both Web UI SSO and Jobs API M2M authentication |
| A3 | Amazon MQ (ActiveMQ) broker exists and is integrated with Active Directory | Assumption | Required for completion notification delivery |
| A4 | JFrog Artifactory is available as the approved internal artifact registry | Constraint | All build dependencies (pip, npm, Docker) must flow through JFrog — no public registry access |
| A5 | Amazon Bedrock model access has been granted for the target region (Claude, Titan models) | Assumption | Core extraction and classification depends on Bedrock model availability |
| A6 | No direct internet egress from the VPC for Lambda functions | Constraint | All AWS service access via VPC Interface/Gateway Endpoints |
| A7 | AWS CodeBuild projects run inside the VPC | Constraint | Build phase requires JFrog access for dependency resolution |
| A8 | Amazon ECR is used for container image storage with image scanning enabled | Constraint | All Lambda container images stored in ECR with vulnerability scanning |
| A9 | Single-tenant deployment model (one CloudFormation stack per environment) | Assumption | No cross-tenant data sharing concerns within a single stack |
| A10 | Cognito user pool OAuth domain must be reachable from user browsers (via VPN/DirectConnect) | Assumption | Web UI login flow requires browser access to Cognito hosted UI |

---

### 1.3 Architectural Decisions

| # | Decision | Rationale | Alternatives Considered |
|---|----------|-----------|------------------------|
| AD1 | **API Gateway for Web UI hosting** (replacing CloudFront) | VPC-only constraint prohibits public CDN endpoints. API Gateway serves both the Web UI (as S3 proxy) and the data API from a single private REST API stage — no CORS, VPC access inherited. | CloudFront (rejected: public endpoint), ALB + S3 VPC Endpoint (rejected: added complexity, required ACM certificate management) |
| AD2 | **Custom Ping Lambda authorizer for Jobs API** (not Cognito-only) | Machine-to-machine (M2M) integration requires OAuth 2.0 client credentials flow with PingFederate tokens. Cognito OAuth domain is not reachable via PrivateLink in VPC-only deployments. Custom authorizer validates Ping JWTs directly via JWKS. | Cognito-only (rejected: OAuth domain unreachable in VPC-only), IAM auth with SigV4 (rejected: requires AWS credentials for external systems) |
| AD3 | **Enterprise fork model** (additive-only, never modify upstream) | Enterprise requirements (private registries, Ping auth, MQ notifications) vary significantly by customer and are deployment/integration concerns, not core processing logic. Keeping them in an isolated `enterprise/` directory enables clean weekly upstream merges and continuous delivery of upstream improvements. | Monolithic fork (rejected: merge conflicts, upstream divergence), Feature flags in upstream (rejected: upstream release cycle too slow for enterprise needs) |
| AD4 | **Amazon MQ (ActiveMQ) for completion notifications** | Customer's existing messaging infrastructure uses ActiveMQ integrated with Active Directory. Push-based notifications eliminate polling and integrate with established operational patterns. | Amazon SNS/SQS (rejected: no existing consumer infrastructure), Polling-only via GET /jobs (rejected: adds latency, requires client-side scheduling) |
| AD5 | **Amazon Cognito with PingFederate federation for Web UI** | Provides standard OIDC/SAML federation flow for human users, leveraging existing corporate SSO while maintaining Cognito's built-in session management, RBAC group mapping, and token lifecycle. | Direct Ping auth in browser (rejected: no built-in session management), Custom auth backend (rejected: unnecessary complexity) |
| AD6 | **Presigned URLs for document upload/download** | Avoids routing document bytes through Lambda functions; S3 direct upload reduces latency, eliminates payload size limits, and reduces cost. Time-limited (1 hour) and scoped to specific job prefix. | Multipart upload through API Gateway (rejected: 10MB payload limit, increased Lambda cost) |

---

### 1.4 Future Architecture

| # | Planned Enhancement | Timeline | Impact |
|---|-------------------|----------|--------|
| F1 | **Bedrock Data Automation (BDA) mode maturation** | Available now (opt-in) | Simplified processing pipeline — BDA handles OCR + extraction in a single managed service call. Reduces pipeline complexity for supported document types. |
| F2 | **MCP (Model Context Protocol) connector** | Upstream available | Enables external AI applications (e.g., Amazon Q, third-party agents) to access IDP data and analytics through Bedrock AgentCore Gateway. |
| F3 | **AgentCore sandboxed execution** | Upstream available | Adds multi-agent AI analysis capabilities with secure Python code execution for interactive document analytics. |
| F4 | **Bedrock Knowledge Base integration** | Upstream available | Semantic document querying — ask natural language questions about processed documents using RAG (Retrieval Augmented Generation). |
| F5 | **Human-in-the-loop (HITL) review integration** | Upstream available | Built-in review workflow for human validation of low-confidence extractions before results are finalized. |
| F6 | **Cross-account Bedrock support** | Upstream available | Route inference to a centralized Bedrock account, supporting organizations with shared AI governance. |

---

### 1.5 Related Applications

| Application | Relationship | Integration Point | Direction |
|-------------|-------------|-------------------|-----------|
| **Loan Origination System (LOS)** | Primary consumer | Jobs API (POST /jobs, GET /jobs/{id}) | LOS → IDP (submit docs), IDP → LOS (results) |
| **PingFederate** | Identity Provider | OIDC federation (Cognito), JWKS validation (Jobs API authorizer) | Ping → IDP (tokens, JWKS) |
| **Amazon MQ (ActiveMQ)** | Notification broker | Completion hook Lambda → ActiveMQ exchange | IDP → ActiveMQ (completion events) |
| **Active Directory** | Broker authentication | ActiveMQ broker auth backend | AD ↔ ActiveMQ |
| **JFrog Artifactory** | Artifact registry | CodeBuild install phase (pip, npm, Docker) | CodeBuild → JFrog (build dependencies) |
| **Bitbucket** | Source control | CodePipeline source stage (via S3 sync) | Bitbucket → S3 → CodePipeline |
| **Amazon ECR** | Container registry | Lambda container image storage + vulnerability scanning | CodeBuild → ECR (push), Lambda → ECR (pull) |

---

### 1.6 Change Log

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| 1.0 | July 2026 | AWS Professional Services | Initial document for production approval |

---

## 2 MODELS

### 2.1 Information Model

#### Data Entities

| Entity | Storage | Description | Retention |
|--------|---------|-------------|-----------|
| **Input Documents** | S3 (Input Bucket) | Original uploaded documents (PDF, images, ZIP archives) | Configurable via S3 lifecycle policy |
| **Processing Results** | S3 (Output Bucket) | Structured extraction JSON, page images, OCR text per document | Configurable via S3 lifecycle policy |
| **Job Records** | DynamoDB | Job metadata: ID, status, timestamps, configuration version, client ID | Indefinite (operational) |
| **Document Tracking** | DynamoDB | Per-document processing state, version history, section results | Indefinite (operational) |
| **Configuration** | DynamoDB | Processing configurations: extraction schemas, prompts, classification rules, validation logic | Versioned (all versions retained) |
| **User Sessions** | Cognito + DynamoDB | Authentication tokens, user preferences, conversation history | Token TTL: 1 hour access, configurable refresh |
| **Audit Logs** | CloudWatch Logs / CloudTrail | API access logs, Lambda execution logs, AWS API call history | Configurable retention (default: 90 days) |
| **Metrics** | CloudWatch Metrics | Processing latency, error rates, queue depth, Bedrock token usage | 15 months (standard CloudWatch retention) |
| **Evaluation Data** | S3 + Athena (Glue Catalog) | Accuracy baselines, evaluation results, comparison reports | Indefinite (analytics) |

#### Data Lifecycle

```
Document Submission → S3 Input Bucket → Processing Pipeline → S3 Output Bucket → Result Retrieval
                                                                                        ↓
                                                                          (Presigned URL, 1hr TTL)
                                                                                        ↓
                                                                              External System
```

1. **Ingestion**: Document uploaded to S3 via presigned URL (Jobs API) or direct S3 upload (Web UI)
2. **Processing**: Document traverses pipeline stages; intermediate results stored in S3
3. **Storage**: Final structured results persisted in S3 Output Bucket + DynamoDB tracking
4. **Delivery**: Results retrieved via presigned download URL (1-hour expiration)
5. **Archival/Deletion**: Governed by S3 lifecycle policies (configurable per environment)

#### Data Classification

| Data Type | Classification | Handling |
|-----------|---------------|----------|
| Uploaded documents | Confidential (may contain PII) | Encrypted at rest (SSE-KMS), in transit (TLS 1.2+) |
| Extracted fields | Confidential (contains PII) | Encrypted at rest, time-limited presigned URLs for retrieval |
| Processing configuration | Internal | Encrypted at rest, RBAC-controlled access |
| Audit logs | Internal | CloudWatch encryption, configurable retention |
| Authentication tokens | Sensitive | Short-lived (1 hour), HTTPS-only transmission |

---

### 2.2 Application Model

#### Core Infrastructure Services

| Service | Usage | Deployment | Runtime |
|---------|-------|------------|---------|
| **Amazon S3** | Input/output document storage, Web UI static assets, configuration storage | ✓ | ✓ |
| **Amazon DynamoDB** | Document tracking, configuration management, concurrency control, conversations | ✓ | ✓ |
| **AWS Lambda** | All processing logic (50+ functions): OCR, classification, extraction, assessment, API handlers | ✓ | ✓ |
| **AWS Step Functions** | Orchestrates multi-step document processing workflow with error handling and retries | ✓ | ✓ |
| **Amazon SQS** | Document queuing, throttling, backpressure management | ✓ | ✓ |
| **Amazon EventBridge** | S3 upload event routing, Step Functions status tracking | ✓ | ✓ |
| **Amazon API Gateway** | Private REST API: Jobs API (custom Ping authorizer), Web UI hosting (S3 proxy), Web UI data API (Cognito auth) | ✓ | ✓ |
| **Amazon ECR** | Container images for Lambda functions (OCR, classification, extraction) with image scanning | ✓ | ✓ |
| **AWS CloudFormation** | Infrastructure-as-Code deployment (nested stacks) | ✓ | |
| **AWS CodeBuild** | Builds container images, Lambda layers, Web UI assets (runs in VPC) | ✓ | |
| **AWS Systems Manager (Parameter Store)** | Runtime configuration parameters | ✓ | ✓ |

#### AI/ML Services

| Service | Usage | Deployment | Runtime |
|---------|-------|------------|---------|
| **Amazon Bedrock** | Foundation models (Claude, Titan) for classification, extraction, assessment, summarization | ✓ | ✓ |
| **Amazon Bedrock Guardrails** | Content safety, PII detection, topic denial policies | ✓ | ✓ |
| **Amazon Textract** | OCR text and table extraction (Pipeline mode) | | ✓ |
| **Bedrock Data Automation (BDA)** | Integrated document processing (BDA mode, optional) | ✓ | ✓ |

#### Authentication & API Services

| Service | Usage | Deployment | Runtime |
|---------|-------|------------|---------|
| **Amazon Cognito** | User pool for Web UI authentication (federated with PingFederate) | ✓ | ✓ |
| **Custom Lambda Authorizer** | PingFederate JWT validation for Jobs API (multi-issuer, role-based) | ✓ | ✓ |

#### Monitoring & Operations

| Service | Usage | Deployment | Runtime |
|---------|-------|------------|---------|
| **Amazon CloudWatch** | Monitoring (60+ alarms), logging, dashboards, alerting | ✓ | ✓ |
| **Amazon SNS** | Operational alert notifications | ✓ | ✓ |
| **AWS KMS** | Encryption key management for S3, DynamoDB | ✓ | ✓ |

#### Enterprise Integration Services

| Service | Usage | Deployment | Runtime |
|---------|-------|------------|---------|
| **Amazon MQ (ActiveMQ)** | Completion notification delivery (AD-integrated) | | ✓ |
| **AWS Secrets Manager** | PingFederate client secrets, JFrog credentials | ✓ | ✓ |
| **AWS CodePipeline** | CI/CD orchestration (source → build → deploy → validate) | ✓ | |

---

### 2.3 Deployment Model

#### Environment Topology

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     AWS Account (Single-Tenant)                           │
│                                                                          │
│  ┌─────────────┐    ┌──────────────────┐    ┌────────────────────────┐  │
│  │    DEV      │    │    STAGING       │    │    PRODUCTION          │  │
│  │  IDP Stack  │    │    IDP Stack     │    │    IDP Stack           │  │
│  │             │    │                  │    │                        │  │
│  │ Auto-deploy │    │ Manual approval  │    │ Manual approval        │  │
│  │ Test data   │    │ Prod-like data   │    │ Live workload          │  │
│  └─────────────┘    └──────────────────┘    └────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                    Shared Infrastructure                             │  │
│  │  VPC + Subnets + VPC Endpoints + Security Groups                    │  │
│  │  CodePipeline + CodeBuild (SDLC)                                    │  │
│  │  JFrog Artifactory (internal registry)                              │  │
│  │  Amazon MQ (ActiveMQ) broker                                        │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

#### CI/CD Pipeline

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Source     │────▶│    Build     │────▶│    Deploy    │────▶│   Validate   │
│ (Bitbucket → │     │ (CodeBuild)  │     │ (CloudFmn)  │     │ (Smoke Test) │
│  S3 trigger) │     │  In-VPC      │     │             │     │              │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

| Phase | Details |
|-------|---------|
| **Source** | Code synced from Bitbucket to S3 source bucket; upload triggers pipeline |
| **Build** | CodeBuild (in VPC): installs from JFrog, builds Lambda layers + container images (ECR), packages CloudFormation templates |
| **Deploy** | CloudFormation stack create/update with environment-specific parameters |
| **Validate** | Automated smoke test: document upload → process → retrieve → verify results |

#### Configuration Promotion (Separate Pipeline)

Document processing configurations (extraction prompts, classification schemas) have their own lightweight pipeline:

1. Configuration YAML files uploaded to S3 as config.zip
2. CodeBuild runs `idp-cli config-upload` for each config version
3. Configs pushed to target stack's DynamoDB — completes in seconds
4. No Docker build, no infrastructure stack update required

#### Rollback Strategy

| Scenario | Method |
|----------|--------|
| Infrastructure failure | CloudFormation automatic rollback to previous stack state |
| Bad configuration | Revert config version via `idp-cli config-upload` (instant) |
| Processing regression | Point `configurationVersion` to last-known-good version |
| Full rollback | Redeploy previous CloudFormation template URL |

---

### 2.4 Security Model

#### Overview

A comprehensive STRIDE-based threat model has been conducted identifying **62 threats** across all system components. Current mitigation status:

| Status | Count | Percentage |
|--------|-------|------------|
| **Mitigated** | 50 | 81% |
| **Partially Mitigated** | 7 | 11% |
| **Accepted** | 5 | 8% |

---

#### 2.4.1 Components List

| # | Component | Service | Version | Owner | Purpose |
|---|-----------|---------|---------|-------|---------|
| 1 | Document Input | Amazon S3 | Current | AWS (managed) | Receives uploaded documents via presigned URLs |
| 2 | Document Output | Amazon S3 | Current | AWS (managed) | Stores processing results, page images, OCR text |
| 3 | Web UI Assets | Amazon S3 | Current | AWS (managed) | Hosts React SPA static files |
| 4 | REST API | Amazon API Gateway | v2 (REST) | Customer Engineering | Private API: Jobs API + Web UI proxy + data operations |
| 5 | Jobs API Authorizer | AWS Lambda (Python 3.12) | Custom | AWS Account Team | Validates PingFederate JWTs via JWKS |
| 6 | Processing Pipeline | AWS Step Functions | Express/Standard | AWS (managed) | Orchestrates document workflow stages |
| 7 | OCR Processing | AWS Lambda (Container) | Custom | AWS GenAI IDP Team | Extracts text via Textract/Bedrock multimodal |
| 8 | Classification | AWS Lambda (Container) | Custom | AWS GenAI IDP Team | Classifies document types via Bedrock |
| 9 | Extraction | AWS Lambda (Container) | Custom | AWS GenAI IDP Team | Extracts structured fields via Bedrock |
| 10 | Assessment | AWS Lambda (Container) | Custom | AWS GenAI IDP Team | Confidence scoring via Bedrock |
| 11 | Rule Validation | AWS Lambda (Python 3.12) | Custom | AWS GenAI IDP Team | Business rule validation |
| 12 | Document Queue | Amazon SQS | Current | AWS (managed) | Queues documents, manages throughput |
| 13 | Event Router | Amazon EventBridge | Current | AWS (managed) | S3 upload events → processing trigger |
| 14 | Document Tracking | Amazon DynamoDB | On-demand | AWS (managed) | Job/document status, metadata |
| 15 | Configuration Store | Amazon DynamoDB | On-demand | AWS (managed) | Processing configs, versions |
| 16 | AI Inference | Amazon Bedrock | Current | AWS (managed) | LLM inference (Claude, Titan) |
| 17 | OCR Service | Amazon Textract | Current | AWS (managed) | Text/table extraction |
| 18 | User Authentication | Amazon Cognito | Current | AWS (managed) | User pool with Ping federation |
| 19 | Completion Hook | AWS Lambda (Python 3.12) | Custom | AWS Account Team | Publishes to ActiveMQ on workflow completion |
| 20 | Message Broker | Amazon MQ (ActiveMQ) | 5.x | Customer Business Unit | Receives completion notifications (AD-integrated) |
| 21 | Container Registry | Amazon ECR | Current | AWS (managed) | Lambda container images + vulnerability scanning |
| 22 | Secrets Store | AWS Secrets Manager | Current | AWS (managed) | Ping client secrets, JFrog credentials |
| 23 | Monitoring | Amazon CloudWatch | Current | AWS (managed) | Logs, metrics, 60+ alarms, dashboards |
| 24 | Encryption | AWS KMS | Current | AWS (managed) | Encryption keys for S3, DynamoDB |
| 25 | CI/CD Pipeline | AWS CodePipeline | v2 | Customer Engineering | Build → deploy → validate pipeline |
| 26 | Build Service | AWS CodeBuild | Current | AWS (managed) | In-VPC builds (images, layers, assets) |

---

#### 2.4.2 Connection List

| # | Source | Destination | Protocol | Port | Auth Method | Data Classification | Encryption |
|---|--------|-------------|----------|------|-------------|-------------------|------------|
| 1 | LOS (External) | API Gateway (Jobs API) | HTTPS | 443 | PingFederate JWT (custom authorizer) | Confidential (documents) | TLS 1.2+ |
| 2 | Browser (VPN) | API Gateway (Web UI) | HTTPS | 443 | Cognito JWT (federated with Ping) | Internal (UI interactions) | TLS 1.2+ |
| 3 | Browser (VPN) | Cognito Hosted UI | HTTPS | 443 | OIDC/SAML federation with Ping | Sensitive (credentials) | TLS 1.2+ |
| 4 | Browser (VPN) | S3 (presigned upload) | HTTPS | 443 | Presigned URL (time-limited) | Confidential (documents) | TLS 1.2+ |
| 5 | API Gateway | Lambda (Jobs Handler) | AWS internal | — | IAM role | Confidential | AWS encryption |
| 6 | API Gateway | S3 (Web UI proxy) | AWS internal | — | IAM role (WebUIProxyRole) | Internal (static assets) | AWS encryption |
| 7 | Lambda (Authorizer) | PingFederate JWKS | HTTPS | 443 | None (public JWKS endpoint) | Internal (public keys) | TLS 1.2+ |
| 8 | Lambda (Processing) | Amazon Bedrock | HTTPS | 443 | IAM role (via VPC endpoint) | Confidential (document text) | TLS 1.2+ |
| 9 | Lambda (Processing) | Amazon Textract | HTTPS | 443 | IAM role (via VPC endpoint) | Confidential (document images) | TLS 1.2+ |
| 10 | Lambda (Processing) | Amazon S3 | HTTPS | 443 | IAM role (via VPC endpoint) | Confidential (results) | TLS 1.2+ |
| 11 | Lambda (Processing) | Amazon DynamoDB | HTTPS | 443 | IAM role (via VPC endpoint) | Internal (metadata) | TLS 1.2+ |
| 12 | Lambda (Completion Hook) | PingFederate Token Endpoint | HTTPS | 443 | Client credentials (secret from Secrets Manager) | Sensitive (credentials) | TLS 1.2+ |
| 13 | Lambda (Completion Hook) | Amazon MQ (ActiveMQ) | AMQPS | 5671 | Ping OAuth2 token (AD-integrated) | Confidential (job completion events) | TLS 1.2+ |
| 14 | EventBridge | Lambda (Queue Sender) | AWS internal | — | IAM role | Internal (S3 event metadata) | AWS encryption |
| 15 | SQS | Lambda (Queue Processor) | AWS internal | — | IAM role | Internal (document references) | SSE-SQS |
| 16 | CodeBuild | JFrog Artifactory | HTTPS | 443 | Credentials from Secrets Manager | Internal (packages) | TLS 1.2+ |
| 17 | CodeBuild | Amazon ECR | HTTPS | 443 | IAM role (via VPC endpoint) | Internal (container images) | TLS 1.2+ |
| 18 | Lambda | CloudWatch Logs | HTTPS | 443 | IAM role (via VPC endpoint) | Internal (execution logs) | TLS 1.2+ |

---

#### 2.4.3 Description of Security

##### Authentication Architecture

**Web UI Authentication (Human Users):**

```
Browser → PingFederate (corporate SSO) → Cognito User Pool (OIDC federation)
    → Cognito issues JWT (ID + Access tokens) → Browser session
    → API Gateway validates Cognito JWT on data operation requests
```

- Amazon Cognito user pool with PingFederate as external identity provider
- Self-signup disabled (`AllowAdminCreateUserOnly: true`)
- 4-tier RBAC: Admin, Author, Reviewer, Viewer
- Token lifetime: Access 1 hour, Refresh configurable
- Strong password policy enforced (if direct Cognito login is used as fallback)

**Jobs API Authentication (Machine-to-Machine):**

```
External System → PingFederate (client_credentials grant) → JWT issued
    → POST /jobs with Bearer token → Custom Lambda Authorizer
    → Authorizer validates: JWT signature (JWKS), issuer, expiration, role claims
    → IAM policy generated → Request proceeds or is denied
```

- Custom Lambda authorizer validates PingFederate JWTs directly
- Supports RS256, ES256 signature algorithms via JWKS endpoint
- Multi-issuer support (2 simultaneous Ping environments)
- Role-based access control via `userRoles` / `memberOf` claims
- No Cognito dependency for M2M flows

##### Authorization Model

| Layer | Mechanism | Enforcement |
|-------|-----------|-------------|
| API Gateway | Custom authorizer (Jobs API), Cognito authorizer (Web UI) | Request-level allow/deny |
| Lambda Business Logic | JWT claims inspection, role verification | Operation-level access control |
| DynamoDB | Partition key includes client/user ID | Data-level isolation |
| S3 | IAM policies, presigned URL scoping | Object-level access control |

##### Encryption

**At Rest:**

| Resource | Method |
|----------|--------|
| S3 Buckets (all) | SSE-S3 (default) or SSE-KMS (configurable) |
| DynamoDB Tables (all) | AWS-managed encryption |
| SQS Queues | SSE-SQS |
| CloudWatch Logs | CloudWatch default encryption |
| Secrets Manager | AWS KMS |

**In Transit:**

| Communication Path | Protocol |
|-------------------|----------|
| All external API calls | HTTPS / TLS 1.2+ |
| All internal AWS service calls | TLS via AWS SDK (VPC endpoints) |
| Browser ↔ API Gateway | HTTPS (via execute-api VPC endpoint) |
| Lambda ↔ ActiveMQ | AMQPS (TLS 1.2+) |

##### Network Security

- **No public endpoints**: API Gateway configured as PRIVATE; reachable only via `execute-api` Interface VPC Endpoint
- **VPC isolation**: All Lambda functions execute within customer VPC private subnets
- **Security groups**: Lambda Security Group restricts egress to specific VPC endpoint ENIs
- **VPC Endpoints**: All AWS service access (Bedrock, Textract, S3, DynamoDB, SQS, Step Functions, KMS, CloudWatch, SSM, Lambda, EventBridge, Athena, STS, ECR) via Interface/Gateway endpoints
- **No NAT Gateway** (air-gapped): All traffic routes through VPC endpoints; JFrog provides build dependencies
- **WAFv2**: Optional IP allow-list on API Gateway stage

##### Logging and Audit

| Log Source | Content | Retention |
|-----------|---------|-----------|
| API Gateway Access Logs | All API requests (method, path, status, latency, caller IP) | Configurable (default 90 days) |
| Lambda Execution Logs | Function invocations, processing details, errors | Configurable (default 90 days) |
| Step Functions Execution History | Full workflow state transitions per document | 90 days (service default) |
| CloudTrail | All AWS API calls across the account | Configurable |
| DynamoDB Streams (optional) | Document status transition events | 24 hours (stream), archived to S3 |

##### Threat Model Summary (STRIDE)

A comprehensive STRIDE-based threat analysis identified 62 threats:

| STRIDE Category | Count | Top Concern |
|----------------|-------|-------------|
| **Tampering** | 22 | Prompt injection, configuration manipulation, data poisoning |
| **Information Disclosure** | 16 | Data exfiltration via extensibility points, token exposure |
| **Elevation of Privilege** | 12 | RBAC bypass, hook privilege escalation |
| **Denial of Service** | 10 | Resource exhaustion, cost escalation |
| **Spoofing** | 7 | Token theft, credential compromise |
| **Repudiation** | 5 | Insufficient audit trail |

**Critical Risks (Score 8+) and Mitigation:**

| Threat | Risk Score | Status | Mitigation |
|--------|-----------|--------|------------|
| Configuration tampering (malicious prompts/schemas) | 8 | Mitigated | 4-tier RBAC (Admin-only for config), configuration versioning, JSON Schema validation, audit logging |
| Prompt injection via document content | 9 | Mitigated | Prompt engineering with guardrails, input/output tagging, Bedrock Guardrails, output schema validation, evaluation framework |
| Data exfiltration via MCP tools | 8 | Partially Mitigated | IAM least-privilege, VPC egress controls, audit logging. *Note: MCP is disabled in this deployment.* |
| Data exfiltration via post-processing hook | 8 | Partially Mitigated | IAM least-privilege, VPC with egress controls, audit logging. *Note: Hooks run in customer-managed VPC with controlled egress.* |
| Malicious code execution via Lambda hooks | 4 | Accepted | Customer responsibility — hook code deployed by customer engineering team, subject to their code review and security scanning processes |

##### Container Security

- All Lambda functions deployed as container images stored in Amazon ECR
- **ECR image scanning** enabled: automated vulnerability detection on push
- Images built in CodeBuild (in-VPC) from base images pulled through JFrog Artifactory
- No public Docker Hub access — all base images mirrored internally

---

## 3 ARCHITECTURE OBSERVATIONS

### Key Observations

| # | Observation | Category | Recommendation |
|---|------------|----------|----------------|
| O1 | **Prompt injection is an inherent risk** in any system that processes untrusted documents through LLM prompts. The system mitigates via prompt engineering, guardrails, and output validation, but cannot fully eliminate the risk. | AI/ML Security | Monitor extraction accuracy via evaluation framework; investigate anomalies; consider Bedrock Guardrails Automated Reasoning for critical document types |
| O2 | **Single-tenant deployment** provides strong isolation between environments but means each environment is a full CloudFormation stack (~40 resources). | Scalability | Acceptable for current workload; monitor deployment time as stack grows |
| O3 | **Bedrock model availability** is a single point of dependency. If Bedrock experiences throttling or outage, document processing halts. | Availability | SQS-based queuing provides backpressure; documents are not lost, just delayed. Monitor Bedrock throttling metrics. Request quota increases proactively. |
| O4 | **5 accepted risks** in the threat model are low-likelihood and relate to customer-managed extension points (Lambda hooks, SDK credentials) and inherent service characteristics (BDA opacity). | Security | Accepted risks documented; customer engineering team responsible for hook security; SDK credential management follows corporate standards |
| O5 | **Weekly upstream sync** may introduce merge conflicts if upstream refactors enterprise-touched files (template.yaml, patterns/). | Maintainability | Automated sync creates PR for manual resolution; enterprise code isolated in `enterprise/` directory minimizes conflicts |
| O6 | **Cognito hosted UI requires browser egress** to `cognito-idp.{region}.amazonaws.com`. In strict VPC-only environments, users must access via VPN/DirectConnect that can reach this endpoint. | Network | Documented as assumption A10; verified in current network topology |
| O7 | **ActiveMQ broker is customer-managed infrastructure**. IDP depends on broker availability for completion notifications. If broker is down, notifications fail (but results remain retrievable via polling). | Integration | Completion hook implements retry with exponential backoff; GET /jobs/{id} polling serves as fallback |

### Accepted Risks

| Risk | Justification |
|------|---------------|
| HOOK.T01: Malicious customer code via hooks | Customer responsibility — hooks are customer-deployed Lambda functions subject to customer's own SDLC |
| BDA.T01: BDA service opacity | AWS managed service; limited observability by design; mitigated by evaluation framework comparing BDA outputs to baselines |
| UI.T05: Client-side configuration exposure | Low risk — UI config (API endpoints, Cognito pool ID) is not secret; required for browser operation |

---

## 4 REFERENCES

| # | Document | Location | Description |
|---|----------|----------|-------------|
| 1 | GenAI IDP README | `README.md` (repo root) | Project overview, quick start, feature list |
| 2 | Enterprise Extensions README | `enterprise/README.md` | Enterprise features, structure, deployment |
| 3 | Jobs API Reference | `enterprise/API.md` | Full API endpoint specification |
| 4 | Threat Model (STRIDE) | `threat-modeling/README.md` | 62 threats, methodology, directory structure |
| 5 | Threat Model Executive Summary | `threat-modeling/deliverables/executive-summary.md` | Stakeholder-level summary |
| 6 | Security Controls Implementation | `threat-modeling/deliverables/implementation-guide.md` | Detailed control-to-threat mapping |
| 7 | Risk Assessment Matrix | `threat-modeling/risk-assessment/risk-matrix.md` | Complete risk register with scoring |
| 8 | AWS Services and IAM Roles | `docs/aws-services-and-roles.md` | Full service inventory with IAM requirements |
| 9 | Architecture Guide | `docs/architecture.md` | Detailed system architecture |
| 10 | Private Network Deployment | `docs/deployment-private-network.md` | VPC-only deployment runbook |
| 11 | API Gateway Hosting Guide | `docs/apigateway-hosting.md` | API Gateway hosting mode documentation |
| 12 | Enterprise Fork Proposal | `enterprise/docs/enterprise-fork-proposal.md` | Fork model rationale and phase plan |
| 13 | Enterprise Deployment Guide | `enterprise/docs/deployment-guide.md` | AI-guided deployment walkthrough |
| 14 | Data Flows (Security) | `threat-modeling/architecture/data-flows.md` | Data flow diagrams with trust boundaries |
| 15 | System Overview (Security) | `threat-modeling/architecture/system-overview.md` | Components, trust boundaries, architecture |
| 16 | Mitigation Report | `threat-modeling/Mitigation Report 04252026.md` | Latest mitigation status update |

---

*End of Document*
