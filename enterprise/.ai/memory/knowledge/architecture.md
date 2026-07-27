# Architecture

## What this project is

Enterprise fork of the AWS GenAI IDP (Intelligent Document Processing) accelerator.
Upstream: `github.com/aws-solutions-library-samples/accelerated-intelligent-document-processing-on-aws`.

We maintain enterprise features on top of upstream without modifying core document
processing logic (OCR, classification, extraction, assessment).

## Repository model

- **Fork** (not a wrapper, not a CDK overlay) — we carry patches on upstream files
- **`enterprise/` directory** — all enterprise-only code lives here (never conflicts with upstream)
- **`template.yaml`** — has enterprise params/conditions/resources between markers
- **Upstream sync** — periodic merge from upstream main into `enterprise/develop`
- **Customer delivery** — zip releases, customer merges into their air-gapped repo

## Upstream (unchanged application code)

- OCR → Classification → Extraction → Assessment pipeline (Step Functions)
- Web UI (React + API Gateway REST API, v0.6.1)
- Cognito User Pool (Web UI auth, supports SAML/OIDC federation)
- Jobs API (headless M2M) — Private API Gateway
- Feature Platform (plugin marketplace for vertical packs)
- Bedrock Data Automation (BDA) integration

## Enterprise additions

- **Ping JWT authorizer** — replaces Cognito on Jobs API (multi-issuer, role-based, CA cert support for TLS inspection)
- **Completion hook** — publishes to Amazon MQ (RabbitMQ + Ping OAuth2) on workflow complete
- **Per-job configurationVersion** — callers specify which config version to process with
- **Private registry** — Dockerfile/buildspec/template params for internal registries
- **SDLC pipeline** — CodePipeline for automated publish + deploy
- **Enterprise deployment script** — simplified CD script (`enterprise/sdlc/codebuild_deployment.py`)
- **Config pipeline** — lightweight pipeline for document config promotion

## Deployment model

- One pipeline per environment (dev, staging, prod)
- Same code.zip dropped to each account's S3
- Per-environment `pipeline-config.yaml` in S3 tells pipeline what params to use
- Enterprise layers built by `enterprise/build.sh` before publish
- Pipeline uses enterprise script if present, falls back to upstream's

## Current versions

- Fork: v0.6.1 (enterprise/develop branch, synced 2026-07-20)
- Upstream: v0.6.1
- Main branch mirrors upstream main (no enterprise commits)
- Releases tagged from `enterprise/develop`

## Accounts

- Test account (502161568083): `idp-default`, `idp-enterprise` stacks (v0.6.1 validated)
- Customer account (153439803068): `mf-aidp-2` stack, air-gapped environment
