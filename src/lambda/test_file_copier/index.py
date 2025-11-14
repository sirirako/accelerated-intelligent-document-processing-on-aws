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
            successful_baseline_files = _copy_baseline_files(baseline_bucket, test_run_id, matching_files, tracking_table)
            
            # Copy and process documents (only for files with successful baselines)
            document_failed_count = _copy_and_process_documents(input_bucket, test_run_id, successful_baseline_files)
            
            # Check if all documents failed to copy
            if document_failed_count == len(successful_baseline_files):
                raise ValueError("All documents failed to copy for processing")
            
            # Update failed files count (baseline failures + document copy failures)
            baseline_failed_count = len(matching_files) - len(successful_baseline_files)
            total_failed_count = baseline_failed_count + document_failed_count
            if total_failed_count > 0:
                _update_test_run_status(tracking_table, test_run_id, None, failed_count=total_failed_count)
            
            logger.info(f"Completed file copying for test run {test_run_id}")
            
        except ValueError as e:
            # Business logic errors - don't retry SQS message
            logger.error(f"Business logic error: {str(e)}")
            if 'test_run_id' in locals() and 'matching_files' in locals():
                _update_test_run_status(tracking_table, test_run_id, 'FAILED', str(e), len(matching_files))
        except Exception as e:
            # Infrastructure/system errors - retry SQS message
            logger.error(f"System error processing message: {str(e)}")
            if 'test_run_id' in locals():
                _update_test_run_status(tracking_table, test_run_id, 'FAILED', str(e))
            raise

def _update_test_run_status(tracking_table, test_run_id, status, error=None, failed_count=None):
    """Update test run status in tracking table"""
    try:
        table = dynamodb.Table(tracking_table)  # type: ignore
        update_expression_parts = []
        expression_attribute_names = {}
        expression_attribute_values = {}
        
        if status:
            update_expression_parts.append('#status = :status')
            expression_attribute_names['#status'] = 'Status'
            expression_attribute_values[':status'] = status
        
        if error:
            update_expression_parts.append('#error = :error')
            expression_attribute_names['#error'] = 'Error'
            expression_attribute_values[':error'] = error
        
        if failed_count is not None:
            update_expression_parts.append('BaselineFailedFiles = :failed_count')
            expression_attribute_values[':failed_count'] = failed_count
        
        if update_expression_parts:
            update_expression = 'SET ' + ', '.join(update_expression_parts)
            
            table.update_item(
                Key={'PK': f'testrun#{test_run_id}', 'SK': 'metadata'},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names if expression_attribute_names else None,
                ExpressionAttributeValues=expression_attribute_values
            )
            logger.info(f"Updated test run {test_run_id}")
    except Exception as e:
        logger.error(f"Failed to update test run status: {e}")

def _copy_baseline_files(baseline_bucket, test_run_id, files, tracking_table):
    """Copy baseline files to test run prefix and validate baseline documents exist"""
    
    def process_baseline_for_file(file_key):
        # Check if baseline files exist in S3 bucket
        baseline_prefix = f"{file_key}/"
        new_prefix = f"{test_run_id}/{file_key}/"
        
        logger.info(f"Looking for baseline files: bucket={baseline_bucket}, prefix={baseline_prefix}")
        
        try:
            # List objects under the baseline prefix
            response = s3.list_objects_v2(Bucket=baseline_bucket, Prefix=baseline_prefix)
            
            if 'Contents' not in response or len(response['Contents']) == 0:
                logger.error(f"No baseline files found in S3 for {file_key}. Check bucket: {baseline_bucket}, prefix: {baseline_prefix}")
                return file_key, False, 0, "No baseline files found in S3"
            
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
                logger.error(f"No baseline files found in S3 for {file_key}. Check bucket: {baseline_bucket}, prefix: {baseline_prefix}")
                return file_key, False, 0, "No baseline files found in S3 (404)"
            else:
                logger.error(f"Failed to copy baseline files {baseline_prefix}: {e}")
                return file_key, False, 0, f"S3 error: {str(e)}"
        except Exception as e:
            logger.error(f"Failed to copy baseline files {baseline_prefix}: {e}")
            return file_key, False, 0, f"Exception: {str(e)}"
    
    baseline_files_found = False
    failed_files = []
    successful_files = []
    
    # Process baseline files in parallel with max 20 concurrent operations
    max_workers = min(20, len(files))
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(process_baseline_for_file, file_key): file_key for file_key in files}
        
        for future in concurrent.futures.as_completed(future_to_file):
            try:
                file_key, success, files_copied, error = future.result(timeout=60)
                if success:
                    baseline_files_found = True
                    successful_files.append(file_key)
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
        logger.error(f"Failed to process baseline files for {len(failed_files)} documents: {failed_files}")
    
    if successful_files:
        logger.info(f"Successfully processed baseline files for {len(successful_files)} documents: {successful_files}")
    
    if not baseline_files_found:
        raise ValueError("No baseline files found for any of the test documents. Please create baseline data first by processing documents and using 'Use as baseline'.")
    
    return successful_files

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
    successful_files = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(copy_single_document, file_key): file_key for file_key in files}
        
        for future in concurrent.futures.as_completed(future_to_file):
            try:
                file_key, success, error = future.result(timeout=30)
                if success:
                    successful_files.append(file_key)
                else:
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
        logger.error(f"Failed to copy {len(failed_files)} documents: {failed_files}")
    
    if successful_files:
        logger.info(f"Successfully copied {len(successful_files)} documents for processing: {successful_files}")
    
    return len(failed_files)
