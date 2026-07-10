"""API Gateway Lambda Authorizer (TOKEN/REQUEST type).

Validates Ping JWT tokens against multiple issuers and checks role/group
membership. Supports TOKEN authorizer (authorizationToken) and REQUEST
authorizer (headers: Authorization Bearer, custom token header, x-jwt-token).
"""

import logging
import os

import jwt
from jwt import PyJWKClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_jwks_clients = {}

ISSUER_CONFIG = {
    os.getenv("ISSUER1", ""): os.getenv("JWKSURI1", ""),
    os.getenv("ISSUER2", ""): os.getenv("JWKSURI2", ""),
}
# Remove empty entries (unconfigured issuers)
ISSUER_CONFIG = {k: v for k, v in ISSUER_CONFIG.items() if k and v}

REQUIRED_ROLES = [
    r.strip() for r in os.getenv("REQUIRED_ROLES", "").split(",") if r.strip()
]
# Asymmetric algorithms only. HS256 must never be accepted alongside JWKS-sourced
# (public) keys — doing so enables an algorithm-confusion forgery where the public
# key is used as the HMAC secret.
ALGORITHMS = ["ES256", "RS256"]


def handler(event, context):
    """API Gateway Lambda Authorizer."""
    logger.info("Authorizer invoked")

    token = _extract_token(event)
    if not token:
        logger.warning("No token found in request")
        raise Exception("Unauthorized")

    is_valid, payload, error = _validate_token(token)
    if not is_valid:
        logger.warning(f"Token validation failed: {error}")
        raise Exception("Unauthorized")

    principal_id = payload.get("sub", "unknown")
    method_arn = event.get("methodArn") or event.get("routeArn") or "*"

    logger.info(f"Authorized user: {principal_id}")

    return _generate_policy(principal_id, "Allow", method_arn, payload)


def _extract_token(event):
    """Extract JWT from authorizer event.

    Supports TOKEN authorizer (authorizationToken) and REQUEST authorizer (headers).
    Checks custom token header, Authorization Bearer, and x-jwt-token headers.
    """
    # TOKEN type authorizer
    auth_token = event.get("authorizationToken", "")
    if auth_token:
        return (
            auth_token[7:] if auth_token.lower().startswith("bearer ") else auth_token
        )

    # REQUEST type authorizer — check headers
    headers = event.get("headers") or {}
    lower_headers = {k.lower(): v for k, v in headers.items()}

    # Custom JWT header (configure via CUSTOM_TOKEN_HEADER env var if needed)
    custom_header = os.getenv("CUSTOM_TOKEN_HEADER", "").lower()
    if custom_header and lower_headers.get(custom_header):
        return lower_headers[custom_header]

    auth_header = lower_headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:]

    return lower_headers.get("x-jwt-token")


def _validate_token(token):
    """Validate JWT with multiple issuer support."""
    # Read the (unverified) issuer claim WITHOUT trusting it, only to select the
    # matching JWKS. The authoritative decode below re-verifies iss against the
    # signing key, so a forged iss cannot escape its own issuer's JWKS.
    try:
        unverified_issuer = jwt.decode(token, options={"verify_signature": False}).get(
            "iss"
        )
    except jwt.InvalidTokenError as e:
        return False, None, f"Malformed token: {e}"

    jwks_url = ISSUER_CONFIG.get(unverified_issuer)
    if not jwks_url:
        # Do not fall back to probing other issuers — strict per-issuer binding.
        return False, None, f"Unknown issuer: {unverified_issuer}"
    token_issuer = unverified_issuer

    try:
        if jwks_url not in _jwks_clients:
            _jwks_clients[jwks_url] = PyJWKClient(
                jwks_url, cache_keys=True, max_cached_keys=50, lifespan=3600
            )
        signing_key = _jwks_clients[jwks_url].get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=ALGORITHMS,
            issuer=token_issuer,
            # verify_exp/nbf default to True. Require exp+iss so a token missing
            # them is rejected rather than silently accepted.
            options={"require": ["exp", "iss"], "verify_aud": False},
            leeway=30,
        )
    except jwt.InvalidTokenError as e:
        return False, None, f"Token validation failed: {e}"
    except Exception as e:  # signing-key resolution / network errors -> fail closed
        return False, None, f"Token validation error: {type(e).__name__}"

    # Role / entitlement check. Fail CLOSED: if no roles are configured, deny.
    if not REQUIRED_ROLES:
        return False, None, "No REQUIRED_ROLES configured; denying by default"

    user_roles = payload.get("userRoles") or payload.get("memberOf") or []
    if isinstance(user_roles, str):
        user_roles = [user_roles]
    user_roles = set(user_roles)
    if not any(role in user_roles for role in REQUIRED_ROLES):
        return (
            False,
            None,
            f"User {payload.get('sub')} lacks required entitlements",
        )

    return True, payload, None


def _generate_policy(principal_id, effect, method_arn, payload=None):
    """Build an API Gateway authorizer response (IAM policy document)."""
    # Allow access to all methods under this API stage
    arn_parts = method_arn.split(":")
    if len(arn_parts) >= 6:
        region = arn_parts[3]
        account_id = arn_parts[4]
        api_gw_parts = arn_parts[5].split("/")
        api_id = api_gw_parts[0]
        stage = api_gw_parts[1] if len(api_gw_parts) > 1 else "*"
        resource_arn = f"arn:aws:execute-api:{region}:{account_id}:{api_id}/{stage}/*"
    else:
        resource_arn = method_arn

    policy = {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": resource_arn,
                }
            ],
        },
    }

    if payload:
        policy["context"] = {
            "sub": payload.get("sub", ""),
            "firstName": payload.get("firstName", ""),
            "lastName": payload.get("lastName", ""),
        }

    return policy
