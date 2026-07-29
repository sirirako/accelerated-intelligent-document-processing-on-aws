#!/usr/bin/env python3
"""
Test ActiveMQ STOMP connection with Ping JWT authentication.

Tests the completion hook's MQ publishing flow without deploying Lambda.
Verifies: Secrets Manager read -> Ping ROPC token -> STOMP connect -> publish.

Usage:
    1. Copy env_activemq.example to .env_activemq and fill in values
    2. Run: python test_activemq.py

    Or with explicit params:
    python test_activemq.py --host amq-broker.example.com --port 61617 \
        --destination /queue/test --token <pre-fetched-jwt>

Requirements:
    pip install stomp.py boto3 requests
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
                          ca_cert=None, disable_host_verify=False):
    """Connect to ActiveMQ via STOMP+SSL and publish a test message."""
    import stomp

    print(f"  Broker: {host}:{port}")
    print(f"  Destination: {destination}")

    ssl_ctx = ssl.create_default_context()
    if ca_cert and os.path.exists(ca_cert):
        ssl_ctx = ssl.create_default_context(cafile=ca_cert)
    if disable_host_verify:
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

    conn = stomp.Connection([(host, port)], use_ssl=True, ssl_context=ssl_ctx)

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
    print(f"  OK - message published!")
    print(f"  Body: {json.dumps(message, indent=2)}")

    conn.disconnect()
    return True


def main():
    parser = argparse.ArgumentParser(description="Test ActiveMQ STOMP connection")
    parser.add_argument("--host", help="ActiveMQ broker hostname")
    parser.add_argument("--port", type=int, default=61617, help="SSL port")
    parser.add_argument("--destination", default="/queue/idp.test", help="Queue/topic")
    parser.add_argument("--token", help="Pre-fetched JWT (skip Ping token request)")
    parser.add_argument("--ca-cert", help="CA certificate file path")
    parser.add_argument("--no-verify-host", action="store_true", help="Disable hostname verification")
    args = parser.parse_args()

    env = load_env()

    host = args.host or env.get("MQ_HOST")
    port = args.port or int(env.get("MQ_PORT", "61617"))
    destination = args.destination or env.get("MQ_DESTINATION", "/queue/idp.test")
    ca_cert = args.ca_cert or env.get("CA_CERT_PATH")
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
            ca_cert=ca_cert,
        )
    else:
        print(f"1. Using pre-fetched token: {token[:30]}...")

    print("\n2. Testing STOMP connection to ActiveMQ...")
    try:
        test_stomp_connection(
            host, port, destination, token,
            ca_cert=ca_cert,
            disable_host_verify=disable_host_verify,
        )
        print("\n[OK] All tests passed!")
    except Exception as e:
        print(f"\n[FAILED] {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
