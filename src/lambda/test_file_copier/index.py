# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
import concurrent.futures

import boto3
from botocore.exceptions import ClientError
from idp_common.s3 import find_matching_files

# Type: ignore for boto3 resource type inference
dynamodb = boto3.resource('dynamodb')  # type: ignore

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

def handler(event, context):
    """Process file copy jobs from SQS"""
    logger.info(f"File copier invoked with {len(event['Records'])} messages")
    
    for record in event['Records']:
        try:
            message = json.loads(record['body'])
            
            test_run_id = message['testRunId']
            file_pattern = message['filePattern']
            input_bucket = message['inputBucket']
            baseline_bucket = message['baselineBucket']
            tracking_table = message['trackingTable']
            
            logger.info(f"Processing test run {test_run_id} with pattern '{file_pattern}'")
            
            # Update status to RUNNING
            _update_test_run_status(tracking_table, test_run_id, 'RUNNING')
            
            # Find matching files
            matching_files = find_matching_files(input_bucket, file_pattern)
            
            if not matching_files:
                raise ValueError(f"No files found matching pattern: {file_pattern}")
            
            logger.info(f"Found {len(matching_files)} files matching pattern")
            
            # Copy baseline files
            _copy_baseline_files(baseline_bucket, test_run_id, matching_files, tracking_table)
            
            # Copy and process documents
            _copy_and_process_documents(input_bucket, test_run_id, matching_files)
            
            logger.info(f"Completed file copying for test run {test_run_id}")
            
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            # Update test run status to failed
            if 'test_run_id' in locals():
                _update_test_run_status(tracking_table, test_run_id, 'FAILED', str(e))
            raise

def _update_test_run_status(tracking_table, test_run_id, status, error=None):
    """Update test run status in tracking table"""
    try:
        table = dynamodb.Table(tracking_table)  # type: ignore
        update_expression = 'SET #status = :status'
        expression_attribute_names = {'#status': 'Status'}
        expression_attribute_values = {':status': status}
        
        if error:
            update_expression += ', #error = :error'
            expression_attribute_names['#error'] = 'Error'
            expression_attribute_values[':error'] = error
        
        table.update_item(
            Key={'PK': f'testrun#{test_run_id}', 'SK': 'metadata'},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values
        )
        logger.info(f"Updated test run {test_run_id} status to {status}")
    except Exception as e:
        logger.error(f"Failed to update test run status: {e}")

def _copy_baseline_files(baseline_bucket, test_run_id, files, tracking_table):
    """Copy baseline files to test run prefix and validate baseline documents exist"""
    
    def process_baseline_for_file(file_key):
        # Check if baseline document record exists in tracking table
        table = dynamodb.Table(tracking_table)  # type: ignore
        baseline_response = table.get_item(Key={'PK': f'doc#{file_key}', 'SK': 'none'})
        
        if 'Item' not in baseline_response:
            raise ValueError(f"No baseline document record found for {file_key}. Please process this document first and use 'Use as baseline' to create ground truth data.")
        
        baseline_doc = baseline_response['Item']
        
        # Check if baseline has evaluation data (not just a processed document)
        if baseline_doc.get('EvaluationStatus') != 'BASELINE_AVAILABLE':
            raise ValueError(f"Document {file_key} exists but is not marked as baseline. Please use 'Use as baseline' to establish ground truth data.")
        
        # Baseline files are stored with the same key as original files
        baseline_prefix = f"{file_key}/"
        new_prefix = f"{test_run_id}/{file_key}/"
        
        logger.info(f"Looking for baseline files: bucket={baseline_bucket}, prefix={baseline_prefix}")
        
        try:
            # List objects under the baseline prefix
            response = s3.list_objects_v2(Bucket=baseline_bucket, Prefix=baseline_prefix)
            
            if 'Contents' not in response or len(response['Contents']) == 0:
                raise ValueError(f"No baseline files found in S3 for {file_key}. Baseline document record exists but S3 files are missing. Check bucket: {baseline_bucket}, prefix: {baseline_prefix}")
            
            # Copy all files under the prefix
            files_copied = 0
            for obj in response['Contents']:
                source_key = obj['Key']
                # Replace the prefix to create the new key
                new_key = source_key.replace(baseline_prefix, new_prefix, 1)
                
                s3.copy_object(
                    CopySource={'Bucket': baseline_bucket, 'Key': source_key},
                    Bucket=baseline_bucket,
                    Key=new_key
                )
                files_copied += 1
            
            logger.info(f"Copied {files_copied} baseline files: {baseline_prefix} -> {new_prefix}")
            return file_key, True, files_copied, None
            
        except ClientError as e:
            logger.error(f"S3 error for baseline files {baseline_prefix}: {e}")
            if e.response['Error']['Code'] == '404':
                raise ValueError(f"No baseline files found in S3 for {file_key}. Baseline document record exists but S3 files are missing. Check bucket: {baseline_bucket}, prefix: {baseline_prefix}")
            else:
                logger.error(f"Failed to copy baseline files {baseline_prefix}: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to copy baseline files {baseline_prefix}: {e}")
            raise
    
    baseline_files_found = False
    failed_files = []
    
    # Process baseline files in parallel with max 20 concurrent operations
    max_workers = min(20, len(files))
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(process_baseline_for_file, file_key): file_key for file_key in files}
        
        for future in concurrent.futures.as_completed(future_to_file):
            try:
                file_key, success, files_copied, error = future.result(timeout=60)
                if success:
                    baseline_files_found = True
                else:
                    failed_files.append(f"{file_key}: {error}")
            except concurrent.futures.TimeoutError:
                file_key = future_to_file[future]
                logger.error(f"Timeout processing baseline for {file_key}")
                failed_files.append(f"{file_key}: timeout")
            except Exception as e:
                file_key = future_to_file[future]
                logger.error(f"Exception processing baseline for {file_key}: {e}")
                failed_files.append(f"{file_key}: {str(e)}")
    
    if failed_files:
        raise Exception(f"Failed to process baseline files: {failed_files}")
    
    if not baseline_files_found:
        raise ValueError("No baseline files found for any of the test documents. Please create baseline data first by processing documents and using 'Use as baseline'.")

def _copy_and_process_documents(input_bucket, test_run_id, files):
    """Copy documents to test run prefix to trigger processing"""
    
    def copy_single_document(file_key):
        new_key = f"{test_run_id}/{file_key}"
        try:
            s3.copy_object(
                CopySource={'Bucket': input_bucket, 'Key': file_key},
                Bucket=input_bucket,
                Key=new_key
            )
            logger.info(f"Copied document for processing: {file_key} -> {new_key}")
            return file_key, True, None
        except Exception as e:
            logger.error(f"Failed to copy document {file_key}: {e}")
            return file_key, False, str(e)
    
    # Process files in parallel with max 30 concurrent operations
    max_workers = min(30, len(files))
    failed_files = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(copy_single_document, file_key): file_key for file_key in files}
        
        for future in concurrent.futures.as_completed(future_to_file):
            try:
                file_key, success, error = future.result(timeout=30)
                if not success:
                    failed_files.append(f"{file_key}: {error}")
            except concurrent.futures.TimeoutError:
                file_key = future_to_file[future]
                logger.error(f"Timeout copying document {file_key}")
                failed_files.append(f"{file_key}: timeout")
            except Exception as e:
                file_key = future_to_file[future]
                logger.error(f"Exception copying document {file_key}: {e}")
                failed_files.append(f"{file_key}: {str(e)}")
    
    if failed_files:
        raise Exception(f"Failed to copy {len(failed_files)} documents: {failed_files}")
