import uuid
import json
import logging
from datetime import datetime
import os
import boto3
from botocore.config import Config
from idp_common.s3 import find_matching_files
from idp_common.dynamodb import DynamoDBClient

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Configure S3 client with S3v4 signature
s3_config = Config(
    signature_version='s3v4',
    s3={'addressing_style': 'path'}
)
s3_client = boto3.client('s3', config=s3_config)
db_client = DynamoDBClient(table_name=os.environ['TRACKING_TABLE'])

def handler(event, context):
    field_name = event['info']['fieldName']
    logger.info(f"Test set resolver invoked with field_name: {field_name}")
    
    if field_name == 'addTestSet':
        return add_test_set(event['arguments'])
    elif field_name == 'addTestSetFromUpload':
        return add_test_set_from_upload(event['arguments'])
    elif field_name == 'deleteTestSets':
        return delete_test_sets(event['arguments'])
    elif field_name == 'getTestSets':
        return get_test_sets()
    elif field_name == 'listInputBucketFiles':
        return list_input_bucket_files(event['arguments'])
    else:
        raise Exception(f'Unknown field: {field_name}')

def add_test_set_from_upload(args):
    logger.info(f"Adding test set from upload: {args}")
    
    input_data = args['input']
    test_set_name = input_data['name']
    
    # Validate that each input file has a corresponding baseline file
    input_file_names = {f['fileName'] for f in input_data['inputFiles']}
    baseline_file_names = {f['fileName'].replace('.zip', '') for f in input_data['baselineFiles']}
    
    missing_baselines = input_file_names - baseline_file_names
    if missing_baselines:
        raise Exception(f"Missing baseline files for: {', '.join(missing_baselines)}")
    
    # Generate test set ID with name_date format, replace spaces with dashes
    today = datetime.utcnow().strftime('%Y%m%d')
    test_set_id = f"{test_set_name.replace(' ', '-')}_{today}"
    
    test_set_bucket = os.environ['TEST_SET_BUCKET']
    
    # Generate presigned URLs for input files
    input_upload_urls = []
    for file_info in input_data['inputFiles']:
        # Sanitize file name to avoid URL encoding issues
        sanitized_file_name = file_info['fileName'].replace(' ', '_')
        key = f"{test_set_id}/input/{sanitized_file_name}"
        
        presigned_post = s3_client.generate_presigned_post(
            Bucket=test_set_bucket,
            Key=key,
            Fields={
                'Content-Type': file_info.get('contentType', 'application/octet-stream')
            },
            Conditions=[
                ['content-length-range', 1, 104857600],  # 1 Byte to 100 MB
                {'Content-Type': file_info.get('contentType', 'application/octet-stream')}
            ],
            ExpiresIn=900  # 15 minutes
        )
        
        logger.info(f"Generated presigned POST for input file {key}: {json.dumps(presigned_post)}")
        
        input_upload_urls.append({
            'fileName': file_info['fileName'],
            'presignedUrl': json.dumps(presigned_post),
            'objectKey': key,
            'usePostMethod': 'True'
        })
    
    # Generate presigned URLs for baseline files
    baseline_upload_urls = []
    for file_info in input_data['baselineFiles']:
        # Sanitize file name to avoid URL encoding issues
        sanitized_file_name = file_info['fileName'].replace(' ', '_')
        key = f"{test_set_id}/baseline/{sanitized_file_name}"
        
        presigned_post = s3_client.generate_presigned_post(
            Bucket=test_set_bucket,
            Key=key,
            Fields={
                'Content-Type': 'application/zip'
            },
            Conditions=[
                ['content-length-range', 1, 104857600],  # 1 Byte to 100 MB
                {'Content-Type': 'application/zip'}
            ],
            ExpiresIn=900  # 15 minutes
        )
        
        logger.info(f"Generated presigned POST for baseline file {key}: {json.dumps(presigned_post)}")
        
        baseline_upload_urls.append({
            'fileName': file_info['fileName'],
            'presignedUrl': json.dumps(presigned_post),
            'objectKey': key,
            'usePostMethod': 'True'
        })
    
    # Add test set entry to tracking table
    now = datetime.utcnow().isoformat() + 'Z'
    file_count = len(input_data['inputFiles'])
    
    item = {
        'PK': f'testset#{test_set_id}',
        'SK': 'metadata',
        'id': test_set_id,
        'name': test_set_name,
        'filePattern': '',  # Empty for uploaded test sets
        'fileCount': file_count,
        'Status': 'QUEUED',
        'createdAt': now
    }
    
    db_client.put_item(item)
    logger.info(f"Created test set {test_set_id} in tracking table with QUEUED status")
    
    # Send message to baseline extractor queue to process ZIP files after upload
    # Use SQS delay to allow client to upload files first
    sqs = boto3.client('sqs')
    baseline_queue_url = os.environ['BASELINE_EXTRACTOR_QUEUE_URL']
    
    total_files = len(input_data['inputFiles']) + len(input_data['baselineFiles'])
    delay_seconds = min(15 + (total_files * 2), 300)  # 15s base + 2s per file, max 5 minutes
    
    sqs.send_message(
        QueueUrl=baseline_queue_url,
        MessageBody=json.dumps({
            'testSetId': test_set_id,
            'bucket': test_set_bucket,
            'trackingTable': os.environ['TRACKING_TABLE']
        }),
        DelaySeconds=delay_seconds
    )
    
    logger.info(f"Queued baseline extraction job for test set {test_set_id}")
    
    return {
        'testSetId': test_set_id,
        'inputUploadUrls': input_upload_urls,
        'baselineUploadUrls': baseline_upload_urls
    }

def add_test_set(args):
    logger.info(f"Adding test set: {args}")
    
    test_set_name = args['name']
    file_count = args['fileCount']
    
    # Generate test set ID with name_date format, replace spaces with dashes
    today = datetime.utcnow().strftime('%Y%m%d')
    test_set_id = f"{test_set_name.replace(' ', '-')}_{today}"
    
    # Create initial test set record
    now = datetime.utcnow().isoformat() + 'Z'
    
    item = {
        'PK': f'testset#{test_set_id}',
        'SK': 'metadata',
        'id': test_set_id,
        'name': test_set_name,
        'filePattern': args['filePattern'],
        'fileCount': file_count,
        'Status': 'QUEUED',
        'createdAt': now
    }
    
    db_client.put_item(item)
    logger.info(f"Created test set {test_set_id} in tracking table")
    
    # Send file copying job to SQS queue
    import boto3
    sqs = boto3.client('sqs')
    queue_url = os.environ['TEST_SET_COPY_QUEUE_URL']
    
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({
            'testSetId': test_set_id,
            'filePattern': args['filePattern'],
            'trackingTable': os.environ['TRACKING_TABLE']
        })
    )
    
    logger.info(f"Queued test set creation job for {test_set_id} with pattern '{args['filePattern']}'")
    
    return {
        'id': test_set_id,
        'name': test_set_name,
        'filePattern': args['filePattern'],
        'fileCount': file_count,
        'status': 'QUEUED',
        'createdAt': now
    }

def delete_test_sets(args):
    logger.info(f"Deleting test sets: {args['testSetIds']}")
    
    test_set_ids = args['testSetIds']
    test_set_bucket = os.environ['TEST_SET_BUCKET']
    
    for test_set_id in test_set_ids:
        # Delete files from test set bucket
        try:
            # List all objects with test_set_id prefix
            response = s3_client.list_objects_v2(
                Bucket=test_set_bucket,
                Prefix=f"{test_set_id}/"
            )
            
            if 'Contents' in response:
                # Delete all objects in the test set folder
                objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
                
                if objects_to_delete:
                    s3_client.delete_objects(
                        Bucket=test_set_bucket,
                        Delete={'Objects': objects_to_delete}
                    )
                    logger.info(f"Deleted {len(objects_to_delete)} files for test set {test_set_id}")
            
        except Exception as e:
            logger.error(f"Failed to delete files for test set {test_set_id}: {str(e)}")
        
        # Delete tracking table record
        db_client.delete_item({
            'PK': f'testset#{test_set_id}',
            'SK': 'metadata'
        })
    
    logger.info(f"Deleted {len(test_set_ids)} test sets")
    return True

def get_test_sets():
    logger.info("Retrieving all test sets")
    
    items = db_client.scan_all(
        filter_expression='begins_with(PK, :pk) AND SK = :sk',
        expression_attribute_values={
            ':pk': 'testset#',
            ':sk': 'metadata'
        }
    )
    result = []
    
    for item in items:
        result.append({
            'id': item['id'],
            'name': item['name'],
            'filePattern': item.get('filePattern', ''),  # Use get() with default
            'fileCount': item['fileCount'],
            'status': item.get('Status'),
            'createdAt': item['createdAt']
        })
    
    logger.info(f"Found {len(result)} test sets")
    return result

def list_input_bucket_files(args):
    logger.info(f"Listing files with pattern: {args['filePattern']}")
    
    file_pattern = args['filePattern']
    input_bucket = os.environ['INPUT_BUCKET']
    
    files = find_matching_files(input_bucket, file_pattern)
    logger.info(f"Found {len(files)} matching files")
    
    return files
