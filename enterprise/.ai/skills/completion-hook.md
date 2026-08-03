# Completion Hook — ActiveMQ with Ping OAuth2 (ROPC)

## Overview

The completion hook Lambda publishes document processing results to ActiveMQ after
each document completes. Authentication uses PingFederate ROPC grant (AD credentials)
to get a JWT, which is passed as the STOMP passcode to the broker's OAuth2 backend.

## Flow

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  Lambda Function │         │  Secrets Manager │         │  PingFederate   │
│  (Completion     │────1───▶│  (AD user/pass + │         │  (Token Server) │
│   Hook)          │◀───────│   client secret) │         │                 │
│                  │────2──────────────────────────────▶│                 │
│                  │◀───────────────────────────────────│  JWT            │
│                  │                                     └─────────────────┘
│                  │────3───▶┌─────────────────┐
│                  │         │  ActiveMQ        │
└─────────────────┘         │  (STOMP+SSL      │
                            │   port 61617)    │
                            └─────────────────┘

1. Read AD username, password, client secret from Secrets Manager
2. POST /as/token.oauth2 (grant_type=password, client_id, client_secret, username, password)
3. STOMP CONNECT (login="", passcode=JWT) → SEND message
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `EnableCompletionHook` | Yes | `false` | Enable the hook |
| `CompletionHookMQHost` | Yes | — | ActiveMQ broker hostname |
| `CompletionHookMQPort` | No | `61617` | ⚠️ SSL port. **61617 is OpenWire-SSL, not STOMP** — STOMP+SSL is normally **61614**. stomp.py cannot speak OpenWire. Confirm the broker's STOMP connector port before deploying; see the protocol note in `memory/knowledge/constraints.md` |
| `CompletionHookMQDestination` | No | `/queue/idp.document.completed` | Queue or topic |
| `CompletionHookPingTokenUrl` | Yes | — | Ping token endpoint |
| `CompletionHookPingClientId` | Yes | — | OAuth2 client ID |
| `CompletionHookPingClientSecretArn` | Yes | — | Secrets Manager ARN: client secret |
| `CompletionHookPingUsernameSecretArn` | Yes | — | Secrets Manager ARN: AD username |
| `CompletionHookPingPasswordSecretArn` | Yes | — | Secrets Manager ARN: AD password |
| `CompletionHookPingScope` | No | — | OAuth2 scope (optional) |
| `CompletionHookPingValidatorId` | No | — | Ping password validator ID (optional) |

## Secrets Manager setup

```bash
# Client secret
aws secretsmanager create-secret \
  --name "idp/completion-hook/client-secret" \
  --secret-string '<client-secret-value>'

# AD username
aws secretsmanager create-secret \
  --name "idp/completion-hook/username" \
  --secret-string '<ad-service-account-username>'

# AD password
aws secretsmanager create-secret \
  --name "idp/completion-hook/password" \
  --secret-string '<ad-service-account-password>'
```

## Pipeline config example

```yaml
parameters:
  EnableCompletionHook: "true"
  CompletionHookPingTokenUrl: https://ping.example.com/as/token.oauth2
  CompletionHookPingClientId: idp-mq-client
  CompletionHookPingClientSecretArn: arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:idp/completion-hook/client-secret-xxx
  CompletionHookPingUsernameSecretArn: arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:idp/completion-hook/username-xxx
  CompletionHookPingPasswordSecretArn: arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:idp/completion-hook/password-xxx
  CompletionHookPingScope: edit
  CompletionHookPingValidatorId: FHLMCPCV
  CompletionHookMQHost: amq-broker.internal.example.com
  CompletionHookMQPort: "61617"
  CompletionHookMQDestination: /queue/idp.document.completed
```

## Which protocol does the broker actually speak?

Before testing the hook, confirm a STOMP connector exists — `stomp.py` cannot
speak OpenWire (61617) or AMQP (5671).

```bash
# Probes every ActiveMQ wire port: TCP -> TLS -> STOMP CONNECT.
# No credentials needed. Run from inside the VPC / a host that can reach the broker.
python enterprise/test-jobs-api/probe_mq_ports.py \
    --host amq-broker.example.com --ca-cert /path/to/ca-bundle.pem
```

A STOMP `ERROR` frame is a **pass** — it proves the connector is live and only
the anonymous credentials were rejected. Timeouts on every port usually mean a
security-group problem, not a broker one; re-run from inside the VPC before
concluding STOMP is unavailable.

Also worth establishing: **Amazon MQ or self-managed ActiveMQ?** Amazon MQ enables
STOMP+SSL on 61614 by default (nothing to turn on), whereas a self-managed broker
only exposes what `activemq.xml` `<transportConnectors>` lists. "We have not
validated STOMP" from a customer usually means untested rather than unavailable.

## Testing (without deploying)

