# 2026-08-03: ActiveMQ STOMP Testing + Memory Reconcile

## Memory reconcile

Knowledge had drifted behind the activity logs and the code:

- `.ai/README.md` "start here" pointed at four files that don't exist
  (`memory/architecture.md`, `memory/enterprise-state.md`, `memory/open-work.md`,
  `skills/test-api.md`). Rewrote it to match the real tree: `memory/knowledge/*`,
  `memory/activities/`, the 9 actual skills, and the `agents/` directory (which
  the README never mentioned).
- `constraints.md` "Completion hook (ActiveMQ)" still said "protocol TBD (STOMP?
  AMQP 1.0?)" and "current code uses pika — needs update", contradicting
  `mq_activemq.py` and the 07-27 log. Replaced with shipped state: STOMP+SSL on
  61617, JWT as STOMP passcode, `stomp.py==8.2.0`, vendored docopt +
  websocket-client, the two TLS env vars, and the pending pika→stomp rename.

## Work since the 07-27 log (was unlogged)

- `1d9d3a7f` — vendored `docopt` + `websocket-client` into the STOMP layer.
  docopt is tarball-only in customer JFrog and CodeBuild can't build from source,
  so the pure Python deps are pre-vendored and stomp.py installs with `--no-deps`.
- `f4f8b8c9` — `build.sh` updated for stomp.py (pure Python, no platform constraint)
- `0694f7ef` — Ping authorizer hardening cherry-pick landed
- `enterprise/docs/production-readiness.md` added (uncommitted) — architecture +
  security posture overview for the customer's production approval process
- `enterprise/layers/ping_verifier/python/bin/cffi-gen-src` — untracked build
  artifact from a local layer build; should not be committed

## Naming debt

`enterprise/layers/pika/` and CFN layer `EnterprisePikaLayer` contain stomp.py,
not pika. Rename deferred — touches `build.sh` and template layer paths. Noted in
`constraints.md` so the next reader isn't misled.

## ActiveMQ STOMP testing

Code complete (`mq_activemq.py`, `test_activemq.py`). Testing against the
customer broker is blocked on a certificate issue — see below.

### Certificate issue — root cause was NOT cert configuration

`mq_activemq.py` and `test_activemq.py` both called:

```python
stomp.Connection([(host, port)], use_ssl=True, ssl_context=ssl_ctx)
```

Those kwargs don't exist in stomp.py 8.x. Verified against the vendored layer:

```
accepts use_ssl?     False
accepts ssl_context? False
TypeError: StompConnection11.__init__() got an unexpected keyword argument 'use_ssl'
```

So the carefully-built SSL context was never reaching the socket — the call
raised `TypeError` before any network I/O. No cert change could have fixed this.
The correct API is `conn.transport.set_ssl(for_hosts=..., ca_certs=...)`.

Second problem, which is the *actual* cert issue underneath: `set_ssl()` only
offers two modes — `ca_certs` set means `CERT_REQUIRED` **and** hostname
verification; `ca_certs=None` disables validation entirely. The customer's broker
cert CN/SAN doesn't match the hostname (their URLs use `verifyHostName=false`),
so one mode fails the handshake and the other abandons chain validation.

Fix: `_ssl_context_override()` swaps `stomp.transport.ssl` for a shim returning a
pre-built context, giving `CERT_REQUIRED` + `check_hostname=False`.

Gotcha found while testing: the library re-asserts `verify_mode` on the injected
context, derived only from `ca_certs` truthiness. The first fix attempt left
`MQ_INSECURE_SKIP_VERIFY` broken because the context said CERT_NONE while
`ca_certs` was still truthy. `_build_ssl_context` now returns both values so they
can't disagree.

### Verified against a stub TLS broker (cert CN deliberately mismatched)

| Mode | Result |
|------|--------|
| Correct CA, hostname verified | fails (expected — CN mismatch) |
| Correct CA + `MQ_DISABLE_HOST_VERIFY` | **publishes** ← customer's config |
| **Wrong** CA + `MQ_DISABLE_HOST_VERIFY` | fails ← proves chain still validated |
| `MQ_INSECURE_SKIP_VERIFY` | publishes |

The wrong-CA case is the important one: it confirms skipping the hostname check
did not silently disable chain validation.

### Second bug, found from the customer's actual traceback

The reported error was at `ping_token.py:92` — the **Ping token endpoint**, not
the broker, so it fires before any STOMP code runs:

```
[ERROR] URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED]
        certificate verify failed: self-signed certificate in certificate chain>
```

Cause: `template.yaml` set `MQ_CA_CERT_PATH` on the completion hook but **not**
`CA_CERT_PATH`. `ping_token._get_ssl_context()` read the unset var, returned
`None`, and fell back to the system CA store — which cannot know the corporate
TLS-inspection CA. The broker had a CA bundle configured; the token call had none.

Fixed by adding `CA_CERT_PATH: /var/task/ca-bundle.pem` alongside the existing
`MQ_CA_CERT_PATH`.

### Where the CA bundle belongs (asked this session)

`/var/task/` is the function's `CodeUri` (`enterprise/completion_hook/`). Lambda
**layers** mount at `/opt/` — a bundle placed in a layer resolves to
`/opt/python/ca-bundle.pem` and is never found. So: the pem goes in the CodeUri
directory, and it is *correct* that it never appears in the layer. `build.sh`
does not copy it.

