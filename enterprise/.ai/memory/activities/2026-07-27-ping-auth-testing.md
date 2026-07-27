# 2026-07-27: Ping Auth Testing + Scripts

## What was done
- Reviewed Robert's `enterprise/securityreview` branch (2 commits)
  - `b111ad15`: Harden Ping authorizer (enforce exp, fail-closed roles, drop HS256)
  - `a25b05fd`: Layer build via SAM BuildMethod (remove vendored deps)
  - Decision: merge auth hardening (commit 1), skip layer refactor (commit 2) for now
- Fixed architecture mismatch: enterprise Lambda functions/layers now use `!Ref LambdaArchitecture` instead of hardcoded arm64
- Added CA cert support to Ping authorizer (`CA_CERT_PATH` env var + ssl_context on PyJWKClient)
- Upgraded PyJWT to 2.13.0 + explicit cryptography dep
- Removed customer-specific references from code
- Fixed Get-PingToken.ps1: removed emojis (broke Windows parser), updated for password grant
- Created Ping-authenticated Jobs API test scripts:
  - `test_jobs_api_ping.ps1` (PowerShell)
  - `test_jobs_api_ping.py` (Python)
  - `env_api_ping.example` (config template)
- Updated README with Ping auth testing instructions

## Customer's Ping flow
- Grant type: `password` (not client_credentials)
- Requires: client_id, client_secret, username, password
- Optional: validator_id, scope
- Token endpoint: Ping's `/as/token.oauth2`

## Key findings
- Customer's TLS inspection intercepts JWKS fetch — authorizer needs CA cert
- `CA_CERT_PATH` env var set to `/var/task/ca-bundle.pem` (bundled with function code)
- Permissions boundary blocks Anthropic models — must use Amazon Nova
- Robert's layer refactor uses `BuildArchitecture: arm64` which is wrong for customer (x86_64) — deferred

## Status
- SAML Ping federation for UI: working
- Jobs API Ping authorizer: deployed, needs testing with real Ping token
- Completion hook: not yet tested (waiting for MQ broker)