```bash
# Install deps
pip install stomp.py boto3

# Copy config
cp enterprise/test-jobs-api/env_activemq.example enterprise/test-jobs-api/.env_activemq
# Edit with real values

# Run test
python enterprise/test-jobs-api/test_activemq.py

# Or with pre-fetched token
python enterprise/test-jobs-api/test_activemq.py --token <jwt> --host amq-broker.example.com
```

## Lambda layer

The completion hook uses the `EnterprisePikaLayer` (name is legacy — actually contains `stomp.py`).
Layer requirements: `enterprise/layers/pika/requirements.txt` → `stomp.py==8.2.0`

## TLS / CA cert

**Where the bundle goes:** `enterprise/completion_hook/ca-bundle.pem` — the
function's `CodeUri`, which Lambda mounts at `/var/task/`. **Not** in a layer:
layers mount at `/opt/`, so a bundle there resolves to `/opt/python/ca-bundle.pem`
and is never found. You will not see it in the layer, and that is correct.
The file is customer-supplied and lives only in the customer's repo.

**These are Lambda env vars hardcoded in `template.yaml`, not CloudFormation
parameters.** There is nothing to set in `pipeline-config.yaml` — if a path is
wrong, fix the template. Deploying the stack is what applies a change.

| Env var | Trust path | Set in template? |
|---------|-----------|------------------|
| `CA_CERT_PATH` | Ping token endpoint (`ping_token.py`) | yes — was **missing**, added 2026-08-03 |
| `MQ_CA_CERT_PATH` | ActiveMQ broker (`mq_activemq.py`) | yes — was already present |

Both point at `/var/task/ca-bundle.pem`. The hook originally had only
`MQ_CA_CERT_PATH`, so the Ping token call fell back to the system CA store and
failed before the broker was ever contacted.

Optional overrides (add to the template's `Environment.Variables` only if needed):

- `MQ_DISABLE_HOST_VERIFY=true` if broker hostname doesn't match cert (e.g. `verifyHostName=false` in their connection URL). Keeps CA chain validation, skips only the hostname check.
- `MQ_INSECURE_SKIP_VERIFY=true` disables validation entirely — broker bring-up diagnostics only, never production.

### stomp.py has no `use_ssl=`/`ssl_context=` arguments

Those kwargs don't exist in stomp.py 8.x — passing them raises `TypeError`
before any connection is attempted. TLS goes through
`conn.transport.set_ssl(for_hosts=..., ca_certs=...)`.

`set_ssl()` alone can't express "validate the chain but skip the hostname
check": with `ca_certs` set the library forces hostname verification on, and
without it all validation is off. `mq_activemq._ssl_context_override()` injects a
pre-built SSLContext to get `CERT_REQUIRED` + `check_hostname=False`. If you
change that code, keep the `ca_certs` argument and the injected context in
agreement — the library re-derives `verify_mode` from `ca_certs` truthiness and
will otherwise silently override the context.

Diagnostic ladder for TLS failures (`ConnectFailedException` with an empty
message is a swallowed SSLError):

```bash
# 1. Does it connect at all? (no validation - diagnostics only)
python test_activemq.py --insecure
# 2. Is the chain trusted?
python test_activemq.py --ca-cert /path/to/corporate-ca-bundle.pem
# 3. Is only the hostname wrong?
python test_activemq.py --ca-cert /path/to/corporate-ca-bundle.pem --no-verify-host
# Ground truth, outside Python:
openssl s_client -connect <broker>:61617 -CAfile <ca-bundle> -showcerts
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `401` from Ping token endpoint | Invalid credentials | Check all 4 secrets in Secrets Manager |
| STOMP connection refused | Wrong port or protocol | Verify broker supports STOMP on 61617 (auto-detect) |
| `CERTIFICATE_VERIFY_FAILED` on token ("self-signed certificate in certificate chain") | `CA_CERT_PATH` not in the template's env vars, or pem missing from CodeUri | Both are template/code fixes, not parameters. Check CloudWatch for the "CA_CERT_PATH is not set" vs "does not exist" warning — they distinguish the two causes |
| `CERTIFICATE_VERIFY_FAILED` on broker | TLS inspection | Set MQ_CA_CERT_PATH to the corporate CA bundle |
| `ConnectFailedException` with empty message | Swallowed TLS error | Run the diagnostic ladder above |
| `TypeError: unexpected keyword argument 'use_ssl'` | Wrong stomp.py TLS API | Use `transport.set_ssl()` — see above |
| Handshake fails, cert CN/SAN != hostname | Broker cert mismatch | `MQ_DISABLE_HOST_VERIFY=true` (keeps chain validation) |
| Message not appearing in queue | Wrong destination | Check destination format: `/queue/name` or `/topic/name` |
| Lambda timeout | Broker unreachable | Check VPC security group allows outbound to port 61617 |
| Password expiry | AD password rotated | Update Secrets Manager value |
