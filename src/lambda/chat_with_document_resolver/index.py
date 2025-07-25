import json
import boto3
import logging
import botocore
import html
import mimetypes
import base64
import hashlib
import os
from urllib.parse import urlparse
from botocore.exceptions import ClientError

# Set up logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
# Get LOG_LEVEL from environment variable with INFO as default

def handler(event, context):
    response_data = {}

    try:
        # logger.info(f"Received event: {json.dumps(event)}")

        objectKey = event['arguments']['s3Uri']
        prompt = event['arguments']['prompt']
        selectedModelId = event['arguments']['modelId']
        logger.info(f"Processing S3 URI: {objectKey}")

        output_bucket = os.environ['OUTPUT_BUCKET']

        bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-west-2')

        # Call Bedrock Runtime to get Python code based on the prompt
        if (len(objectKey)):
            encoded_string = objectKey.encode()
            md5_hash = hashlib.md5(encoded_string)
            hex_representation = md5_hash.hexdigest()

            # full text key
            fulltext_key = objectKey + '/summary/fulltext.txt'

            # read full contents of the object as text
            s3 = boto3.client('s3')
            response = s3.get_object(Bucket=output_bucket, Key=fulltext_key)
            content_str = response['Body'].read().decode('utf-8')

            message = [
                {
                    "role":"user",
                    "content": [
                        {
                            "text": content_str
                        },
                        {
                           "cachePoint" : {
                                'type': 'default'
                            }
                        }
                    ]
                },
                {
                    "role":"user",
                    "content": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ]

            # print('invoking model converse')

            response = bedrock_runtime.converse(
                modelId=selectedModelId,
                messages=message
            )

            token_usage = response['usage']
            # print(f"Input tokens:  {token_usage['inputTokens']}")
            # print(f"Output tokens:  {token_usage['outputTokens']}")
            # print(f"Total tokens:  {token_usage['totalTokens']}")
            # print(f"cacheReadInputTokens:  {token_usage['cacheReadInputTokens']}")
            # print(f"cacheWriteInputTokens:  {token_usage['cacheWriteInputTokens']}")
            # print(f"Stop reason: {response['stopReason']}")

            output_message = response['output']['message']

            model_response_text = ''
            for content in output_message['content']:
                model_response_text += content['text']

            # print output_message

            chat_response = {"cr" : output_message }
            return json.dumps(chat_response)


    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"S3 ClientError: {error_code} - {error_message}")
        
        if error_code == 'NoSuchKey':
            raise Exception(f"File not found: {objectKey}")
        elif error_code == 'NoSuchBucket':
            raise Exception(f"Bucket not found: {output_bucket}")
        else:
            raise Exception(f"Error accessing S3: {error_message}")
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise Exception(f"Error fetching file: {str(e)}")
    
    return response_data