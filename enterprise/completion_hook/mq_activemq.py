"""Publish to ActiveMQ over STOMP+SSL using a Ping JWT as passcode.

ActiveMQ's OAuth2 plugin authenticates the STOMP CONNECT frame using the JWT
presented as the passcode. The broker validates the token against the configured
JWKS endpoint.
"""

import os
import ssl

import stomp


def _get_ssl_context():
    """Build SSL context for ActiveMQ broker connection."""
    ca_path = os.getenv("MQ_CA_CERT_PATH", "")
    if ca_path and os.path.exists(ca_path):
        ctx = ssl.create_default_context(cafile=ca_path)
    else:
        ctx = ssl.create_default_context()

    # ActiveMQ broker may use internal hostname that doesn't match cert
    if os.getenv("MQ_DISABLE_HOST_VERIFY", "").lower() in ("1", "true"):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    return ctx


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
    ssl_ctx = _get_ssl_context()

    conn = stomp.Connection(
        [(host, port)],
        use_ssl=True,
        ssl_context=ssl_ctx,
    )

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
