# Architecture

## What this project is

Enterprise fork of the AWS GenAI IDP (Intelligent Document Processing) accelerator.
The upstream is at `github.com/aws-solutions-library-samples/accelerated-intelligent-document-processing-on-aws`.

We maintain enterprise features on top of upstream without modifying core document
processing logic (OCR, classification, extraction, assessment).

## Repository model

- **Fork** (not a wrapper, not a CDK overlay) — we carry patches on upstream files
- **`enterprise/` directory** — all enterprise-only code lives here (never conflicts with upstream)
- **`template.yaml`** — has enterprise params/conditions/resources added (merge surface)
- **Upstream sync** — periodic merge from upstream develop/main into `enterprise/develop`

## Key components

### Upstream (unchanged)
- OCR → Classification → Extraction → Assessment pipeline (Step Functions)
- Web UI (React + API Gateway REST API in v0.6, was AppSync in v0.5)
- Cognito User Pool (Web UI auth)
- Jobs API (headless M2M) — Private API Gateway with Cognito client-credentials

### Enterprise additions
- **Ping JWT authorizer** — replaces Cognito on the Jobs API (multi-issuer, role-based)
- **Completion hook** — publishes to Amazon MQ (RabbitMQ + Ping OAuth2) on workflow complete
- **Per-job configurationVersion** — callers specify which config version to process with
- **Private registry** — Dockerfile/buildspec/template params for internal registries
- **SDLC pipeline** — CodePipeline for automated publish + deploy
- **Config pipeline** — lightweight pipeline for document config promotion

## Deployment model

- One pipeline per environment (dev, staging, prod)
- Same code.zip dropped to each account's S3
- Per-environment `pipeline-config.yaml` in S3 tells the pipeline what params to use
- Enterprise layers built by `enterprise/build.sh` before publish
- Config promotion is a separate lightweight pipeline

## Versions

- Current fork: v0.5.16 (enterprise/develop branch)
- Upstream develop: v0.6.x (AppSync removed, replaced with API Gateway REST API)
- v0.6 not yet merged into our fork — waiting for upstream release

## Accounts

- Dev/test account (549366490058): IDP-ENTERPRISE-TEST, idp-vpc-headless-test, IDP-ALB, etc.
- Second test account (502161568083): IDP-PRIVATE, idp-private-headless (v0.6 testing)
