# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
from datetime import datetime

import boto3
from botocore.exceptions import ClientError
from idp_common.s3 import find_matching_files

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
stepfunctions = boto3.client('stepfunctions')

def handler(event, context):
    logger.info(f"Test runner invoked with event: {json.dumps(event)}")
    
    try:
        input_data = event['arguments']['input']
        test_set_id = input_data['testSetId']
        context = input_data.get('context', '')
        tracking_table = os.environ['TRACKING_TABLE']
        input_bucket = os.environ['INPUT_BUCKET']
        baseline_bucket = os.environ['BASELINE_BUCKET']
        config_table = os.environ['CONFIG_TABLE']
        
        # Get test set
        test_set = _get_test_set(tracking_table, test_set_id)
        if not test_set:
            raise ValueError(f"Test set with ID '{test_set_id}' not found")
        
        # Create test run identifier using test set name
        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        test_run_id = f"{test_set['name']}-{timestamp}"
        
        matching_files = find_matching_files(input_bucket, test_set['filePattern'])
        
        if not matching_files:
            raise ValueError(f"No files found matching test set pattern: {test_set['filePattern']}")
        
        # Capture current config
        config = _capture_config(config_table)
        
        # Copy baseline files
        _copy_baseline_files(baseline_bucket, test_run_id, matching_files)
        
        # Copy and process documents
        _copy_and_process_documents(input_bucket, test_run_id, matching_files)
        
        # Store test run metadata
        _store_test_run_metadata(tracking_table, test_run_id, test_set['name'], config, matching_files, context)
        
        return {
            'testRunId': test_run_id,
            'testSetName': test_set['name'],
            'status': 'RUNNING',
            'filesCount': len(matching_files),
            'completedFiles': 0,
            'createdAt': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        }
        
    except Exception as e:
        logger.error(f"Error in test runner: {str(e)}")
        raise

def _get_test_set(tracking_table, test_set_id):
    """Get test set by ID"""
    table = dynamodb.Table(tracking_table)  # type: ignore[attr-defined]
    
    try:
        response = table.get_item(
            Key={
                'PK': f'testset#{test_set_id}',
                'SK': 'metadata'
            }
        )
        return response.get('Item')
    except Exception as e:
        logger.error(f"Error getting test set {test_set_id}: {e}")
        return None

def _capture_config(config_table):
    """Capture current configuration"""
    table = dynamodb.Table(config_table)  # type: ignore[attr-defined]
    
    config = {}
    for config_type in ['Schema', 'Default', 'Custom']:
        try:
            response = table.get_item(Key={'Configuration': config_type})
            if 'Item' in response:
                config[config_type] = response['Item']
        except Exception as e:
            logger.warning(f"Could not retrieve {config_type} config: {e}")
    
    return config

def _copy_baseline_files(baseline_bucket, test_run_id, files):
    """Copy baseline files to test run prefix and validate baseline documents exist"""
    baseline_files_found = False
    
    for file_key in files:
        # Check if baseline document record exists in tracking table
        table = dynamodb.Table(os.environ['TRACKING_TABLE'])  # type: ignore[attr-defined]
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
            baseline_files_found = True
            
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
    
    if not baseline_files_found:
        raise ValueError("No baseline files found for any of the test documents. Please create baseline data first by processing documents and using 'Use as baseline'.")

def _copy_and_process_documents(input_bucket, test_run_id, files):
    """Copy documents to test run prefix to trigger processing"""
    for file_key in files:
        new_key = f"{test_run_id}/{file_key}"
        
        try:
            s3.copy_object(
                CopySource={'Bucket': input_bucket, 'Key': file_key},
                Bucket=input_bucket,
                Key=new_key
            )
            logger.info(f"Copied document for processing: {file_key} -> {new_key}")
        except Exception as e:
            logger.error(f"Failed to copy document {file_key}: {e}")
            raise

def _store_test_run_metadata(tracking_table, test_run_id, test_set_name, config, files, context=None):
    """Store test run metadata in tracking table"""
    table = dynamodb.Table(tracking_table)  # type: ignore[attr-defined]
    
    try:
        item = {
            'PK': f'testrun#{test_run_id}',
            'SK': 'metadata',
            'TestSetName': test_set_name,
            'TestRunId': test_run_id,
            'Status': 'RUNNING',
            'FilesCount': len(files),
            'CompletedFiles': 0,
            'FailedFiles': 0,
            'Files': files,
            'Config': config,
            'CreatedAt': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        }
        
        if context:
            item['Context'] = context
            
        table.put_item(Item=item)
        logger.info(f"Stored test run metadata for {test_run_id}")
    except Exception as e:
        logger.error(f"Failed to store test run metadata: {e}")
        raise