The pem is customer-supplied and exists only in the customer's repo, so its
absence from this repo is expected, not a missing file. Confirmed it is not
gitignored and was never committed here, and that nothing in packaging strips
`.pem`.

Because both readers silently fell back to the system CA store, a missing bundle
produced only a bare `CERTIFICATE_VERIFY_FAILED` with no hint about which trust
path or whether a bundle loaded at all. Both now log the bundle in use, or warn
with the /var/task vs /opt distinction when it is unset or absent.

### Also changed

- `test_activemq.py` now imports the TLS setup from `mq_activemq` instead of
  duplicating it, so a passing test means the Lambda will connect too
- test script uses the vendored layer's stomp.py (exact Lambda version, no pip)
- added `--insecure`, and a diagnostic ladder printed on
  `ConnectFailedException` (which has an empty message — the library swallows the
  real SSLError in its reconnect loop)
- `CA_CERT_PATH` vs `MQ_CA_CERT_PATH` were conflated in the test script; now
  separate, matching the Lambda

Removed the unused `base64` import from `ping_token.py` while editing that file
for the CA logging (was a pre-existing lint error). `enterprise/completion_hook/`
now passes ruff clean.

## Protocol mismatch found at end of session — blocks release

Customer answered the "what protocol/port?" question with their broker URL:

```
failover:(ssl://amq-lz1-broker.<redacted>:61617?verifyHostName=false)
```

That is **OpenWire over TLS**, not STOMP. 61617 is the OpenWire-SSL port; STOMP
+SSL is 61614. `ssl://` is the Java/OpenWire scheme and `verifyHostName` is an
OpenWire client option. Our `stomp.py` client cannot speak OpenWire.

The 07-27 note "STOMP+SSL on port 61617" was wrong — right protocol, wrong
port — and 61617 then propagated into `app.py`'s default, `env_authorizer`
example, and the skill docs. All flagged in `constraints.md`.

This does not invalidate today's TLS fixes (both apply to whatever port is used),
but it does mean the hook cannot be assumed working until the connector question
is settled with the customer.

Confirmed from the same URL: `verifyHostName=false` means the broker cert CN/SAN
does not match its hostname, so `MQ_DISABLE_HOST_VERIFY: "true"` was added to the
template (keeps CA chain validation, skips only the hostname check).

## Customer says STOMP "not validated" — added a probe instead of waiting

Their reply: *"We have not validated STOMP protocol."* Untested, not unavailable.

The decisive follow-up is **Amazon MQ or self-managed ActiveMQ?** Amazon MQ ships
STOMP+SSL on 61614 enabled by default (nothing to validate); a self-managed broker
only has what `activemq.xml` lists. Their custom hostname doesn't reveal which.

Wrote `enterprise/test-jobs-api/probe_mq_ports.py` so we can answer it without
them: probes 61613/61614/61617/61616/5671/8883/61619 in three stages (TCP → TLS →
STOMP CONNECT) and reports which protocols answer. No credentials needed. Treats a
STOMP `ERROR` frame as success (proves the connector is live, auth merely
rejected) and distinguishes firewall timeouts from refused ports from non-STOMP
binary replies.

Validated against stub brokers covering all five outcomes:

| Stub behavior | Probe verdict |
|---------------|---------------|
| `CONNECTED` frame | STOMP available |
| `ERROR` frame | STOMP available (auth rejected) |
| OpenWire binary junk | no STOMP — "non-STOMP reply" |
| silent | no STOMP — "no reply" |
| nothing listening | "refused" |

### Probe run at customer: DNS failure — inconclusive

Ran against `amq-lz1-broker.itn01.n.fhlmc.com` and got a DNS failure, i.e. the
hostname did not resolve. The probe never reached TCP/TLS/STOMP, so this says
**nothing** about whether STOMP is available — do not record it as "no STOMP".

Follow-up: `nslookup` returns no answer from **both** inside the VPC and the VDI.
That rules out private-hosted-zone / split-horizon DNS scope, which was the main
cause that wouldn't have involved the customer.

Remaining causes:
1. **Broker not provisioned yet** — most likely. Nothing we can do.
2. Hostname differs from what we were given (the URL we have is `lz1`; may be a
   different environment, or a name that was only ever planned)

Blocked pending the customer confirming the broker exists and giving a hostname
that resolves. When it does, re-probe from inside the VPC.

Worth asking them for the exact DNS rcode if they investigate: **NXDOMAIN** means
the zone answered authoritatively that the name doesn't exist (→ not provisioned,
or wrong name), whereas **SERVFAIL/timeout** would point at a resolver or zone
delegation problem on their side rather than at the broker.

## Status

- SAML Ping federation for UI: working
- Jobs API Ping authorizer: hardened, deployed, needs real-token test
- Completion hook: TLS path fixed (both CA vars + host-verify) and verified
  against a stub broker. **Release blocked**, two open items:
  1. Is the broker live? Probe returned DNS failure — hostname did not resolve.
     Waiting on the customer.
  2. OpenWire vs STOMP — their URL is OpenWire (61617); STOMP+SSL is normally
     61614. Re-probe from inside the VPC once the broker resolves. Also worth
     asking: Amazon MQ (STOMP on by default) or self-managed?
- pandas pinned to 3.0.3 at customer (3.0.5 wheel not in JFrog for cp312)
