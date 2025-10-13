# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import os
import time
import logging
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from decimal import Decimal

# Custom JSON encoder to handle Decimal objects from DynamoDB
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

dynamodb = boto3.resource('dynamodb')

def handler(event, context):
    """GraphQL resolver for test results queries"""
    field_name = event['info']['fieldName']
    
    if field_name == 'getTestRuns':
        time_period_hours = event.get('arguments', {}).get('timePeriodHours', 2)  # Default 2 hours
        logger.info(f"Processing getTestRuns request with timePeriodHours: {time_period_hours}")
        return get_test_runs(time_period_hours)
    elif field_name == 'getTestRun':
        test_run_id = event['arguments']['testRunId']
        logger.info(f"Processing getTestRun request for test run: {test_run_id}")
        return get_test_results(test_run_id)
    elif field_name == 'getTestRunStatus':
        test_run_id = event['arguments']['testRunId']
        logger.info(f"Processing getTestRunStatus request for test run: {test_run_id}")
        return get_test_run_status(test_run_id)
    elif field_name == 'compareTestRuns':
        test_run_ids = event['arguments']['testRunIds']
        logger.info(f"Processing compareTestRuns request for test runs: {test_run_ids}")
        return compare_test_runs(test_run_ids)
    
    raise ValueError(f"Unknown field: {field_name}")

def compare_test_runs(test_run_ids):
    """Compare multiple test runs"""
    logger.info(f"Comparing test runs: {test_run_ids}")
    
    if not test_run_ids or len(test_run_ids) < 2:
        logger.warning(f"Insufficient test runs for comparison: {len(test_run_ids) if test_run_ids else 0}")
        return {'metrics': [], 'configs': []}
    
    # Get results for each test run
    results = []
    configs = []
    
    for test_run_id in test_run_ids:
        logger.info(f"Getting results for test run: {test_run_id}")
        test_result = get_test_results(test_run_id)
        if test_result:
            logger.info(f"Found results for {test_run_id}: {test_result.keys()}")
            results.append(test_result)
            config = _get_test_run_config(test_run_id)
            configs.append({'testRunId': test_run_id, 'config': config})
        else:
            logger.warning(f"No results found for test run: {test_run_id}")
    
    logger.info(f"Total results found: {len(results)}")
    
    if len(results) < 2:
        logger.warning(f"Insufficient results for comparison: {len(results)}")
        return {'metrics': [], 'configs': []}
    
    metrics_comparison = _build_metrics_comparison(results)
    configs_comparison = _build_config_comparison(configs)
    
    logger.info(f"Configs data: {configs}")
    logger.info(f"Config comparison result: {configs_comparison}")
    
    comparison_result = {
        'metrics': metrics_comparison,
        'configs': configs_comparison
    }
    
    logger.info(f"Final comparison result: {comparison_result}")
    
    return comparison_result

def _format_datetime(dt_str):
    """Format datetime string for GraphQL AWSDateTime type"""
    if not dt_str:
        return None
    # Add Z suffix if not present
    return dt_str + 'Z' if not dt_str.endswith('Z') else dt_str

