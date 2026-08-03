# Constraints (Air-Gapped / Customer Environment)

Things that are BLOCKED or MUST NOT be done. Violating these causes deploy failures.

## Network — what's unreachable

| Endpoint | Why blocked | What breaks |
|----------|-------------|-------------|
| Docker Hub (`moby/buildkit`) | Air-gapped | `docker buildx create --driver docker-container` |
| `ghcr.io` (uv image) | Air-gapped | `FROM ghcr.io/astral-sh/uv` |
| `cdn.sheetjs.com` | Air-gapped | xlsx tarball download in npm install |
| `public.ecr.aws` | Air-gapped | Lambda base image pull |
| `cdn.amazonlinux.com` | TLS inspection | `dnf install git` (or any dnf package) |
| `registry.npmjs.org` | Air-gapped | npm packages not in JFrog |
| `pypi.org` | Air-gapped | pip/uv packages not in JFrog |
| `nodejs.org` | Air-gapped | Node.js binary download (`n 22.14.0`) |

## Buildspec — NEVER include

These will pass in our test account but FAIL at customer:

1. `docker buildx create --use --driver docker-container` — pulls moby/buildkit
2. `INSTALL_GIT=true` — runs `dnf install git` which reaches cdn.amazonlinux.com
3. `n 22.14.0` or any Node.js download — uses nodejs.org
4. `npm install -g npm@11` — may reach registry.npmjs.org

## Buildspec — MUST include

1. Install phase: CA cert, Docker config, pip config, uv config from env vars
2. `docker --config /root/.config/docker` on ALL docker commands
3. `BASE_IMAGE_ARGS` with `LAMBDA_BASE_IMAGE` support (full image:tag from internal registry)
4. `SECRET_ARGS` for `--secret id=pipconf,cacert,uvconf` mounts
5. Env var `CA_CERT_S3_URI` (not `CA_CERT_BUNDLE_S3_URI`)

## Template — PATTERNSTACK requirements

- `LAMBDA_BASE_IMAGE` env var on DockerBuildProject
- `DOCKER_CONF`, `PIP_CONF`, `UV_CONF` env vars (SECRETS_MANAGER type)
- `CA_CERT_S3_URI` env var
- DockerBuildRole: S3 access to CA cert bucket (not just ArtifactPrefix)
- DockerBuildRole: secretsmanager:GetSecretValue on registry secrets
- Registry params: DockerConfigSecretArn, UvConfigSecretArn, PipConfigSecretArn, LambdaBaseImage, CACertBundleS3Uri

## Customer infrastructure

- `LambdaArchitecture=x86_64` (native builds, no cross-compilation)
- VPC endpoint required for private API access (vpce-id format URL)
- TLS inspection on outbound traffic (requires CA cert injection)
- Permissions boundary on all IAM roles (set via `PermissionsBoundaryArn` parameter)
- Bedrock deny on `anthropic.*` models — must use Amazon Nova
- `WebUIHosting=APIGateway` (ALB removed in v0.6.1)
- `CreateTestVpc=false` on pipeline (no NAT Gateway, no VPC quota usage)

## Ping authorizer specifics

- Customer uses **password grant** (ROPC) with username/password + client ID/secret + validator_id
- `validator_id` is a PingFederate param that selects which password validator to use (e.g. LDAP)
- Token endpoint: Ping's `/as/token.oauth2`
- TLS inspection intercepts JWKS fetch — authorizer needs `CA_CERT_PATH=/var/task/ca-bundle.pem`
- `PingRequiredRoles` is MANDATORY after security hardening (fail-closed if empty)
- Algorithms: ES256/RS256 only (HS256 removed — algorithm-confusion attack surface)
- Token must have `exp` and `iss` claims (enforced, no longer optional)
- Strict per-issuer JWKS binding — no fallback probing of other issuers
- Role claims coerced to set (prevents substring matching bypass)
- 30s leeway on expiry for clock drift
- Enterprise functions/layers use `!Ref LambdaArchitecture` (not hardcoded arm64)

## Completion hook (ActiveMQ)

- Customer uses **ActiveMQ** (not RabbitMQ)
- ⚠️ **UNRESOLVED: protocol mismatch.** The customer's broker URL is
  `failover:(ssl://amq-lz1-broker.<redacted>:61617?verifyHostName=false)`.
  That is **OpenWire over TLS**, not STOMP:
  - `61617` is ActiveMQ's OpenWire-SSL port (STOMP+SSL is **61614**)
  - `ssl://` is the Java/OpenWire client scheme (STOMP would be `stomp+ssl://`)
  - `verifyHostName` is an OpenWire client option, not a STOMP one

  Our client is `stomp.py`, which speaks **only STOMP** and cannot talk OpenWire.
  There is no pure-Python OpenWire client.

  Asked 2026-08-03 whether the broker supports STOMP; answer was *"We have not
  validated STOMP protocol."* That means untested, **not** unavailable — so it is
  still an open question, and one we can answer ourselves.

  **The decisive question is Amazon MQ vs self-managed ActiveMQ:**
  - **Amazon MQ** — STOMP+SSL on 61614 is enabled **by default** on every broker.
    Nothing to turn on; "not validated" just means no one tried it.
  - **Self-managed ActiveMQ on EC2** — connectors come from `activemq.xml`
    `<transportConnectors>`; STOMP may genuinely be absent and require a config
    change plus a broker restart.

  The hostname (`amq-lz1-broker.<domain>`) is a custom domain, so it does not
  reveal which — it could be a CNAME to an Amazon MQ endpoint (native form:
  `b-<uuid>-1.mq.<region>.amazonaws.com`) or an EC2 host.

  Do not wait on the answer: `enterprise/test-jobs-api/probe_mq_ports.py` probes
  every ActiveMQ wire port (TCP → TLS → STOMP CONNECT) and reports which
  protocols actually answer. Needs only network reach — no credentials, no JWT.
  An `ERROR` frame counts as success: it proves a STOMP connector is live.

  If STOMP is truly unavailable, stomp.py is the wrong client and the hook needs
  rework (AMQP 1.0 on 5671 via `qpid-proton`, or a JMS bridge).

  The earlier "STOMP over SSL, port 61617" note in this file was wrong — it
  combined the right protocol with the OpenWire port. Do not trust `61617` as a
  STOMP port anywhere (`app.py` default, `env_activemq.example`, skill docs).
