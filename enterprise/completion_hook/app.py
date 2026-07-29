"""Completion hook: IDP workflow SUCCEEDED -> publish notification to ActiveMQ.

Wired via the upstream PostProcessingLambdaHookFunctionArn mechanism: EventBridge ->
PostProcessingDecompressor -> this function (async). Auth to MQ is via PingFederate:
fetch a Ping JWT (ROPC grant with AD credentials) and present it to ActiveMQ's OAuth2
backend as the STOMP passcode.
"""

import json
import os

from event import parse_completion
from mq_activemq import publish
from ping_token import get_token

PING_TOKEN_URL = os.environ["PING_TOKEN_URL"]
PING_CLIENT_ID = os.environ["PING_CLIENT_ID"]
PING_CLIENT_SECRET_ARN = os.environ["PING_CLIENT_SECRET_ARN"]
PING_USERNAME_SECRET_ARN = os.environ["PING_USERNAME_SECRET_ARN"]
PING_PASSWORD_SECRET_ARN = os.environ["PING_PASSWORD_SECRET_ARN"]
PING_SCOPE = os.environ.get("PING_SCOPE", "")
PING_VALIDATOR_ID = os.environ.get("PING_VALIDATOR_ID", "")

MQ_HOST = os.environ["MQ_HOST"]
MQ_PORT = int(os.environ.get("MQ_PORT", "61617"))
MQ_DESTINATION = os.environ.get("MQ_DESTINATION", "/queue/idp.document.completed")


def handler(event, context):
    message = parse_completion(event)
    body = json.dumps(message).encode()
    message_id = message.get("execution_arn") or getattr(context, "aws_request_id", "")

    token = get_token(
        token_url=PING_TOKEN_URL,
        client_id=PING_CLIENT_ID,
        client_secret_arn=PING_CLIENT_SECRET_ARN,
        username_secret_arn=PING_USERNAME_SECRET_ARN,
        password_secret_arn=PING_PASSWORD_SECRET_ARN,
        scope=PING_SCOPE,
        validator_id=PING_VALIDATOR_ID,
    )

    publish(
        host=MQ_HOST,
        port=MQ_PORT,
        destination=MQ_DESTINATION,
        token=token,
        body=body,
        message_id=message_id,
    )

    return {
        "published": True,
        "document_id": message.get("document_id"),
        "message_id": message_id,
    }
