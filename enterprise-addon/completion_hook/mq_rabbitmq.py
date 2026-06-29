"""Publish to Amazon MQ for RabbitMQ over AMQPS using a Ping JWT.

RabbitMQ's OAuth 2.0 backend authenticates the connection with a bearer token supplied
as the AMQP password. The broker validates the JWT against Ping's JWKS and authorizes
via the token's scopes.
"""

import ssl

import pika


def publish(
    *,
    host: str,
    port: int,
    vhost: str,
    exchange: str,
    routing_key: str,
    token: str,
    body: bytes,
    message_id: str,
) -> None:
    credentials = pika.PlainCredentials(username="", password=token)
    ssl_context = ssl.create_default_context()

    params = pika.ConnectionParameters(
        host=host,
        port=port,
        virtual_host=vhost,
        credentials=credentials,
        ssl_options=pika.SSLOptions(ssl_context),
        socket_timeout=10,
        blocked_connection_timeout=10,
        connection_attempts=2,
        retry_delay=1,
    )

    connection = pika.BlockingConnection(params)
    try:
        channel = connection.channel()
        channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=body,
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
                message_id=message_id,
            ),
        )
    finally:
        try:
            connection.close()
        except Exception:
            pass