def get_test_results(test_run_id):
    """Get detailed test results for a specific test run"""
    table = dynamodb.Table(os.environ['TRACKING_TABLE'])
    
    # Get test run metadata
    response = table.get_item(
        Key={'PK': f'testrun#{test_run_id}', 'SK': 'metadata'}
    )
    
    if 'Item' not in response:
        raise ValueError(f"Test run {test_run_id} not found")
        
    metadata = response['Item']
    current_status = metadata.get('Status')
    
    # Update status if not completed
    if current_status not in ['COMPLETE', 'PARTIAL_COMPLETE']:
        status_result = get_test_run_status(test_run_id)
        if status_result:
            current_status = status_result['status']
    
    # Raise error if status is still not complete
    if current_status not in ['COMPLETE', 'PARTIAL_COMPLETE']:
        raise ValueError(f"Test run {test_run_id} is not complete. Current status: {current_status}")
    
    # Check if cached results exist
    if metadata.get('testRunResult') is not None:
        logger.info(f"Retrieved cached testRunResult for test run: {test_run_id}")
        return metadata.get('testRunResult')
    
    # Calculate metrics if not cached
    evaluation_metrics = _query_evaluation_metrics(test_run_id)
    # Build result with native types (keep Decimals for DynamoDB compatibility)
    result = {
        'testRunId': test_run_id,
        'testSetName': metadata.get('TestSetName'),
        'status': current_status,
        'filesCount': metadata.get('FilesCount', 0),
        'completedFiles': metadata.get('CompletedFiles', 0),
        'failedFiles': metadata.get('FailedFiles', 0),
        'accuracySimilarity': evaluation_metrics.get('accuracy_similarity'),
        'confidenceSimilarity': evaluation_metrics.get('confidence_similarity'),
        'baseline': evaluation_metrics.get('baseline', {}),
        'test': evaluation_metrics.get('test', {}),
        'createdAt': _format_datetime(metadata.get('CreatedAt')),
        'completedAt': _format_datetime(metadata.get('CompletedAt'))
    }

    # Cache results (DynamoDB handles Decimals natively)
    try:
        logger.info(f"Caching test results for test run: {test_run_id}")
        
        # Convert floats to Decimals for DynamoDB storage
        def float_to_decimal(obj):
            if isinstance(obj, float):
                return Decimal(str(obj))
            elif isinstance(obj, dict):
                return {k: float_to_decimal(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [float_to_decimal(v) for v in obj]
            return obj
        
        table.update_item(
            Key={'PK': f'testrun#{test_run_id}', 'SK': 'metadata'},
            UpdateExpression='SET testRunResult = :testRunResult',
            ExpressionAttributeValues={':testRunResult': float_to_decimal(result)}
        )
        logger.info(f"Successfully cached test results for test run: {test_run_id}")
    except Exception as e:
        logger.warning(f"Failed to cache results for {test_run_id}: {e}")
    
    logger.info(f"Returning test results for test run: {test_run_id}")
    return result

def get_test_runs(time_period_hours=2):
    """Get list of test runs within specified time period"""
    table = dynamodb.Table(os.environ['TRACKING_TABLE'])
    
    # Validate and sanitize time_period_hours
    if time_period_hours is None or not isinstance(time_period_hours, (int, float)):
        time_period_hours = 2  # Default to 2 hours
    
    # Calculate cutoff time
    cutoff_time = datetime.utcnow() - timedelta(hours=time_period_hours)
    cutoff_iso = cutoff_time.isoformat() + 'Z'
    
    logger.info(f"Fetching test runs created after: {cutoff_iso}")
    logger.info(f"Current UTC time: {datetime.utcnow().isoformat()}Z")
    logger.info(f"Time period hours: {time_period_hours}")
    
    # Handle pagination for DynamoDB scan
    items = []
    scan_kwargs = {
        'FilterExpression': 'begins_with(PK, :pk) AND SK = :sk AND CreatedAt >= :cutoff',
        'ExpressionAttributeValues': {
            ':pk': 'testrun#',
            ':sk': 'metadata',
            ':cutoff': cutoff_iso
        }
    }
    
    while True:
        response = table.scan(**scan_kwargs)
        items.extend(response.get('Items', []))
        
        if 'LastEvaluatedKey' not in response:
            break
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
    
    logger.info(f"DynamoDB scan completed. Items found: {len(items)}")
    if items:
        logger.info(f"Sample item CreatedAt: {items[0].get('CreatedAt')}")
    else:
        logger.info("No items found in scan")
    
    test_runs = [{
        'testRunId': item['TestRunId'],
        'testSetName': item.get('TestSetName'),
        'status': item.get('Status'),
        'filesCount': item.get('FilesCount', 0),
        'completedFiles': item.get('CompletedFiles', 0),
        'failedFiles': item.get('FailedFiles', 0),
        'createdAt': _format_datetime(item.get('CreatedAt')),
        'completedAt': _format_datetime(item.get('CompletedAt'))
    } for item in items]
    
    # Sort by createdAt descending (most recent first)
    # Handle None values and convert to datetime for proper sorting
    def sort_key(test_run):
        created_at = test_run.get('createdAt')
        if not created_at:
            return '1970-01-01T00:00:00Z'  # Very old date for None values
        return created_at
    
    test_runs.sort(key=sort_key, reverse=True)
    
    return test_runs

def get_test_run_status(test_run_id):
    """Get lightweight status for specific test run - checks both document and evaluation status"""
    table = dynamodb.Table(os.environ['TRACKING_TABLE'])
    
    try:
        logger.info(f"Getting test run status for: {test_run_id}")
        
        # Get test run metadata
        response = table.get_item(
            Key={'PK': f'testrun#{test_run_id}', 'SK': 'metadata'}
        )
        
        if 'Item' not in response:
            logger.warning(f"Test run metadata not found for: {test_run_id}")
            return None
            
        item = response['Item']
        files = item.get('Files', [])
        files_count = len(files)
        
        logger.info(f"Test run {test_run_id}: Found {files_count} files: {files}")
        
        # Always check actual document status from tracking table
        completed_files = 0
        failed_files = 0
        evaluating_files = 0
        
        for file_key in files:
            logger.info(f"Checking file: {file_key} for test run: {test_run_id}")
            doc_response = table.get_item(
                Key={'PK': f'doc#{test_run_id}/{file_key}', 'SK': 'none'}
            )
            if 'Item' in doc_response:
                doc_status = doc_response['Item'].get('ObjectStatus', 'PROCESSING')
                eval_status = doc_response['Item'].get('EvaluationStatus', 'PENDING')
                logger.info(f"File {file_key}: ObjectStatus={doc_status}, EvaluationStatus={eval_status}")
                
                if doc_status == 'COMPLETED':
                    # Check if evaluation is also complete
                    if eval_status in ['COMPLETED', 'BASELINE_AVAILABLE', 'NO_BASELINE']:
                        completed_files += 1
                        logger.info(f"File {file_key}: counted as completed")
                    elif eval_status in ['RUNNING', 'PENDING']:
                        evaluating_files += 1
                        logger.info(f"File {file_key}: counted as evaluating")
                    else:
                        # Evaluation failed but document completed
                        completed_files += 1
                        logger.info(f"File {file_key}: counted as completed (eval failed)")
                elif doc_status in ['FAILED', 'ERROR']:
                    failed_files += 1
                    logger.info(f"File {file_key}: counted as failed")
                else:
                    logger.info(f"File {file_key}: still processing (status: {doc_status})")
            else:
                logger.warning(f"Document not found: doc#{test_run_id}/{file_key}")
        
        logger.info(f"Test run {test_run_id} counts: completed={completed_files}, failed={failed_files}, evaluating={evaluating_files}, total={files_count}")
        
        # Determine overall test run status based on document and evaluation states
        if completed_files == files_count and files_count > 0:
            overall_status = 'COMPLETE'
        elif failed_files > 0 and (completed_files + failed_files + evaluating_files) == files_count:
            overall_status = 'PARTIAL_COMPLETE'
        elif evaluating_files > 0:
            overall_status = 'EVALUATING'
        elif completed_files + failed_files + evaluating_files < files_count:
            overall_status = 'RUNNING'
        else:
            overall_status = item.get('Status', 'RUNNING')
        
        # Auto-update database metadata if calculated status differs from stored status
        stored_status = item.get('Status', 'RUNNING')
        if overall_status != stored_status:
            logger.info(f"Auto-updating test run {test_run_id} status from {stored_status} to {overall_status}")
            try:
                table.update_item(
                    Key={'PK': f'testrun#{test_run_id}', 'SK': 'metadata'},
                    UpdateExpression='SET #status = :status, #completedAt = :completedAt, CompletedFiles = :completedFiles, FailedFiles = :failedFiles',
                    ExpressionAttributeNames={'#status': 'Status', '#completedAt': 'CompletedAt'},
                    ExpressionAttributeValues={
                        ':status': overall_status,
                        ':completedAt': datetime.utcnow().isoformat() + 'Z' if overall_status in ['COMPLETE', 'PARTIAL_COMPLETE'] else item.get('CompletedAt'),
                        ':completedFiles': completed_files,
                        ':failedFiles': failed_files
                    }
                )
                logger.info(f"Successfully updated test run {test_run_id} status to {overall_status}")
            except Exception as e:
                logger.error(f"Failed to auto-update test run {test_run_id} status: {e}")
        
        progress = (completed_files / files_count * 100) if files_count > 0 else 0
        
        result = {
            'testRunId': test_run_id,
            'status': overall_status,
            'filesCount': files_count,
            'completedFiles': completed_files,
            'failedFiles': failed_files,
            'evaluatingFiles': evaluating_files,
            'progress': progress
        }
        
        logger.info(f"Test run {test_run_id} final result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error getting test run status for {test_run_id}: {e}")
        return None
    
def _parse_s3_uri(uri):
    """Parse S3 URI into bucket and key"""
    if uri and uri.startswith('s3://'):
        parts = uri[5:].split('/', 1)
        if len(parts) == 2:
            return parts[0], parts[1]
    return None, None

def _calculate_accuracy_from_data(test_data, baseline_data):
    """Calculate accuracy as percentage change from baseline with breakdown"""
    try:
        if not test_data or not baseline_data:
            return None, {}
            
        test_metrics = test_data.get('overall_metrics', {})
        baseline_metrics = baseline_data.get('overall_metrics', {})
        
        if not test_metrics or not baseline_metrics:
            return None, {}
            
        # Calculate percentage differences for each metric
        total_percentage_diff = 0
        metric_count = 0
        accuracy_breakdown = {}
        
        for key in baseline_metrics:
            if key in test_metrics and baseline_metrics[key] > 0:
                baseline_value = baseline_metrics[key]
                test_value = test_metrics[key]
                # Calculate (test - baseline) / baseline * 100
                percentage_diff = ((test_value - baseline_value) / baseline_value) * 100
                total_percentage_diff += percentage_diff
                metric_count += 1
                
                # Store breakdown data
                accuracy_breakdown[f"{key}_accuracy_similarity"] = percentage_diff
                accuracy_breakdown[f"test_{key}"] = test_value
                accuracy_breakdown[f"baseline_{key}"] = baseline_value
        
        # Return average percentage difference and breakdown
        overall_accuracy = total_percentage_diff / metric_count if metric_count > 0 else None
        return overall_accuracy, accuracy_breakdown
        
    except Exception as e:
        logger.warning(f"Error calculating accuracy from data: {e}")
        return None

def _calculate_confidence_from_data(test_data, baseline_data):
    """Calculate confidence from downloaded report data"""
    try:
        if not test_data or not baseline_data:
            return None, {}
            
        # Extract confidence scores from all sections (same logic as original)
        test_confidences = []
        baseline_confidences = []
        
        for section in test_data.get('section_results', []):
            for attr in section.get('attributes', []):
                if attr.get('confidence') is not None:
                    test_confidences.append(float(attr['confidence']))
        
        for section in baseline_data.get('section_results', []):
            for attr in section.get('attributes', []):
                if attr.get('confidence') is not None:
                    baseline_confidences.append(float(attr['confidence']))
        
        if not test_confidences or not baseline_confidences:
            return None, {}
        
        # Calculate average confidence for each
        test_avg_confidence = sum(test_confidences) / len(test_confidences)
        baseline_avg_confidence = sum(baseline_confidences) / len(baseline_confidences)
        
        # Calculate similarity (percentage difference) - test vs baseline
        if baseline_avg_confidence > 0:
            percentage_diff = ((test_avg_confidence - baseline_avg_confidence) / baseline_avg_confidence) * 100
            similarity = percentage_diff  # Positive if test has higher confidence (good)
        else:
            similarity = 0.0
        
        # Create breakdown data
        confidence_breakdown = {
            'baseline_confidence': baseline_avg_confidence,
            'test_confidence': test_avg_confidence,
            'confidence_similarity': similarity
        }
        
        logger.info(f"Confidence comparison: test_avg={test_avg_confidence:.3f}, baseline_avg={baseline_avg_confidence:.3f}, similarity={similarity:.1f}%")
        return similarity, confidence_breakdown
        
    except Exception as e:
        logger.warning(f"Error calculating confidence from data: {e}")
        return None, {}

def _query_evaluation_metrics(test_run_id):
    """Query evaluation reports for accuracy, cost, and usage metrics with baseline comparison"""
    start_time = time.time()
    logger.info(f"Starting accuracy metrics query for test run: {test_run_id}")
    
    table = dynamodb.Table(os.environ['TRACKING_TABLE'])
    
    try:
        # Scan for documents for this test run with pagination
        scan_start = time.time()
        items = []
        scan_kwargs = {
            'FilterExpression': 'begins_with(PK, :pk) AND SK = :sk',
            'ExpressionAttributeValues': {
                ':pk': f'doc#{test_run_id}/',
                ':sk': 'none'
            }
        }
        
        while True:
            response = table.scan(**scan_kwargs)
            items.extend(response.get('Items', []))
            
            if 'LastEvaluatedKey' not in response:
                break
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        
        scan_time = time.time() - scan_start
        logger.info(f"DynamoDB scan completed in {scan_time:.2f}s")
        if not items:
            raise ValueError(f"No documents found for test run {test_run_id}")
        
        logger.info(f"Found {len(items)} documents to process")
        
        # Process documents in parallel
        
        def process_document(item):
            doc_start = time.time()
            local_s3 = boto3.client('s3')
            local_table = dynamodb.Table(os.environ['TRACKING_TABLE'])
            
            doc_key = item['PK'].replace('doc#', '')
            filename = doc_key.split('/', 1)[1]
            logger.info(f"Starting processing document: {filename}")
            
            # Get baseline document record
            baseline_start = time.time()
            baseline_response = local_table.get_item(Key={'PK': f'doc#{filename}', 'SK': 'none'})
            baseline_time = time.time() - baseline_start
            logger.info(f"Baseline lookup for {filename}: {baseline_time:.2f}s")
            
            if 'Item' not in baseline_response:
                logger.warning(f"No baseline found for {filename}")
                return None
                
            baseline_doc = baseline_response['Item']
            test_evaluation_uri = item.get('EvaluationReportUri')
            baseline_evaluation_uri = baseline_doc.get('EvaluationReportUri')
            
            if not (test_evaluation_uri and baseline_evaluation_uri):
                logger.warning(f"Missing evaluation URIs for {filename}")
                return {'accuracy': None, 'confidence': None, 'cost_comparison': None, 'usage_comparison': {}}
            
            # Download all S3 files concurrently
            download_start = time.time()
            logger.info(f"Starting concurrent S3 downloads for {filename}")
            
            def download_file(uri, file_type):
                try:
                    json_uri = uri.replace('report.md', 'results.json')
                    bucket, key = _parse_s3_uri(json_uri)
                    if bucket and key:
                        obj = local_s3.get_object(Bucket=bucket, Key=key)
                        data = json.loads(obj['Body'].read())
                        logger.info(f"Downloaded {file_type} for {filename}")
                        return data
                except Exception as e:
                    logger.warning(f"Failed to download {file_type} for {filename}: {e}")
                return None
            
            # Download both evaluation reports concurrently
            with ThreadPoolExecutor(max_workers=2) as download_executor:
                test_future = download_executor.submit(download_file, test_evaluation_uri, "test report")
                baseline_future = download_executor.submit(download_file, baseline_evaluation_uri, "baseline report")
                
                test_data = test_future.result(timeout=30)
                baseline_data = baseline_future.result(timeout=30)
            
            download_time = time.time() - download_start
            logger.info(f"S3 downloads for {filename} completed in {download_time:.2f}s")
            
            # Process data concurrently
            concurrent_start = time.time()
            logger.info(f"Starting concurrent processing for {filename}")
            
            def get_accuracy():
                op_start = time.time()
                result, breakdown = _calculate_accuracy_from_data(test_data, baseline_data)
                op_time = time.time() - op_start
                logger.info(f"Accuracy calculation for {filename}: {op_time:.2f}s")
                return result, breakdown
            
            def get_confidence():
                op_start = time.time()
                result, breakdown = _calculate_confidence_from_data(test_data, baseline_data)
                op_time = time.time() - op_start
                logger.info(f"Confidence calculation for {filename}: {op_time:.2f}s")
                return result, breakdown
            
            def get_cost_comparison():
                op_start = time.time()
                # Get completion dates from already-loaded tracking records
                test_completion_date = None
                baseline_completion_date = None
                
                # Extract completion date from test document (item)
                if 'CompletionTime' in item:
                    completion_time = item['CompletionTime']
                    completion_date = datetime.fromisoformat(completion_time)
                    test_completion_date = completion_date.strftime('%Y-%m-%d')
                
                # Extract completion date from baseline document (baseline_doc)
                if 'CompletionTime' in baseline_doc:
                    completion_time = baseline_doc['CompletionTime']
                    completion_date = datetime.fromisoformat(completion_time)
                    baseline_completion_date = completion_date.strftime('%Y-%m-%d')
                
                result = _compare_document_costs(doc_key, filename, test_completion_date, baseline_completion_date)
                op_time = time.time() - op_start
                logger.info(f"Cost comparison for {filename}: {op_time:.2f}s")
                return result
            
            def get_usage_comparison():
                op_start = time.time()
                test_metering = item.get('Metering', {})
                baseline_metering = baseline_doc.get('Metering', {})
                result = _compare_metering_usage(test_metering, baseline_metering) if test_metering and baseline_metering else {}
                op_time = time.time() - op_start
                logger.info(f"Usage comparison for {filename}: {op_time:.2f}s")
                return result
            
            # Execute processing concurrently
            with ThreadPoolExecutor(max_workers=4) as process_executor:
                logger.info(f"Submitting 4 concurrent processing tasks for {filename}")
                accuracy_future = process_executor.submit(get_accuracy)
                confidence_future = process_executor.submit(get_confidence)
                cost_future = process_executor.submit(get_cost_comparison)
                usage_future = process_executor.submit(get_usage_comparison)
                
                # Collect results
                accuracy = confidence = cost_comparison = None
                usage_comparison = {}
                
                try:
                    accuracy, accuracy_breakdown = accuracy_future.result(timeout=30)
                except Exception as e:
                    logger.warning(f"Accuracy calculation failed for {filename}: {e}")
                    accuracy, accuracy_breakdown = None, {}
                
                try:
                    confidence, confidence_breakdown = confidence_future.result(timeout=30)
                except Exception as e:
                    logger.warning(f"Confidence calculation failed for {filename}: {e}")
                    confidence, confidence_breakdown = None, {}
                
                try:
                    cost_comparison = cost_future.result(timeout=30)
                except Exception as e:
                    logger.warning(f"Cost comparison failed for {filename}: {e}")
                
                try:
                    usage_comparison = usage_future.result(timeout=30)
                except Exception as e:
                    logger.warning(f"Usage comparison failed for {filename}: {e}")
                    usage_comparison = {}
            
            concurrent_time = time.time() - concurrent_start
            doc_time = time.time() - doc_start
            logger.info(f"Concurrent processing for {filename} completed in {concurrent_time:.2f}s")
            logger.info(f"Document {filename} total processing time: {doc_time:.2f}s")
            
            return {
                'accuracy': accuracy,
                'confidence': confidence,
                'cost_comparison': cost_comparison,
                'usage_comparison': usage_comparison,
                'accuracy_breakdown': accuracy_breakdown,
                'confidence_breakdown': confidence_breakdown
            }
        
        # Execute in parallel with max 5 threads
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_item = {executor.submit(process_document, item): item for item in items}
            for future in as_completed(future_to_item):
                result = future.result()
                if result:
                    results.append(result)
        
        # Aggregate results
        total_accuracy = 0
        total_confidence = 0
        doc_count = 0
        confidence_count = 0
        final_cost_metrics = {}
        final_usage_metrics = {}
        final_accuracy_metrics = {}
        
        for result in results:
            if result['accuracy'] is not None:
                total_accuracy += result['accuracy']
                doc_count += 1
            
            if result['confidence'] is not None:
                total_confidence += result['confidence']
                confidence_count += 1
            
            if result['cost_comparison']:
                final_cost_metrics.update(result['cost_comparison'])
            
            if result['usage_comparison']:
                final_usage_metrics.update(result['usage_comparison'])
                
            if result['accuracy_breakdown']:
                final_accuracy_metrics.update(result['accuracy_breakdown'])
                
            if result['confidence_breakdown']:
                final_accuracy_metrics.update(result['confidence_breakdown'])
                # Store the confidence similarity for use in the response
                final_accuracy_metrics['confidence_similarity'] = result['confidence_breakdown'].get('confidence_similarity', 0)
        
        # Aggregate metrics by context - now using actual baseline/test data
        # Extract cost and usage data from the actual comparison results
        baseline_cost = {'total_cost': 0}
        test_cost = {'total_cost': 0}
        baseline_usage = {}
        test_usage = {}
        
        # Aggregate from individual document results
        for result in results:
            # Extract cost data from cost_comparison
            if result.get('cost_comparison'):
                cost_data = result['cost_comparison']
                if isinstance(cost_data, dict):
                    # Get baseline and test cost structures
                    baseline_data = cost_data.get('baseline', {})
                    test_data = cost_data.get('test', {})
                    
                    # Add total costs
                    baseline_cost['total_cost'] += baseline_data.get('total_cost', 0)
                    test_cost['total_cost'] += test_data.get('total_cost', 0)
                    
                    # Aggregate context-level costs
                    for context, services in baseline_data.items():
                        if context != 'total_cost' and isinstance(services, dict):
                            if context not in baseline_cost:
                                baseline_cost[context] = {}
                            for service, cost in services.items():
                                baseline_cost[context][service] = baseline_cost[context].get(service, 0) + cost
                    
                    for context, services in test_data.items():
                        if context != 'total_cost' and isinstance(services, dict):
                            if context not in test_cost:
                                test_cost[context] = {}
                            for service, cost in services.items():
                                test_cost[context][service] = test_cost[context].get(service, 0) + cost
            
            # Extract usage data from usage_comparison  
            if result.get('usage_comparison'):
                usage_data = result['usage_comparison']
                if isinstance(usage_data, dict):
                    # Get baseline and test usage structures
                    baseline_usage_data = usage_data.get('baseline', {})
                    test_usage_data = usage_data.get('test', {})
                    
                    # Aggregate usage metrics - maintain original format
                    for service, metrics in baseline_usage_data.items():
                        if isinstance(metrics, dict):
                            baseline_usage[service] = baseline_usage.get(service, {})
                            for metric, value in metrics.items():
                                baseline_usage[service][metric] = baseline_usage[service].get(metric, 0) + value
                    
                    for service, metrics in test_usage_data.items():
                        if isinstance(metrics, dict):
                            test_usage[service] = test_usage.get(service, {})
                            for metric, value in metrics.items():
                                test_usage[service][metric] = test_usage[service].get(metric, 0) + value
        
        if doc_count > 0:
            total_time = time.time() - start_time
            logger.info(f"Accuracy metrics query completed in {total_time:.2f}s for {doc_count} documents")
            return {
                'accuracy_similarity': total_accuracy / doc_count,
                'confidence_similarity': total_confidence / confidence_count if confidence_count > 0 else None,
                'baseline': json.dumps({
                    'cost': baseline_cost,
                    'usage': baseline_usage,
                    'accuracy': {
                        'precision': final_accuracy_metrics.get('baseline_precision', 0),
                        'recall': final_accuracy_metrics.get('baseline_recall', 0),
                        'f1_score': final_accuracy_metrics.get('baseline_f1_score', 0),
                        'accuracy': final_accuracy_metrics.get('baseline_accuracy', 0)
                    },
                    'confidence': {
                        'average_confidence': final_accuracy_metrics.get('baseline_confidence', 0.85),
                        'baseline_confidence': final_accuracy_metrics.get('baseline_confidence', 0.85),
                        'test_confidence': final_accuracy_metrics.get('test_confidence', total_confidence / confidence_count if confidence_count > 0 else None),
                        'confidence_similarity': final_accuracy_metrics.get('confidence_similarity', 0)
                    }
                }, cls=DecimalEncoder),
                'test': json.dumps({
                    'cost': test_cost,
                    'usage': test_usage,
                    'accuracy': {
                        'precision': final_accuracy_metrics.get('test_precision', 0),
                        'recall': final_accuracy_metrics.get('test_recall', 0),
                        'f1_score': final_accuracy_metrics.get('test_f1_score', 0),
                        'accuracy': final_accuracy_metrics.get('test_accuracy', 0)
                    },
                    'confidence': {
                        'average_confidence': final_accuracy_metrics.get('test_confidence', total_confidence / confidence_count if confidence_count > 0 else None),
                        'baseline_confidence': final_accuracy_metrics.get('baseline_confidence', 0.85),
                        'test_confidence': final_accuracy_metrics.get('test_confidence', total_confidence / confidence_count if confidence_count > 0 else None),
                        'confidence_similarity': final_accuracy_metrics.get('confidence_similarity', 0)
                    }
                }, cls=DecimalEncoder)
            }
    
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"Error querying accuracy metrics for {test_run_id} after {total_time:.2f}s: {e}")
        raise


def _get_document_costs_from_reporting_db(document_id, completion_date):
    """Get actual costs from S3 Parquet files using provided completion date"""
    try:
        import pyarrow.compute as pc
        import pyarrow.fs as fs
        import pyarrow.parquet as pq
        
        # Get reporting bucket from environment
        reporting_bucket = os.environ.get('REPORTING_BUCKET')
        if not reporting_bucket:
            return {}
        
        logger.info(f"Using completion date {completion_date} for document {document_id}")
        
        # List files in the specific date partition
        s3 = boto3.client('s3')
        partition_prefix = f"metering/date={completion_date}/"
        
        response = s3.list_objects_v2(Bucket=reporting_bucket, Prefix=partition_prefix)
        
        if 'Contents' not in response:
            logger.warning(f"No files found in partition {completion_date}")
            return {}
        
        # Find the parquet file for this document
        document_pattern = document_id.replace('/', '_')
        
        for obj in response['Contents']:
            if obj['Key'].endswith('_results.parquet') and document_pattern in obj['Key']:
                logger.info(f"Reading parquet file: {obj['Key']}")
                
                # Read parquet file using pyarrow
                s3_fs = fs.S3FileSystem()
                parquet_file = f"{reporting_bucket}/{obj['Key']}"
                
                table_data = pq.read_table(parquet_file, filesystem=s3_fs)
                
                # Filter by document_id if column exists
                if 'document_id' in table_data.column_names:
                    mask = pc.equal(table_data['document_id'], document_id)
                    table_data = table_data.filter(mask)
                
                if table_data.num_rows == 0:
                    return {}
                
                # Convert to Python dict for processing
                data = table_data.to_pydict()
                
                # Group and sum costs manually
                cost_groups = {}
                for i in range(len(data['context'])):
                    context = data['context'][i]
                    service_api = data['service_api'][i]
                    unit = data['unit'][i]
                    cost = float(data['estimated_cost'][i])
                    
                    key = f"{context}_{service_api}_{unit}"
                    cost_groups[key] = cost_groups.get(key, 0) + cost
                
                return cost_groups
        
        logger.warning(f"No parquet file found for {document_id} in {completion_date}")
        return {}
        
    except Exception as e:
        logger.warning(f"Failed to get costs from parquet for {document_id}: {e}")
        return {}

def _compare_document_costs(test_document_id, baseline_document_id, test_completion_date=None, baseline_completion_date=None):
    """Compare actual costs between test and baseline documents"""
    
    # Run both Parquet queries in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        test_future = executor.submit(_get_document_costs_from_reporting_db, test_document_id, test_completion_date)
        baseline_future = executor.submit(_get_document_costs_from_reporting_db, baseline_document_id, baseline_completion_date)
        
        test_costs = test_future.result()
        baseline_costs = baseline_future.result()
    
    if not test_costs and not baseline_costs:
        return {}
    
    all_services = set(test_costs.keys()) | set(baseline_costs.keys())
    cost_comparison = {}
    
    test_total = sum(test_costs.values())
    baseline_total = sum(baseline_costs.values())
    
    for service in all_services:
        test_cost = test_costs.get(service, 0)
        baseline_cost = baseline_costs.get(service, 0)
        
        # Calculate percentage difference (positive = higher cost than baseline)
        if baseline_cost > 0:
            percentage_diff = ((test_cost - baseline_cost) / baseline_cost) * 100
            similarity = percentage_diff  # Positive if test costs more (bad)
        else:
            similarity = 0.0 if test_cost > 0 else 0.0
        
        cost_comparison[f"{service}_cost_similarity"] = similarity
    
    # Overall cost similarity
    if baseline_total > 0:
        percentage_diff = ((test_total - baseline_total) / baseline_total) * 100
        overall_similarity = percentage_diff
    else:
        overall_similarity = 0.0 if test_total > 0 else 0.0
    
    cost_comparison['overall_cost_similarity'] = overall_similarity
    cost_comparison['test_total_cost'] = test_total
    cost_comparison['baseline_total_cost'] = baseline_total
    
    # Add actual cost breakdown for aggregation
    cost_comparison['baseline'] = {'total_cost': baseline_total}
    cost_comparison['test'] = {'total_cost': test_total}
    
    # Group costs by context (service prefix)
    baseline_contexts = {}
    test_contexts = {}
    
    for service in all_services:
        # Extract context from service name (e.g., "Summarization_bedrock" -> "Summarization")
        parts = service.split('_')
        context = parts[0] if parts else service
        service_type = '_'.join(parts[1:]) if len(parts) > 1 else 'unknown'
        
        if context not in baseline_contexts:
            baseline_contexts[context] = {}
        if context not in test_contexts:
            test_contexts[context] = {}
            
        baseline_contexts[context][service_type] = baseline_costs.get(service, 0)
        test_contexts[context][service_type] = test_costs.get(service, 0)
    
    cost_comparison['baseline'].update(baseline_contexts)
    cost_comparison['test'].update(test_contexts)
    
    return cost_comparison

def _compare_metering_usage(test_metering, baseline_metering):
    """Compare usage metrics from DynamoDB metering data"""
    usage_comparison = {}
    
    # Get all service keys from both test and baseline
    all_services = set(test_metering.keys()) | set(baseline_metering.keys())
    
    for service in all_services:
        test_metrics = test_metering.get(service, {})
        baseline_metrics = baseline_metering.get(service, {})
        
        # Compare each metric type (tokens, pages, invocations, etc.)
        all_metric_types = set(test_metrics.keys()) | set(baseline_metrics.keys())
        
        for metric_type in all_metric_types:
            test_value = test_metrics.get(metric_type, 0)
            baseline_value = baseline_metrics.get(metric_type, 0)
            
            # Calculate percentage difference (positive = higher usage than baseline)
            if baseline_value > 0:
                percentage_diff = ((test_value - baseline_value) / baseline_value) * 100
                similarity = percentage_diff  # Positive if test uses more (bad)
            else:
                similarity = 0.0 if test_value > 0 else 0.0
            
            key = f"{service}_{metric_type}_usage_similarity"
            usage_comparison[key] = similarity
    
    # Add actual usage breakdown for aggregation
    usage_comparison['baseline'] = baseline_metering
    usage_comparison['test'] = test_metering
    
    return usage_comparison

def _get_test_run_config(test_run_id):
    """Get test run configuration from metadata record"""
    table = dynamodb.Table(os.environ['TRACKING_TABLE'])
    response = table.get_item(
        Key={'PK': f'testrun#{test_run_id}', 'SK': 'metadata'}
    )
    
    config = response.get('Item', {}).get('Config', {})
    
    # Convert DynamoDB Decimal objects to regular Python types for JSON serialization
    def convert_decimals(obj):
        if isinstance(obj, dict):
            return {k: convert_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_decimals(v) for v in obj]
        elif hasattr(obj, '__class__') and obj.__class__.__name__ == 'Decimal':
            # Convert Decimal to float or int
            if obj % 1 == 0:
                return int(obj)
            else:
                return float(obj)
        else:
            return obj
    
    return convert_decimals(config)

def _build_metrics_comparison(results):
    """Build metrics comparison table - return complete results"""
    # Convert list to dict with testRunId as key
    results_dict = {result['testRunId']: result for result in results}
    return results_dict

def _build_config_comparison(configs):
    """Build configuration differences - compare Custom configs, fallback to Default"""
    if not configs or len(configs) != 2:
        return None
    
    config1 = configs[0]['config']
    config2 = configs[1]['config']
    test_run_id1 = configs[0]['testRunId']
    test_run_id2 = configs[1]['testRunId']
    
    custom1 = config1.get('Custom', {})
    custom2 = config2.get('Custom', {})
    default_config = config1.get('Default', {})
    
    def get_nested_value(dictionary, path):
        """Get nested value from dictionary using dot notation path"""
        keys = path.split('.')
        current = dictionary
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current
    
    def get_all_paths(dictionary, prefix=""):
        """Get all nested paths from dictionary"""
        paths = []
        for key, value in dictionary.items():
            current_path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                paths.extend(get_all_paths(value, current_path))
            else:
                paths.append(current_path)
        return paths
    
    # Get all possible configuration paths
    all_paths = set()
    all_paths.update(get_all_paths(custom1))
    all_paths.update(get_all_paths(custom2))
    all_paths.update(get_all_paths(default_config))
    
    differences = []
    for path in all_paths:
        # Get effective values (Custom overrides Default)
        value1 = get_nested_value(custom1, path)
        if value1 is None:
            value1 = get_nested_value(default_config, path)
            
        value2 = get_nested_value(custom2, path)
        if value2 is None:
            value2 = get_nested_value(default_config, path)
        
        # Only include if values are different
        if value1 != value2 and value1 is not None and value2 is not None:
            differences.append({
                'setting': path,
                'values': {
                    test_run_id1: str(value1),
                    test_run_id2: str(value2)
                }
            })
    
    return differences
