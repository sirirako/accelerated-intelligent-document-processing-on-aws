"""Completion hook: IDP workflow SUCCEEDED -> publish notification to Amazon MQ.

Wired via the upstream PostProcessingLambdaHookFunctionArn mechanism: EventBridge ->
PostProcessingDecompressor -> this function (async). Auth to MQ is M2M via PingFederate:
fetch a Ping client-credentials JWT and present it to RabbitMQ's OAuth2 backend.
"""

import json
import os

from event import parse_completion
from mq_rabbitmq import publish
from ping_token import get_token

PING_TOKEN_URL = os.environ["PING_TOKEN_URL"]
PING_CLIENT_ID = os.environ["PING_CLIENT_ID"]
PING_CLIENT_SECRET_ARN = os.environ["PING_CLIENT_SECRET_ARN"]
MQ_OAUTH_SCOPE = os.environ.get("MQ_OAUTH_SCOPE", "")

MQ_HOST = os.environ["MQ_HOST"]
MQ_PORT = int(os.environ.get("MQ_PORT", "5671"))
MQ_VHOST = os.environ.get("MQ_VHOST", "/")
MQ_EXCHANGE = os.environ.get("MQ_EXCHANGE", "")
MQ_ROUTING_KEY = os.environ.get("MQ_ROUTING_KEY", "idp.document.completed")


def handler(event, context):
    message = parse_completion(event)
    body = json.dumps(message).encode()
    message_id = message.get("execution_arn") or getattr(context, "aws_request_id", "")

    token = get_token(PING_TOKEN_URL, PING_CLIENT_ID, PING_CLIENT_SECRET_ARN, MQ_OAUTH_SCOPE)

    publish(
        host=MQ_HOST,
        port=MQ_PORT,
        vhost=MQ_VHOST,
        exchange=MQ_EXCHANGE,
        routing_key=MQ_ROUTING_KEY,
        token=token,
        body=body,
        message_id=message_id,
    )

    return {"published": True, "document_id": message.get("document_id"), "message_id": message_id}
