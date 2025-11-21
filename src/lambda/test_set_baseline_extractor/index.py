# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
import zipfile
import tempfile

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

def handler(event, context):
    """Process SQS messages for baseline ZIP extraction"""
    logger.info(f"Baseline extractor invoked with {len(event['Records'])} SQS messages")
    
    for record in event['Records']:
        try:
            # Parse SQS message
            message_body = json.loads(record['body'])
            test_set_id = message_body['testSetId']
            bucket = message_body['bucket']
            
            logger.info(f"Processing baseline extraction for test set: {test_set_id}")
            
            # Find and extract all ZIP files in the baseline folder
            _extract_all_baseline_zips(bucket, test_set_id)
            
            # Update test set status to COMPLETED
            _update_test_set_status(test_set_id, 'COMPLETED')
            
            logger.info(f"Successfully processed baseline extraction for test set {test_set_id}")
            
        except Exception as e:
            logger.error(f"Error processing SQS message: {str(e)}")
            # Try to update test set status to FAILED if we can extract test set ID
            try:
                message_body = json.loads(record['body'])
                test_set_id = message_body.get('testSetId')
                if test_set_id:
                    _update_test_set_status(test_set_id, 'FAILED', str(e))
            except:
                pass
            raise  # Re-raise to trigger SQS retry/DLQ
    
    return {'statusCode': 200}

def _extract_all_baseline_zips(bucket, test_set_id):
    """Find and extract all ZIP files in the test set baseline folder"""
    baseline_prefix = f"{test_set_id}/baseline/"
    
    # List all objects in the baseline folder
    response = s3.list_objects_v2(Bucket=bucket, Prefix=baseline_prefix)
    
    if 'Contents' not in response:
        error_msg = f"No files found in baseline folder for test set {test_set_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    zip_files = []
    for obj in response['Contents']:
        key = obj['Key']
        if key.lower().endswith('.zip') and not key.endswith('/'):
            zip_files.append(key)
    
    if not zip_files:
        logger.info(f"No ZIP files found in baseline folder for test set {test_set_id}")
        return
    
    logger.info(f"Found {len(zip_files)} ZIP files to extract for test set {test_set_id}")
    
    # Extract each ZIP file
    for zip_key in zip_files:
        _extract_baseline_zip(bucket, zip_key, test_set_id)

def _extract_baseline_zip(bucket, zip_key, test_set_id):
    """Extract ZIP file contents to proper baseline folder structure"""
    
    # Download ZIP file to temporary location
    with tempfile.NamedTemporaryFile() as temp_file:
        s3.download_fileobj(bucket, zip_key, temp_file)
        temp_file.seek(0)
        
        # Extract ZIP contents
        with zipfile.ZipFile(temp_file, 'r') as zip_ref:
            # Get the base filename without .zip extension
            zip_filename = zip_key.split('/')[-1]
            base_name = zip_filename.rsplit('.', 1)[0]  # Remove .zip extension
            
            # Extract each file to proper location
            for file_info in zip_ref.infolist():
                if not file_info.is_dir():
                    # Read file content
                    file_content = zip_ref.read(file_info.filename)
                    
                    # Remove duplicate base name from ZIP path if it exists
                    file_path = file_info.filename
                    if file_path.startswith(f"{base_name}/"):
                        file_path = file_path[len(base_name)+1:]
                    
                    # Create destination key: test-set-id/baseline/base_name/cleaned_path
                    dest_key = f"{test_set_id}/baseline/{base_name}/{file_path}"
                    
                    # Upload to S3
                    s3.put_object(
                        Bucket=bucket,
                        Key=dest_key,
                        Body=file_content
                    )
                    
                    logger.info(f"Extracted: {file_info.filename} -> {dest_key}")
    
    # Delete original ZIP file
    s3.delete_object(Bucket=bucket, Key=zip_key)
    logger.info(f"Deleted original ZIP file: {zip_key}")

def _update_test_set_status(test_set_id, status, error=None):
    """Update test set status in tracking table"""
    table = dynamodb.Table(os.environ['TRACKING_TABLE'])
    
    try:
        update_expression = 'SET #status = :status'
        expression_values = {':status': status}
        expression_names = {'#status': 'Status'}
        
        if error:
            update_expression += ', #error = :error'
            expression_values[':error'] = error
            expression_names['#error'] = 'Error'
        
        table.update_item(
            Key={'PK': f'testset#{test_set_id}', 'SK': 'metadata'},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )
        
        logger.info(f"Updated test set {test_set_id} status to {status}")
        
    except Exception as e:
        logger.error(f"Failed to update test set status for {test_set_id}: {e}")
