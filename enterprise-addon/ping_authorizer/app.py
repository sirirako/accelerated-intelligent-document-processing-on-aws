"""API Gateway Lambda Authorizer (TOKEN/REQUEST type).

Validates Ping JWT tokens against multiple issuers and checks role/group
membership. Supports TOKEN authorizer (authorizationToken) and REQUEST
authorizer (headers: Authorization Bearer, Fhlmcjwt, x-jwt-token).
"""

import json
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
    r.strip()
    for r in os.getenv("REQUIRED_ROLES", "").split(",")
    if r.strip()
]
ALGORITHMS = ["ES256", "RS256", "HS256"]


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
    Checks Fhlmcjwt, Authorization Bearer, and x-jwt-token headers.
    """
    # TOKEN type authorizer
    auth_token = event.get("authorizationToken", "")
    if auth_token:
        return auth_token[7:] if auth_token.lower().startswith("bearer ") else auth_token

    # REQUEST type authorizer — check headers
    headers = event.get("headers") or {}
    lower_headers = {k.lower(): v for k, v in headers.items()}

    if lower_headers.get("fhlmcjwt"):
        return lower_headers["fhlmcjwt"]

    auth_header = lower_headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:]

    return lower_headers.get("x-jwt-token")


def _validate_token(token):
    """Validate JWT with multiple issuer support."""
    jwks_client = None
    token_issuer = None
    last_exception = None

    for issuer, jwks_url in ISSUER_CONFIG.items():
        try:
            if jwks_url not in _jwks_clients:
                _jwks_clients[jwks_url] = PyJWKClient(
                    jwks_url, cache_keys=True, max_cached_keys=50, lifespan=3600
                )

            client = _jwks_clients[jwks_url]
            signing_key = client.get_signing_key_from_jwt(token)

            temp_payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=ALGORITHMS,
                options={"verify_exp": False, "verify_aud": False},
            )
            token_issuer = temp_payload.get("iss")

            if token_issuer == issuer or token_issuer in ISSUER_CONFIG:
                jwks_client = client
                break
        except Exception as e:
            logger.info(f"Issuer {issuer} did not match: {type(e).__name__}: {e}")
            last_exception = e
            continue

    if not token_issuer or token_issuer not in ISSUER_CONFIG:
        if last_exception:
            return False, None, str(last_exception)
        return False, None, f"Unknown issuer: {token_issuer}"

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=ALGORITHMS,
            issuer=token_issuer,
            options={"verify_exp": False, "verify_aud": False},
        )
    except jwt.InvalidTokenError as e:
        return False, None, f"Token validation failed: {e}"

    # Role / entitlement check (skip if no roles configured)
    if REQUIRED_ROLES:
        user_roles = payload.get("userRoles", []) or payload.get("memberOf", [])
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
