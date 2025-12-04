# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os

import boto3
from idp_common.s3 import find_matching_files  # type: ignore

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

def handler(event, context):
    """Process test set file copy jobs from SQS"""
    logger.info(f"Test set file copier invoked with {len(event['Records'])} messages")
    
    for record in event['Records']:
        try:
            message = json.loads(record['body'])
            
            test_set_id = message['testSetId']
            file_pattern = message['filePattern']
            bucket_type = message['bucketType']
            tracking_table = message['trackingTable']
            
            # Get environment variables
            input_bucket = os.environ['INPUT_BUCKET']
            test_set_bucket = os.environ['TEST_SET_BUCKET']
            baseline_bucket = os.environ['BASELINE_BUCKET']
            
            # Determine source bucket based on bucket type
            if bucket_type == 'input':
                source_bucket = input_bucket
            elif bucket_type == 'testset':
                source_bucket = test_set_bucket
            else:
                raise ValueError(f"Invalid bucket type: {bucket_type}")
            
            logger.info(f"Processing test set {test_set_id} with pattern '{file_pattern}' from {bucket_type} bucket")
            
            # Find matching files in source bucket
            matching_files = find_matching_files(source_bucket, file_pattern)
            
            if not matching_files:
                raise ValueError(f"No files found matching pattern: {file_pattern}")
            
            logger.info(f"Found {len(matching_files)} files matching pattern, matching files {matching_files}")
            
            # Validate baseline folders exist for all input files before copying anything
            missing_baselines = []
            for file_key in matching_files:
                try:
                    if bucket_type == 'testset':
                        # For testset bucket, baseline is in the same bucket under baseline/ path
                        # Extract test set name from file path (assuming format: test_set_name/input/file)
                        path_parts = file_key.split('/')
                        if len(path_parts) >= 3 and path_parts[1] == 'input':
                            test_set_name = path_parts[0]
                            file_name = path_parts[2]
                            baseline_prefix = f"{test_set_name}/baseline/{file_name}/"
                            baseline_check_bucket = source_bucket
                        else:
                            missing_baselines.append(file_key)
                            continue
                    else:
                        # For input bucket, baseline is in separate baseline bucket
                        baseline_prefix = f"{file_key}/"
                        baseline_check_bucket = baseline_bucket
                    
                    # Check if baseline folder exists by listing objects with prefix
                    response = s3.list_objects_v2(Bucket=baseline_check_bucket, Prefix=baseline_prefix, MaxKeys=1)
                    
                    if 'Contents' not in response or len(response['Contents']) == 0:
                        missing_baselines.append(file_key)
                        
                except Exception as e:
                    logger.error(f"Error checking baseline folder {file_key}: {e}")
                    missing_baselines.append(file_key)
            
            if missing_baselines:
                raise ValueError(f"Missing baseline folders for: {', '.join(missing_baselines)}")
            
            # Copy input files to test set bucket
            _copy_files_to_test_set(source_bucket, test_set_bucket, test_set_id, 'input', matching_files)
            
            # Copy baseline folders to test set bucket
            if bucket_type == 'testset':
                _copy_baseline_from_testset(source_bucket, test_set_bucket, test_set_id, matching_files)
            else:
                _copy_files_to_test_set(baseline_bucket, test_set_bucket, test_set_id, 'baseline', matching_files)
            
            logger.info(f"Copied {len(matching_files)} input files and {len(matching_files)} baseline folders")
            
            # Update test set record with completion status
            _update_test_set_status(tracking_table, test_set_id, 'COMPLETED')
            
            logger.info(f"Test set {test_set_id} file copying completed successfully: {len(matching_files)} files")
            
        except Exception as e:
            logger.error(f"Error processing test set {test_set_id}: {str(e)}")
            if 'test_set_id' in locals() and 'tracking_table' in locals():
                _update_test_set_status(tracking_table, test_set_id, 'FAILED', str(e))
    
    return {'statusCode': 200}

def _copy_files_to_test_set(source_bucket, dest_bucket, test_set_id, folder_type, files):
    """Copy files from source bucket to test set bucket folder"""
    
    for file_key in files:
        if folder_type == 'baseline':
            # For baseline, copy entire folder structure
            baseline_prefix = f"{file_key}/"
            dest_prefix = f"{test_set_id}/baseline/{file_key}/"
            
            # List all objects in the baseline folder
            paginator = s3.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=source_bucket, Prefix=baseline_prefix)
            
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        source_key = obj['Key']
                        # Replace the baseline prefix with the test set prefix
                        dest_key = source_key.replace(baseline_prefix, dest_prefix, 1)
                        
                        # Copy file
                        s3.copy_object(
                            CopySource={'Bucket': source_bucket, 'Key': source_key},
                            Bucket=dest_bucket,
                            Key=dest_key
                        )
                        
                        logger.info(f"Copied baseline file: {source_key} -> {dest_bucket}/{dest_key}")
        else:
            # For input files, copy individual file
            source_key = file_key
            dest_key = f"{test_set_id}/{folder_type}/{file_key}"
            
            # Copy file
            s3.copy_object(
                CopySource={'Bucket': source_bucket, 'Key': source_key},
                Bucket=dest_bucket,
                Key=dest_key
            )
            
            logger.info(f"Copied {folder_type} file: {source_key} -> {dest_bucket}/{dest_key}")

def _copy_baseline_from_testset(source_bucket, dest_bucket, test_set_id, files):
    """Copy baseline files from testset bucket where baselines are in test_set/baseline/ path"""
    
    for file_key in files:
        # Extract test set name and file name from path (format: test_set_name/input/file_name)
        path_parts = file_key.split('/')
        if len(path_parts) >= 3 and path_parts[1] == 'input':
            source_test_set_name = path_parts[0]
            file_name = path_parts[2]
            
            # Source baseline path in testset bucket
            source_baseline_prefix = f"{source_test_set_name}/baseline/{file_name}/"
            # Destination baseline path
            dest_baseline_prefix = f"{test_set_id}/baseline/{file_name}/"
            
            # List all objects in the source baseline folder
            paginator = s3.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=source_bucket, Prefix=source_baseline_prefix)
            
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        source_key = obj['Key']
                        # Replace the source baseline prefix with dest baseline prefix
                        dest_key = source_key.replace(source_baseline_prefix, dest_baseline_prefix, 1)
                        
                        # Copy file
                        s3.copy_object(
                            CopySource={'Bucket': source_bucket, 'Key': source_key},
                            Bucket=dest_bucket,
                            Key=dest_key
                        )
                        
                        logger.info(f"Copied testset baseline file: {source_key} -> {dest_bucket}/{dest_key}")
        else:
            logger.warning(f"Unexpected file path format for testset baseline: {file_key}")

def _update_test_set_status(tracking_table, test_set_id, status, error=None):
    """Update test set status in tracking table"""
    table = dynamodb.Table(tracking_table)  # type: ignore
    
    try:
        update_expression = 'SET #status = :status'
        expression_values = {':status': status}
        expression_names = {'#status': 'status'}
        
        if error:
            update_expression += ', #error = :error'
            expression_values[':error'] = error
            expression_names['#error'] = 'error'
        
        table.update_item(
            Key={'PK': f'testset#{test_set_id}', 'SK': 'metadata'},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )
        
        logger.info(f"Updated test set {test_set_id} status to {status}")
        
    except Exception as e:
        logger.error(f"Failed to update test set status for {test_set_id}: {e}")
