"""
Lambda function to deploy the RealKIE-FCC-Verified dataset from HuggingFace
to the TestSetBucket during stack deployment.
"""

import json
import os
import logging
import boto3
from datetime import datetime
from typing import Dict, Any
import cfnresponse

# Set HuggingFace cache to /tmp (Lambda's writable directory)
os.environ['HF_HOME'] = '/tmp/huggingface'
os.environ['HUGGINGFACE_HUB_CACHE'] = '/tmp/huggingface/hub'

# Lightweight HuggingFace access
from huggingface_hub import hf_hub_download
import pyarrow.parquet as pq

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Environment variables
TESTSET_BUCKET = os.environ.get('TESTSET_BUCKET')
TRACKING_TABLE = os.environ.get('TRACKING_TABLE')

# Constants
DATASET_NAME = 'RealKIE-FCC-Verified'
DATASET_PREFIX = 'realkie-fcc-verified/'
TEST_SET_ID = 'realkie-fcc-verified'


def handler(event, context):
    """
    Main Lambda handler for deploying the FCC dataset.
    """
    logger.info(f"Event: {json.dumps(event)}")
    
    try:
        request_type = event['RequestType']
        
        if request_type == 'Delete':
            # On stack deletion, we leave the data in place
            logger.info("Delete request - keeping dataset in place")
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
            return
        
        # Extract properties
        properties = event['ResourceProperties']
        dataset_version = properties.get('DatasetVersion', '1.0')
        dataset_description = properties.get('DatasetDescription', '')
        
        logger.info(f"Processing dataset version: {dataset_version}")
        
        # Check if dataset already exists with this version
        if check_existing_version(dataset_version):
            logger.info(f"Dataset version {dataset_version} already deployed, skipping")
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {
                'Message': f'Dataset version {dataset_version} already exists'
            })
            return
        
        # Download and deploy the dataset
        result = deploy_dataset(dataset_version, dataset_description)
        
        logger.info(f"Dataset deployment completed: {result}")
        cfnresponse.send(event, context, cfnresponse.SUCCESS, result)
        
    except Exception as e:
        logger.error(f"Error deploying dataset: {str(e)}", exc_info=True)
        cfnresponse.send(event, context, cfnresponse.FAILED, {}, 
                        reason=f"Error deploying dataset: {str(e)}")


def check_existing_version(version: str) -> bool:
    """
    Check if the dataset with the specified version already exists.
    """
    try:
        table = dynamodb.Table(TRACKING_TABLE)
        response = table.get_item(
            Key={
                'PK': f'testset#{TEST_SET_ID}',
                'SK': 'metadata'
            }
        )
        
        if 'Item' in response:
            existing_version = response['Item'].get('datasetVersion', '')
            logger.info(f"Found existing dataset version: {existing_version}")
            
            # Check if version matches and files exist
            if existing_version == version:
                # Verify at least some files exist in S3
                try:
                    response = s3_client.list_objects_v2(
                        Bucket=TESTSET_BUCKET,
                        Prefix=f'{DATASET_PREFIX}input/',
                        MaxKeys=1
                    )
                    if response.get('KeyCount', 0) > 0:
                        logger.info("Files exist in S3, skipping deployment")
                        return True
                except Exception as e:
                    logger.warning(f"Error checking S3 files: {e}")
        
        return False
        
    except Exception as e:
        logger.warning(f"Error checking existing version: {e}")
        return False


