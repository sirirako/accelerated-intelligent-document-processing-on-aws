"""Obtain a PingFederate access token via ROPC (Resource Owner Password Credentials).

The hook fetches AD credentials from Secrets Manager, exchanges them for a Ping JWT
via the password grant, and presents the JWT to ActiveMQ as the STOMP passcode.
Caches the token per warm container until near expiry.
"""

import base64
import json
import os
import ssl
import time
import urllib.parse
import urllib.request

import boto3

_secrets = boto3.client("secretsmanager")
_cache: dict = {}


def _get_secret(secret_arn: str) -> str:
    """Read a plain-text secret from Secrets Manager."""
    raw = _secrets.get_secret_value(SecretId=secret_arn)["SecretString"]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed.get("client_secret") or parsed.get("password") or parsed.get("value") or raw
    except (ValueError, TypeError):
        pass
    return raw


def _get_ssl_context():
    """Build SSL context for Ping token endpoint (corporate TLS proxy)."""
    ca_path = os.getenv("CA_CERT_PATH", "")
    if ca_path and os.path.exists(ca_path):
        return ssl.create_default_context(cafile=ca_path)
    return None


_ssl_context = _get_ssl_context()


def get_token(
    token_url: str,
    client_id: str,
    client_secret_arn: str,
    username_secret_arn: str,
    password_secret_arn: str,
    scope: str = "",
    validator_id: str = "",
) -> str:
    """Get Ping JWT via ROPC grant.

    Args:
        token_url: Ping token endpoint (e.g. https://ping.example.com/as/token.oauth2)
        client_id: OAuth2 client ID
        client_secret_arn: Secrets Manager ARN for client secret
        username_secret_arn: Secrets Manager ARN for AD username
        password_secret_arn: Secrets Manager ARN for AD password
        scope: OAuth2 scope (optional)
        validator_id: PingFederate password validator ID (optional)
    """
    now = time.time()
    cached = _cache.get(token_url)
    if cached and cached[0] > now + 60:
        return cached[1]

    client_secret = _get_secret(client_secret_arn)
    username = _get_secret(username_secret_arn)
    password = _get_secret(password_secret_arn)

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

    ctx = _ssl_context if _ssl_context else None
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        payload = json.loads(resp.read())

    token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 300))
    _cache[token_url] = (now + expires_in, token)
    return token
