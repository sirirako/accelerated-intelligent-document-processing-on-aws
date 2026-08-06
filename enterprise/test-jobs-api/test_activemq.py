#!/usr/bin/env python3
"""
Test ActiveMQ STOMP connection with Ping JWT authentication.

Tests the completion hook's MQ publishing flow without deploying Lambda.
Verifies: Secrets Manager read -> Ping ROPC token -> STOMP connect -> publish.

Usage:
    1. Copy env_activemq.example to .env_activemq and fill in values
    2. Run: python test_activemq.py

    Or with explicit params:
    python test_activemq.py --host amq-broker.example.com --port 61614 \
        --destination /queue/test --token <pre-fetched-jwt>

Diagnosing TLS failures, in order:
    1. --insecure                      does it connect at all? (skips ALL
                                       validation - diagnostics only)
    2. --ca-cert <corporate-ca-bundle> is the chain trusted?
    3. add --no-verify-host            is only the hostname wrong?
                                       (keeps chain validation)

Requirements:
    stomp.py is used from enterprise/layers/pika/python if present (the exact
    version the Lambda runs), so no pip install is needed. boto3/requests are
    only needed if fetching secrets.
"""

import argparse
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def load_env():
    env_file = SCRIPT_DIR / ".env_activemq"
    if not env_file.exists():
        return {}
    env = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def get_ping_token(token_url, client_id, client_secret, username, password,
                   scope="", validator_id="", ca_cert=None):
    """Get Ping JWT via ROPC grant."""
    print(f"  Token endpoint: {token_url}")
    form = {
        "grant_type": "password",
        "client_id": client_id,
        "client_secret": client_secret,
        "username": username,
        "password": password,
    }
    if scope:
        form["scope"] = scope
    if validator_id:
        form["validator_id"] = validator_id

    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(token_url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    ctx = None
    if ca_cert and os.path.exists(ca_cert):
        ctx = ssl.create_default_context(cafile=ca_cert)

    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        payload = json.loads(resp.read())

    token = payload["access_token"]
    expires_in = payload.get("expires_in", "unknown")
    print(f"  OK - token: {token[:30]}... (expires_in: {expires_in}s)")
    return token


def test_stomp_connection(host, port, destination, token, message=None,
                          ca_cert=None, disable_host_verify=False,
                          insecure=False):
    """Connect to ActiveMQ via STOMP+SSL and publish a test message.

    Uses the same TLS setup as the Lambda (enterprise/completion_hook/
    mq_activemq.py) so a pass here means the deployed hook will also connect.
    stomp.py has no use_ssl=/ssl_context= arguments; TLS goes through
    set_ssl() plus a context override. See that module's docstring.
    """
    # Prefer the vendored layer over a pip install: it is the exact stomp.py the
    # Lambda runs, and it works air-gapped with no pip install step.
    vendored = SCRIPT_DIR.parent / "layers" / "pika" / "python"
    if (vendored / "stomp").is_dir():
        sys.path.insert(0, str(vendored))
    import stomp

    sys.path.insert(0, str(SCRIPT_DIR.parent / "completion_hook"))
    import mq_activemq

    print(f"  Broker: {host}:{port}")
    print(f"  Destination: {destination}")

    if insecure:
        os.environ["MQ_INSECURE_SKIP_VERIFY"] = "true"
    if ca_cert:
        os.environ["MQ_CA_CERT_PATH"] = ca_cert
    if disable_host_verify:
        os.environ["MQ_DISABLE_HOST_VERIFY"] = "true"

    ca_bundle = mq_activemq._resolve_ca_bundle()
    print(f"  CA bundle: {ca_bundle or '(none - insecure mode)'}")
    ssl_ctx, ca_certs_arg = mq_activemq._build_ssl_context(ca_bundle)
    print(f"  verify_mode={ssl_ctx.verify_mode!r} "
          f"check_hostname={ssl_ctx.check_hostname}")

    conn = stomp.Connection([(host, port)])
    conn.transport.set_ssl(for_hosts=[(host, port)], ca_certs=ca_certs_arg)

    # Listener to see responses
    class TestListener(stomp.ConnectionListener):
        def on_error(self, frame):
            print(f"  [ERROR] {frame.body}")

        def on_connected(self, frame):
            print(f"  [CONNECTED] server: {frame.headers.get('server', 'unknown')}")

        def on_disconnected(self):
            print("  [DISCONNECTED]")

    conn.set_listener("test", TestListener())

    print("  Connecting (login='', passcode=JWT)...")
    with mq_activemq._ssl_context_override(ssl_ctx):
        conn.connect(login="", passcode=token, wait=True)
    print("  Connected!")

    if message is None:
        message = {
            "test": True,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "test_activemq.py",
        }

    body = json.dumps(message).encode()
    message_id = f"test-{int(time.time())}"

    print(f"  Publishing message (id: {message_id})...")
    conn.send(
        destination=destination,
        body=body,
        headers={
            "content-type": "application/json",
            "message-id": message_id,
            "persistent": "true",
        },
    )
    print("  OK - message published!")
    print(f"  Body: {json.dumps(message, indent=2)}")

    conn.disconnect()
    return True


def main():
    parser = argparse.ArgumentParser(description="Test ActiveMQ STOMP connection")
    parser.add_argument("--host", help="ActiveMQ broker hostname")
    parser.add_argument("--port", type=int, default=61614,
                        help="STOMP+SSL port (61614 on Amazon MQ; NOT OpenWire 61617)")
    parser.add_argument("--destination", default="/queue/idp.test", help="Queue/topic")
    parser.add_argument("--token", help="Pre-fetched JWT (skip Ping token request)")
    parser.add_argument("--ca-cert", help="CA certificate file path")
    parser.add_argument("--no-verify-host", action="store_true",
                        help="Skip hostname check, keep CA chain validation "
                             "(use when broker cert CN/SAN != hostname)")
    parser.add_argument("--insecure", action="store_true",
                        help="Skip ALL certificate validation. Broker bring-up "
                             "diagnostics only - never for production.")
    args = parser.parse_args()

    env = load_env()

    host = args.host or env.get("MQ_HOST")
    port = args.port or int(env.get("MQ_PORT", "61614"))
    destination = args.destination or env.get("MQ_DESTINATION", "/queue/idp.test")
    # Two trust paths, as in the Lambda: CA_CERT_PATH for the Ping endpoint,
    # MQ_CA_CERT_PATH for the broker. --ca-cert overrides both.
    ping_ca_cert = args.ca_cert or env.get("CA_CERT_PATH")
    mq_ca_cert = args.ca_cert or env.get("MQ_CA_CERT_PATH") or ping_ca_cert
    disable_host_verify = args.no_verify_host or env.get("MQ_DISABLE_HOST_VERIFY", "").lower() in ("1", "true")

    if not host:
        print("ERROR: MQ_HOST required (via --host or .env_activemq)")
        sys.exit(1)

    token = args.token
    if not token:
        print("1. Getting Ping token (ROPC)...")
        token_url = env.get("PING_TOKEN_URL")
        client_id = env.get("PING_CLIENT_ID")
        client_secret = env.get("PING_CLIENT_SECRET")
        username = env.get("PING_USERNAME")
        password = env.get("PING_PASSWORD")

        if not all([token_url, client_id, client_secret, username, password]):
            print("ERROR: Ping credentials required in .env_activemq or use --token")
            sys.exit(1)

        token = get_ping_token(
            token_url, client_id, client_secret, username, password,
            scope=env.get("PING_SCOPE", ""),
            validator_id=env.get("PING_VALIDATOR_ID", ""),
            ca_cert=ping_ca_cert,
        )
    else:
        print(f"1. Using pre-fetched token: {token[:30]}...")

    print("\n2. Testing STOMP connection to ActiveMQ...")
    try:
        test_stomp_connection(
            host, port, destination, token,
            ca_cert=mq_ca_cert,
            disable_host_verify=disable_host_verify,
            insecure=args.insecure,
        )
        print("\n[OK] All tests passed!")
    except Exception as e:
        print(f"\n[FAILED] {type(e).__name__}: {e}")
        # stomp.py swallows the underlying SSLError inside its reconnect loop and
        # raises a bare ConnectFailedException, so point at how to see the cause.
        if type(e).__name__ == "ConnectFailedException":
            print(
                "\nConnectFailedException hides the real cause. To diagnose:\n"
                "  1. Confirm TLS separately:\n"
                f"     openssl s_client -connect {host}:{port} "
                f"-CAfile {mq_ca_cert or '<ca-bundle>'} -showcerts\n"
                "  2. Compare the cert CN/SAN to the hostname you connect to.\n"
                "     If they differ, re-run with --no-verify-host (keeps chain\n"
                "     validation, skips only the hostname check).\n"
                "  3. If s_client says 'unable to get local issuer certificate',\n"
                "     the CA bundle is wrong/incomplete - TLS inspection means\n"
                "     you need the corporate CA, not the public one.\n"
                "  4. To confirm it is TLS and not auth/network, try --insecure.\n"
                "     If that connects, the problem is certificate trust.\n"
                "  5. Enable library logging for the raw error:\n"
                "     python -c \"import logging;logging.basicConfig("
                "level=logging.DEBUG)\" style init, or set STOMP debug.\n"
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
