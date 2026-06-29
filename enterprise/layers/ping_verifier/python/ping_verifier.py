"""Shared PingFederate OIDC JWT verifier.

Lives in the Lambda layer so both the API authorizer and completion hook can validate
Ping tokens identically. Fetches Ping's JWKS over the in-VPC network path and caches
keys per warm container.

Validates: RS256/ES256 signature against JWKS, `iss`, `exp`/`nbf`, and audience
(`aud` OR `azp` OR `client_id`). Raises PingTokenError on any failure.
"""

from __future__ import annotations

import time
import urllib.request

import jwt
from jwt import PyJWKClient


class PingTokenError(Exception):
    """Raised when a Ping token fails validation."""


_jwk_clients: dict[str, PyJWKClient] = {}
_claims_cache: dict[str, tuple[float, dict]] = {}
_CLAIMS_TTL = 30.0


def _client(jwks_uri: str) -> PyJWKClient:
    client = _jwk_clients.get(jwks_uri)
    if client is None:
        client = PyJWKClient(jwks_uri, lifespan=600, timeout=5)
        _jwk_clients[jwks_uri] = client
    return client


def verify(
    token: str,
    *,
    issuer: str,
    jwks_uri: str,
    audience: str,
    leeway: int = 30,
) -> dict:
    """Verify a Ping JWT and return its claims, or raise PingTokenError.

    `audience` is matched against aud/azp/client_id so the same call works for
    both ID tokens (aud) and access tokens (azp/client_id) depending on Ping config.
    """
    if not token:
        raise PingTokenError("empty token")

    cached = _claims_cache.get(token)
    if cached and cached[0] > time.time():
        return cached[1]

    try:
        signing_key = _client(jwks_uri).get_signing_key_from_jwt(token).key
    except Exception as exc:
        raise PingTokenError(f"unable to resolve signing key: {exc}") from exc

    try:
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256", "ES256"],
            issuer=issuer,
            options={"verify_aud": False, "require": ["exp", "iss"]},
            leeway=leeway,
        )
    except jwt.InvalidTokenError as exc:
        raise PingTokenError(f"invalid token: {exc}") from exc

    presented = {claims.get("aud"), claims.get("azp"), claims.get("client_id")}
    aud = claims.get("aud")
    if isinstance(aud, (list, tuple)):
        presented.update(aud)
    if audience not in presented:
        raise PingTokenError("audience mismatch")

    _claims_cache[token] = (time.time() + _CLAIMS_TTL, claims)
    return claims
