"""Pure scope helpers for the Ping authorizer."""

WRITE_VERBS = {"POST", "PUT", "PATCH", "DELETE"}


def required_scope(method_arn: str, read_scope: str, write_scope: str) -> str:
    """Map the requested method to its required scope.

    methodArn = arn:aws:execute-api:{region}:{acct}:{apiId}/{stage}/{VERB}/{resource}
    """
    try:
        tail = method_arn.split(":", 5)[5]
        verb = tail.split("/")[2].upper()
    except (IndexError, AttributeError):
        verb = "GET"
    return write_scope if verb in WRITE_VERBS else read_scope


def token_scopes(claims: dict) -> set:
    raw = claims.get("scope")
    if raw is None:
        raw = claims.get("scp", "")
    if isinstance(raw, str):
        return {s for s in raw.split() if s}
    if isinstance(raw, (list, tuple)):
        return {str(s) for s in raw}
    return set()


def _matches(scope: str, required: str) -> bool:
    return scope == required or scope.endswith("/" + required) or scope.endswith(required)


def has_scope(claims: dict, required: str) -> bool:
    return any(_matches(s, required) for s in token_scopes(claims))


def authorize(claims: dict, method_arn: str, read_scope: str, write_scope: str) -> bool:
    """True if the token carries the scope required for the requested method."""
    req = required_scope(method_arn, read_scope, write_scope)
    if has_scope(claims, req):
        return True
    return req == read_scope and has_scope(claims, write_scope)