def deploy_dataset(version: str, description: str) -> Dict[str, Any]:
    """
    Deploy the dataset by downloading PDFs and ground truth from HuggingFace
    using lightweight hf_hub_download and pyarrow.
    """
    try:
        # Ensure cache directory exists in /tmp (Lambda's writable directory)
        cache_dir = '/tmp/huggingface/hub'
        os.makedirs(cache_dir, exist_ok=True)
        logger.info(f"Using cache directory: {cache_dir}")
        
        logger.info(f"Downloading dataset from HuggingFace: amazon-agi/RealKIE-FCC-Verified")
        
        # Download the parquet file with metadata using hf_hub_download
        parquet_path = hf_hub_download(
            repo_id="amazon-agi/RealKIE-FCC-Verified",
            filename="data/test-00000-of-00001.parquet",
            repo_type="dataset",
            cache_dir=cache_dir
        )
        
        logger.info(f"Downloaded parquet metadata file")
        
        # Read parquet file with pyarrow
        table = pq.read_table(parquet_path)
        data_dict = table.to_pydict()
        
        num_documents = len(data_dict['id'])
        logger.info(f"Loaded {num_documents} documents from parquet")
        
        # Process and upload each document
        file_count = 0
        skipped_count = 0
        
        for idx in range(num_documents):
            try:
                document_id = data_dict['id'][idx]
                json_response = data_dict['json_response'][idx]
                
                if not json_response:
                    logger.warning(f"Skipping {document_id}: no json_response")
                    skipped_count += 1
                    continue
                
                logger.info(f"Processing {document_id}")
                
                # Download PDF file from HuggingFace repository using hf_hub_download
                try:
                    pdf_path = hf_hub_download(
                        repo_id="amazon-agi/RealKIE-FCC-Verified",
                        filename=f"pdfs/{document_id}",
                        repo_type="dataset",
                        cache_dir=cache_dir
                    )
                    
                    # Read the downloaded PDF
                    with open(pdf_path, 'rb') as f:
                        pdf_bytes = f.read()
                    
                    logger.info(f"Downloaded PDF for {document_id} ({len(pdf_bytes):,} bytes)")
                    
                    # Upload PDF to input folder
                    pdf_key = f'{DATASET_PREFIX}input/{document_id}'
                    s3_client.put_object(
                        Bucket=TESTSET_BUCKET,
                        Key=pdf_key,
                        Body=pdf_bytes,
                        ContentType='application/pdf'
                    )
                    
                except Exception as e:
                    logger.error(f"Error downloading/uploading PDF for {document_id}: {e}")
                    skipped_count += 1
                    continue
                
                # Upload ground truth baseline (wrap in inference_result)
                result_json = {"inference_result": json_response}
                result_key = f'{DATASET_PREFIX}baseline/{document_id}/sections/1/result.json'
                s3_client.put_object(
                    Bucket=TESTSET_BUCKET,
                    Key=result_key,
                    Body=json.dumps(result_json, indent=2),
                    ContentType='application/json'
                )
                
                file_count += 1
                
                if file_count % 10 == 0:
                    logger.info(f"Processed {file_count}/{num_documents} documents...")
                    
            except Exception as e:
                logger.error(f"Error processing document {idx} ({document_id}): {e}")
                skipped_count += 1
                continue
        
        logger.info(f"Successfully deployed {file_count} documents (skipped {skipped_count})")
        
        # Create test set record in DynamoDB
        create_testset_record(version, description, file_count)
        
        return {
            'DatasetVersion': version,
            'FileCount': file_count,
            'SkippedCount': skipped_count,
            'Message': f'Successfully deployed {file_count} documents with PDFs and baseline files'
        }
        
    except Exception as e:
        logger.error(f"Error deploying dataset: {e}", exc_info=True)
        raise


def create_testset_record(version: str, description: str, file_count: int):
    """
    Create or update the test set record in DynamoDB.
    """
    table = dynamodb.Table(TRACKING_TABLE)
    timestamp = datetime.utcnow().isoformat() + 'Z'
    
    item = {
        'PK': f'testset#{TEST_SET_ID}',
        'SK': 'metadata',
        'id': TEST_SET_ID,
        'name': DATASET_NAME,
        'filePattern': '',
        'fileCount': file_count,
        'status': 'COMPLETED',
        'createdAt': timestamp,
        'datasetVersion': version,
        'source': 'huggingface:amazon-agi/RealKIE-FCC-Verified'
    }
    
    table.put_item(Item=item)
    logger.info(f"Created test set record in DynamoDB: {TEST_SET_ID}")