- Auth to MQ uses ROPC grant (same as API auth — needs username/password + client creds).
  The Ping JWT is passed as the STOMP `passcode` with an empty `login`.
- Client is `stomp.py==8.2.0` (pika/AMQP removed). Implementation:
  `enterprise/completion_hook/mq_activemq.py`
- Layer directory is still named `enterprise/layers/pika/` and the CFN layer is still
  `EnterprisePikaLayer` — **legacy names, they contain stomp.py**. Rename is pending
  (touches `build.sh` + template layer paths).
- stomp.py needs `docopt` and `websocket-client` vendored into the layer (its CLI
  imports them at package import time) — both must be in JFrog
- Two independent TLS trust paths, each with its own env var. **Both must be set**
  — the completion hook shipped with only `MQ_CA_CERT_PATH`, so every Ping token
  fetch failed with `CERTIFICATE_VERIFY_FAILED` before the broker was ever reached:
  - Ping token endpoint → `CA_CERT_PATH` (`ping_token.py`)
  - ActiveMQ broker → `MQ_CA_CERT_PATH` (`mq_activemq.py`)
  - `MQ_DISABLE_HOST_VERIFY=true` when the broker cert CN/SAN doesn't match the
    hostname (customer's connection URL uses `verifyHostName=false`)
- Lambda needs outbound security-group egress to 61617

### CA bundle lives in the function code, NOT in a layer

`CA_CERT_PATH=/var/task/ca-bundle.pem`. `/var/task/` is the function's `CodeUri`
(`enterprise/completion_hook/`); Lambda **layers** mount at `/opt/`, so a bundle
placed in a layer would land at `/opt/python/ca-bundle.pem` and never be found.
Put `ca-bundle.pem` in the `CodeUri` directory. Do not expect to see it in the
layer — `build.sh` does not copy it there.

The bundle is customer-supplied (their corporate CA for TLS inspection) and
exists **only in the customer's repo**, never in ours. Its absence upstream is
expected, not a bug — which is why both readers now log loudly when the file is
missing instead of silently falling back to the system CA store, where the only
symptom is a bare `CERTIFICATE_VERIFY_FAILED: self-signed certificate in
certificate chain`.

Same pattern applies to `enterprise/ping_authorizer/` (also `/var/task/ca-bundle.pem`).

### stomp.py TLS API — do not use `use_ssl=`/`ssl_context=`

`stomp.Connection(..., use_ssl=True, ssl_context=ctx)` **does not exist** in
stomp.py 8.x. Those kwargs are from other STOMP libraries; passing them raises
`TypeError: unexpected keyword argument 'use_ssl'` before any network I/O. TLS is
configured with `conn.transport.set_ssl(for_hosts=[(host, port)], ca_certs=...)`.

`set_ssl()` alone is not sufficient here. The library builds its own SSLContext
inline at connect time and offers only two modes:

| `ca_certs` | Result |
|-----------|--------|
| set | `CERT_REQUIRED` **and** hostname verification on |
| `None` | verification disabled entirely (`CERT_NONE`) |

The customer's broker needs chain validation *with* the hostname check off —
neither mode. `mq_activemq._ssl_context_override()` swaps `stomp.transport.ssl`
for a shim returning our pre-built context, so `CERT_REQUIRED` +
`check_hostname=False` survives.

Gotcha: the library re-asserts `verify_mode` on whatever context it gets, derived
solely from the truthiness of `ca_certs`. The `ca_certs` argument and the
injected context must encode the *same* decision or the library silently
overrides it (this is why `_build_ssl_context` returns both).

`ConnectFailedException` with an empty message means a TLS failure the library
swallowed inside its reconnect loop. Diagnose with `openssl s_client`, or
`test_activemq.py --insecure` to confirm it's trust and not auth/network.

## Pipeline template — hardcoded names that orphan on delete

If redeploying pipeline with same PipelineName after a failed delete, manually remove:
- CodeBuild project: `app-sdlc`
- CodePipeline: `{PipelineName}`
- KMS alias: `alias/{PipelineName}-key`
- IAM role: `genaiic-sdlc-pipeline-trigger-role`
- EventBridge rule: `genaiic-sdlc-pipeline-trigger`
- SNS topic: `{PipelineName}-failures`

## JFrog (customer's private registry)

- Remote npm repo may 404 on newer packages — admin must "Zap Caches" or wait for TTL
- First-time fetches trigger Xray scanning (can timeout) — retry after a few hours
- 401 errors: token may only access local repos, not remote
- `xlsx` is NOT on npm registry — must be manually uploaded as tarball
- Python warming must run on Linux for correct manylinux wheels
