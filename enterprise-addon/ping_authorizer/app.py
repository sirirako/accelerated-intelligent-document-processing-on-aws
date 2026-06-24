"""API Ping authorizer (REQUEST type, in-VPC).

External systems obtain a client-credentials token from PingFederate (in-VPC) and call
the API with `Authorization: Bearer <ping token>`. This authorizer validates the Ping
JWT against Ping's JWKS and enforces scopes by HTTP method, returning an IAM policy.
"""

import os

from ping_verifier import PingTokenError, verify
from scopes import authorize, token_scopes

PING_ISSUER = os.environ["PING_ISSUER"]
PING_JWKS_URI = os.environ["PING_JWKS_URI"]
PING_API_AUDIENCE = os.environ["PING_API_AUDIENCE"]
READ_SCOPE = os.environ.get("READ_SCOPE", "jobs.read")
WRITE_SCOPE = os.environ.get("WRITE_SCOPE", "jobs.write")


def _bearer(event):
    headers = event.get("headers") or {}
    value = next((v for k, v in headers.items() if k.lower() == "authorization"), None)
    if not value:
        value = event.get("authorizationToken")
    if not value:
        return None
    return value[7:].strip() if value[:7].lower() == "bearer " else value.strip()


def _policy(principal, effect, resource, context=None):
    out = {
        "principalId": principal,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [{"Action": "execute-api:Invoke", "Effect": effect, "Resource": resource}],
        },
    }
    if context:
        out["context"] = context
    return out


def handler(event, context):
    token = _bearer(event)
    if not token:
        raise Exception("Unauthorized")

    try:
        claims = verify(
            token,
            issuer=PING_ISSUER,
            jwks_uri=PING_JWKS_URI,
            audience=PING_API_AUDIENCE,
        )
    except PingTokenError:
        raise Exception("Unauthorized")

    method_arn = event.get("methodArn") or event.get("routeArn") or "*"
    principal = str(claims.get("sub") or claims.get("client_id") or "ping-client")

    if not authorize(claims, method_arn, READ_SCOPE, WRITE_SCOPE):
        return _policy(principal, "Deny", method_arn)

    return _policy(
        principal,
        "Allow",
        method_arn,
        context={"sub": principal, "scope": " ".join(sorted(token_scopes(claims)))},
    )
