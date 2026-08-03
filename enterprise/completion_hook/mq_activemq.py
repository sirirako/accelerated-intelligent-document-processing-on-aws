"""Publish to ActiveMQ over STOMP+SSL using a Ping JWT as passcode.

ActiveMQ's OAuth2 plugin authenticates the STOMP CONNECT frame using the JWT
presented as the passcode. The broker validates the token against the configured
JWKS endpoint.

TLS notes (stomp.py 8.2.0):
    stomp.py has no `use_ssl=`/`ssl_context=` constructor arguments — TLS is
    configured with `Transport.set_ssl()`, and the library builds its own
    SSLContext internally at connect time. That internal context only supports
    two modes: with `ca_certs` it uses CERT_REQUIRED *and* hostname verification;
    without it, verification is disabled entirely.

    The customer's broker presents a cert whose CN/SAN does not match the
    hostname we connect to (their own connection URLs use `verifyHostName=false`),
    so neither built-in mode is acceptable: one fails the handshake, the other
    drops chain validation. `_ssl_context_override` scopes a replacement for the
    library's SSLContext constructor over the connect call so we keep CA chain
    validation while disabling only the hostname check.
"""

import contextlib
import logging
import os
import ssl

import stomp
import stomp.transport

logger = logging.getLogger(__name__)


def _resolve_ca_bundle() -> str:
    """Return a path to the CA bundle to validate the broker against.

    Prefers the corporate bundle (TLS inspection re-signs the broker cert), then
    the system default. Returns "" if neither is readable.
    """
    ca_path = os.getenv("MQ_CA_CERT_PATH", "")
    if ca_path:
        if os.path.exists(ca_path):
            logger.info("Using CA bundle %s for the ActiveMQ broker", ca_path)
            return ca_path
        # The bundle ships in the function code (CodeUri -> /var/task/), NOT in a
        # Lambda layer (layers mount at /opt/). It is customer-supplied and only
        # present in the customer's repo, so it is legitimately absent here.
        logger.warning(
            "MQ_CA_CERT_PATH=%s does not exist - falling back to the system CA "
            "store, which fails under TLS inspection. The bundle belongs in the "
            "function's CodeUri directory, not in a layer.",
            ca_path,
        )

    default_ca = ssl.get_default_verify_paths().cafile
    if default_ca and os.path.exists(default_ca):
        return default_ca

    return ""


def _build_ssl_context(ca_bundle: str) -> tuple[ssl.SSLContext, str | None]:
    """Build the SSL context for the broker connection.

    Returns (context, ca_certs_arg). `ca_certs_arg` is what must be handed to
    `set_ssl()`: stomp.py re-asserts `verify_mode` on whatever context it gets,
    deriving it solely from the truthiness of `ca_certs`. Both values therefore
    have to encode the same decision, or the library silently overrides us.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    if os.getenv("MQ_INSECURE_SKIP_VERIFY", "").lower() in ("1", "true"):
        # Escape hatch for broker bring-up only. Never enable in production:
        # it accepts any certificate, including an attacker's.
        logger.warning(
            "MQ_INSECURE_SKIP_VERIFY is set - broker certificate will NOT be "
            "validated. Do not use this outside initial testing."
        )
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        # None keeps the library on its CERT_NONE branch, matching this context.
        return ctx, None

    if not ca_bundle:
        raise RuntimeError(
            "No CA bundle available to validate the ActiveMQ broker. Set "
            "MQ_CA_CERT_PATH to the corporate CA bundle."
        )

    ctx.load_verify_locations(ca_bundle)

    # CERT_REQUIRED with check_hostname=False is a valid combination: it keeps
    # full chain validation while tolerating a CN/SAN mismatch. check_hostname
    # must be cleared before verify_mode is set.
    ctx.check_hostname = os.getenv("MQ_DISABLE_HOST_VERIFY", "").lower() not in (
        "1",
        "true",
    )
    ctx.verify_mode = ssl.CERT_REQUIRED

    return ctx, ca_bundle


@contextlib.contextmanager
def _ssl_context_override(ctx: ssl.SSLContext):
    """Make stomp.transport build our SSLContext instead of its own.

    stomp.transport calls `ssl.SSLContext(DEFAULT_SSL_VERSION)` inline while
    wrapping the socket. Swapping the module-level `ssl` reference for the
    duration of the connect is the only seam available without vendoring a patch
    into the library. The replacement returns our pre-configured context and
    proxies every other attribute through to the real ssl module.
    """

    class _SSLShim:
        def __getattr__(self, name):
            return getattr(ssl, name)

        def SSLContext(self, *_args, **_kwargs):  # noqa: N802 - mirrors ssl API
            return ctx

    original = stomp.transport.ssl
    stomp.transport.ssl = _SSLShim()
    try:
        yield
    finally:
        stomp.transport.ssl = original


def publish(
    *,
    host: str,
    port: int,
    destination: str,
    token: str,
    body: bytes,
    message_id: str,
    content_type: str = "application/json",
) -> None:
    """Publish a message to ActiveMQ via STOMP+SSL.

    Args:
        host: ActiveMQ broker hostname
        port: SSL port (typically 61617)
        destination: Queue or topic (e.g. /queue/idp.document.completed)
        token: Ping JWT used as STOMP passcode
        body: Message body (bytes)
        message_id: Unique message identifier
        content_type: MIME type for the message
    """
    ca_bundle = _resolve_ca_bundle()
    ssl_ctx, ca_certs_arg = _build_ssl_context(ca_bundle)

    conn = stomp.Connection([(host, port)])

    # set_ssl() is what marks this host as TLS; the trust decisions come from the
    # context injected below. ca_certs_arg must agree with that context.
    conn.transport.set_ssl(for_hosts=[(host, port)], ca_certs=ca_certs_arg)

    with _ssl_context_override(ssl_ctx):
        # STOMP CONNECT: login empty, passcode is the JWT
        conn.connect(login="", passcode=token, wait=True)

    try:
        conn.send(
            destination=destination,
            body=body,
            headers={
                "content-type": content_type,
                "message-id": message_id,
                "persistent": "true",
            },
        )
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass
