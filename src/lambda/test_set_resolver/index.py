import uuid
import logging
from datetime import datetime
import os
from idp_common.s3 import find_matching_files
from idp_common.dynamodb import DynamoDBClient

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

db_client = DynamoDBClient(table_name=os.environ['TRACKING_TABLE'])

def handler(event, context):
    field_name = event['info']['fieldName']
    logger.info(f"Test set resolver invoked with field_name: {field_name}")
    
    if field_name == 'addTestSet':
        return add_test_set(event['arguments'])
    elif field_name == 'deleteTestSets':
        return delete_test_sets(event['arguments'])
    elif field_name == 'getTestSets':
        return get_test_sets()
    elif field_name == 'listInputBucketFiles':
        return list_input_bucket_files(event['arguments'])
    else:
        raise Exception(f'Unknown field: {field_name}')

def add_test_set(args):
    logger.info(f"Adding test set: {args}")
    
    test_set_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + 'Z'
    
    item = {
        'PK': f'testset#{test_set_id}',
        'SK': 'metadata',
        'id': test_set_id,
        'name': args['name'],
        'filePattern': args['filePattern'],
        'fileCount': args['fileCount'],
        'createdAt': now
    }
    
    db_client.put_item(item)
    logger.info(f"Created test set {test_set_id}")
    
    return {
        'id': test_set_id,
        'name': args['name'],
        'filePattern': args['filePattern'],
        'fileCount': args['fileCount'],
        'createdAt': now
    }

def delete_test_sets(args):
    logger.info(f"Deleting test sets: {args['testSetIds']}")
    
    test_set_ids = args['testSetIds']
    
    for test_set_id in test_set_ids:
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
    
    input_bucket = os.environ['INPUT_BUCKET']
    result = []
    
    for item in items:
        # Get current file count from S3
        current_files = find_matching_files(input_bucket, item['filePattern'])
        current_file_count = len(current_files)
        
        # Update the file count in database
        db_client.update_item(
            key={'PK': item['PK'], 'SK': item['SK']},
            update_expression='SET fileCount = :count',
            expression_attribute_values={':count': current_file_count}
        )
        
        result.append({
            'id': item['id'],
            'name': item['name'],
            'filePattern': item['filePattern'],
            'fileCount': current_file_count,
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
