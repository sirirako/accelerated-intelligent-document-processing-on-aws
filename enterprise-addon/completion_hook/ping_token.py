"""Obtain a PingFederate client-credentials access token (M2M).

The hook fetches a short-lived Ping JWT and presents it to RabbitMQ as the AMQP
password. Uses urllib + boto3 only (no extra deps), and caches the token per warm
container.
"""

import base64
import json
import time
import urllib.parse
import urllib.request

import boto3

_secrets = boto3.client("secretsmanager")
_cache: dict = {}


def _client_secret(secret_arn: str) -> str:
    raw = _secrets.get_secret_value(SecretId=secret_arn)["SecretString"]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed.get("client_secret") or parsed.get("clientSecret") or raw
    except (ValueError, TypeError):
        pass
    return raw


def get_token(token_url: str, client_id: str, client_secret_arn: str, scope: str) -> str:
    now = time.time()
    cached = _cache.get(token_url)
    if cached and cached[0] > now + 30:
        return cached[1]

    form = {"grant_type": "client_credentials"}
    if scope:
        form["scope"] = scope
    body = urllib.parse.urlencode(form).encode()

    req = urllib.request.Request(token_url, data=body, method="POST")
    basic = base64.b64encode(f"{client_id}:{_client_secret(client_secret_arn)}".encode()).decode()
    req.add_header("Authorization", f"Basic {basic}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(req, timeout=5) as resp:
        payload = json.loads(resp.read())

    token = payload["access_token"]
    _cache[token_url] = (now + int(payload.get("expires_in", 300)), token)
    return token
