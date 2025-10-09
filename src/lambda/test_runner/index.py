# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import boto3
import json
import logging
import re
from datetime import datetime
from textwrap import dedent

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
stepfunctions = boto3.client('stepfunctions')

def handler(event, context):
    logger.info(f"Test runner invoked with event: {json.dumps(event)}")
    
    try:
        input_data = event['arguments']['input']
        test_set_name = input_data['testSetName']
        file_pattern = input_data['filePattern']
        
        # Create test run identifier
        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        test_run_id = f"{test_set_name}-{timestamp}"
        
        input_bucket = os.environ['INPUT_BUCKET']
        baseline_bucket = os.environ['BASELINE_BUCKET']
        config_table = os.environ['CONFIG_TABLE']
        tracking_table = os.environ['TRACKING_TABLE']
        
        # Capture current config
        config = _capture_config(config_table)
        
        # Find matching files
        matching_files = _find_matching_files(input_bucket, file_pattern)
        
        if not matching_files:
            raise ValueError(f"No files found matching pattern: {file_pattern}")
        
        # Copy baseline files
        _copy_baseline_files(baseline_bucket, test_run_id, matching_files)
        
        # Copy and process documents
        _copy_and_process_documents(input_bucket, test_run_id, matching_files)
        
        # Store test run metadata
        _store_test_run_metadata(tracking_table, test_run_id, test_set_name, config, matching_files)
        
        return {
            'testRunId': test_run_id,
            'testSetName': test_set_name,
            'status': 'RUNNING',
            'filesCount': len(matching_files),
            'completedFiles': 0,
            'createdAt': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        }
        
    except Exception as e:
        logger.error(f"Error in test runner: {str(e)}")
        raise

def _capture_config(config_table):
    """Capture current configuration"""
    table = dynamodb.Table(config_table)
    
    config = {}
    for config_type in ['Schema', 'Default', 'Custom']:
        try:
            response = table.get_item(Key={'Configuration': config_type})
            if 'Item' in response:
                config[config_type] = response['Item']
        except Exception as e:
            logger.warning(f"Could not retrieve {config_type} config: {e}")
    
    return config

def _find_matching_files(bucket, pattern):
    """Find files matching the pattern"""
    files = []
    
    paginator = s3.get_paginator('list_objects_v2')
    
    try:
        for page in paginator.paginate(Bucket=bucket):
            if 'Contents' in page:
                for obj in page['Contents']:
                    if _matches_pattern(obj['Key'], pattern):
                        files.append(obj['Key'])
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise
    
    return files

def _matches_pattern(key, pattern):
    """Pattern matching using regex"""
    return re.match(f'^{pattern}$', key) is not None

def _copy_baseline_files(baseline_bucket, test_run_id, files):
    """Copy baseline files to test run prefix and validate baseline documents exist"""
    baseline_files_found = False
    
    for file_key in files:
        # Check if baseline document record exists in tracking table
        table = dynamodb.Table(os.environ['TRACKING_TABLE'])
        baseline_response = table.get_item(Key={'PK': f'doc#{file_key}', 'SK': 'none'})
        
        if 'Item' not in baseline_response:
            raise ValueError(f"No baseline document record found for {file_key}. Please process this document first and use 'Use as baseline' to create ground truth data.")
        
        baseline_doc = baseline_response['Item']
        
        # Check if baseline has evaluation data (not just a processed document)
        if baseline_doc.get('EvaluationStatus') != 'BASELINE_AVAILABLE':
            raise ValueError(f"Document {file_key} exists but is not marked as baseline. Please use 'Use as baseline' to establish ground truth data.")
        
        # Find all baseline files for this document (file_key/)
        baseline_prefix = f"{file_key}/"
        file_baseline_found = False
        
        paginator = s3.get_paginator('list_objects_v2')
        try:
            for page in paginator.paginate(Bucket=baseline_bucket, Prefix=baseline_prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        baseline_key = obj['Key']
                        new_key = f"{test_run_id}/{baseline_key}"
                        
                        try:
                            s3.copy_object(
                                CopySource={'Bucket': baseline_bucket, 'Key': baseline_key},
                                Bucket=baseline_bucket,
                                Key=new_key
                            )
                            logger.info(f"Copied baseline file: {baseline_key} -> {new_key}")
                            file_baseline_found = True
                            baseline_files_found = True
                        except Exception as e:
                            logger.error(f"Failed to copy baseline {baseline_key}: {e}")
                            raise
        except Exception as e:
            logger.error(f"Error listing baseline files for {file_key}: {e}")
            raise
        
        if not file_baseline_found:
            raise ValueError(f"No baseline files found in S3 for {file_key}. Baseline document record exists but S3 files are missing.")
    
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

def _store_test_run_metadata(tracking_table, test_run_id, test_set_name, config, files):
    """Store test run metadata in tracking table"""
    table = dynamodb.Table(tracking_table)
    
    try:
        table.put_item(
            Item={
                'PK': f'testrun#{test_run_id}',
                'SK': 'metadata',
                'TestSetName': test_set_name,
                'TestRunId': test_run_id,
                'Status': 'RUNNING',
                'FilesCount': len(files),
                'Files': files,
                'Config': config,
                'CreatedAt': datetime.utcnow().isoformat()
            }
        )
        logger.info(f"Stored test run metadata for {test_run_id}")
    except Exception as e:
        logger.error(f"Failed to store test run metadata: {e}")
        raise
