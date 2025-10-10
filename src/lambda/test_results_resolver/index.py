# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal

import boto3


def decimal_to_float(obj):
    """Convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(v) for v in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj

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
        return {'metrics': [], 'configDifferences': [], 'costs': []}
    
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
        return {'metrics': [], 'configDifferences': [], 'costs': []}
    
    comparison_result = {
        'metrics': _build_metrics_comparison(results),
        'configDifferences': _build_config_comparison(configs),
        'costs': _build_cost_comparison(results)
    }
    
    logger.info(f"Comparison result: metrics={len(comparison_result['metrics'])}, configs={len(comparison_result['configDifferences'])}, costs={len(comparison_result['costs'])}")
    
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
    accuracy_data = _query_accuracy_metrics(test_run_id)
    # Build result with native types (keep Decimals for DynamoDB compatibility)
    result = {
        'testRunId': test_run_id,
        'testSetName': metadata.get('TestSetName'),
        'status': current_status,
        'filesCount': metadata.get('FilesCount', 0),
        'completedFiles': metadata.get('CompletedFiles', 0),
        'failedFiles': metadata.get('FailedFiles', 0),
        'overallAccuracy': accuracy_data.get('overall_accuracy'),
        'averageConfidence': accuracy_data.get('average_confidence'),
        'totalCost': accuracy_data.get('total_cost'),
        'costBreakdown': json.dumps(decimal_to_float(accuracy_data.get('cost_breakdown', {}))),
        'usageBreakdown': json.dumps(decimal_to_float(accuracy_data.get('usage_breakdown', {}))),
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
    
    response = table.scan(
        FilterExpression='begins_with(PK, :pk) AND SK = :sk AND CreatedAt >= :cutoff',
        ExpressionAttributeValues={
            ':pk': 'testrun#',
            ':sk': 'metadata',
            ':cutoff': cutoff_iso
        }
    )
    
    test_runs = [{
        'testRunId': item['TestRunId'],
        'testSetName': item.get('TestSetName'),
        'status': item.get('Status'),
        'filesCount': item.get('FilesCount', 0),
        'completedFiles': item.get('CompletedFiles', 0),
        'failedFiles': item.get('FailedFiles', 0),
        'createdAt': _format_datetime(item.get('CreatedAt')),
        'completedAt': _format_datetime(item.get('CompletedAt'))
    } for item in response['Items']]
    
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
                    UpdateExpression='SET #status = :status, CompletedAt = :completed',
                    ExpressionAttributeNames={'#status': 'Status'},
                    ExpressionAttributeValues={
                        ':status': overall_status,
                        ':completed': datetime.utcnow().isoformat() + 'Z' if overall_status in ['COMPLETE', 'PARTIAL_COMPLETE'] else item.get('CompletedAt')
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
            'progress': round(progress, 1)
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
    """Calculate accuracy from downloaded report data"""
    try:
        if not test_data or not baseline_data:
            return None
            
        test_metrics = test_data.get('overall_metrics', {})
        baseline_metrics = baseline_data.get('overall_metrics', {})
        
        if not test_metrics or not baseline_metrics:
            return None
            
        # Compare metrics
        matching_metrics = 0
        total_metrics = 0
        
        for key in baseline_metrics:
            if key in test_metrics:
                total_metrics += 1
                if abs(test_metrics[key] - baseline_metrics[key]) < 0.001:
                    matching_metrics += 1
        
        return matching_metrics / total_metrics if total_metrics > 0 else None
        
    except Exception as e:
        logger.warning(f"Error calculating accuracy from data: {e}")
        return None

def _calculate_confidence_from_data(test_data, baseline_data):
    """Calculate confidence from downloaded report data"""
    try:
        if not test_data or not baseline_data:
            return None
            
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
            return None
        
        # Calculate average confidence for each
        test_avg_confidence = sum(test_confidences) / len(test_confidences)
        baseline_avg_confidence = sum(baseline_confidences) / len(baseline_confidences)
        
        # Calculate similarity (percentage difference) - same as original
        if baseline_avg_confidence > 0:
            percentage_diff = ((test_avg_confidence - baseline_avg_confidence) / baseline_avg_confidence) * 100
            similarity = -percentage_diff  # Negative if test has lower confidence
        else:
            similarity = 0.0
        
        logger.info(f"Confidence comparison: test_avg={test_avg_confidence:.3f}, baseline_avg={baseline_avg_confidence:.3f}, similarity={similarity:.1f}%")
        return similarity
        
    except Exception as e:
        logger.warning(f"Error calculating confidence from data: {e}")
        return None

def _query_accuracy_metrics(test_run_id):
    """Query evaluation reports for accuracy metrics using EvaluationReportUri and bucket files"""
    import time
    start_time = time.time()
    logger.info(f"Starting accuracy metrics query for test run: {test_run_id}")
    
    table = dynamodb.Table(os.environ['TRACKING_TABLE'])
    
    try:
        # Scan for documents for this test run
        scan_start = time.time()
        response = table.scan(
            FilterExpression='begins_with(PK, :pk) AND SK = :sk',
            ExpressionAttributeValues={
                ':pk': f'doc#{test_run_id}/',
                ':sk': 'none'
            }
        )
        scan_time = time.time() - scan_start
        logger.info(f"DynamoDB scan completed in {scan_time:.2f}s")
        
        items = response.get('Items', [])
        if not items:
            raise ValueError(f"No documents found for test run {test_run_id}")
        
        logger.info(f"Found {len(items)} documents to process")
        
        # Process documents in parallel
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
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
                result = _calculate_accuracy_from_data(test_data, baseline_data)
                op_time = time.time() - op_start
                logger.info(f"Accuracy calculation for {filename}: {op_time:.2f}s")
                return result
            
            def get_confidence():
                op_start = time.time()
                result = _calculate_confidence_from_data(test_data, baseline_data)
                op_time = time.time() - op_start
                logger.info(f"Confidence calculation for {filename}: {op_time:.2f}s")
                return result
            
            def get_cost_comparison():
                op_start = time.time()
                # Get completion dates from already-loaded tracking records
                test_completion_date = None
                baseline_completion_date = None
                
                # Extract completion date from test document (item)
                if 'CompletionTime' in item:
                    from datetime import datetime
                    completion_time = item['CompletionTime']
                    completion_date = datetime.fromisoformat(completion_time)
                    test_completion_date = completion_date.strftime('%Y-%m-%d')
                
                # Extract completion date from baseline document (baseline_doc)
                if 'CompletionTime' in baseline_doc:
                    from datetime import datetime
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
                    accuracy = accuracy_future.result(timeout=30)
                except Exception as e:
                    logger.warning(f"Accuracy calculation failed for {filename}: {e}")
                
                try:
                    confidence = confidence_future.result(timeout=30)
                except Exception as e:
                    logger.warning(f"Confidence calculation failed for {filename}: {e}")
                
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
                'usage_comparison': usage_comparison
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
        
        if doc_count > 0:
            total_time = time.time() - start_time
            logger.info(f"Accuracy metrics query completed in {total_time:.2f}s for {doc_count} documents")
            return {
                'overall_accuracy': round((total_accuracy / doc_count) * 100, 2),
                'average_confidence': round((total_confidence / confidence_count) * 100, 2) if confidence_count > 0 else None,
                'total_cost': final_cost_metrics.get('test_total_cost'),
                'cost_breakdown': final_cost_metrics,
                'usage_breakdown': final_usage_metrics,
                'confidence_accuracy': []
            }
    
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"Error querying accuracy metrics for {test_run_id} after {total_time:.2f}s: {e}")
        raise


def _calculate_evaluation_accuracy(baseline_data, test_data):
    """Calculate accuracy between baseline and test evaluation reports"""
    logger.info("Starting evaluation accuracy calculation")
    if not baseline_data or not test_data:
        logger.warning("Missing baseline or test data")
        return 0
    
    # Compare overall metrics from evaluation reports
    baseline_metrics = baseline_data.get('overall_metrics', {})
    test_metrics = test_data.get('overall_metrics', {})
    
    logger.info(f"Baseline metrics keys: {list(baseline_metrics.keys()) if baseline_metrics else 'None'}")
    logger.info(f"Test metrics keys: {list(test_metrics.keys()) if test_metrics else 'None'}")
    
    if not baseline_metrics or not test_metrics:
        logger.warning("No overall_metrics found in reports")
        return 0
    
    # Calculate similarity based on how close metrics are
    total_similarity = 0
    metric_count = 0
    
    for key in baseline_metrics:
        if key in test_metrics:
            baseline_val = baseline_metrics[key]
            test_val = test_metrics[key]
            
            # Calculate similarity for numeric values
            if isinstance(baseline_val, (int, float)) and isinstance(test_val, (int, float)):
                if baseline_val == 0 and test_val == 0:
                    similarity = 1.0
                elif baseline_val == 0:
                    similarity = 0.0
                else:
                    # Calculate percentage similarity (1 - relative difference)
                    diff = abs(baseline_val - test_val) / baseline_val
                    similarity = max(0, 1 - diff)
                
                total_similarity += similarity
                metric_count += 1
                logger.debug(f"Metric '{key}': baseline={baseline_val}, test={test_val}, similarity={similarity:.3f}")
    
    accuracy = (total_similarity / metric_count) if metric_count > 0 else 0
    logger.info(f"Overall similarity: {total_similarity:.3f}/{metric_count} metrics, accuracy={accuracy:.3f}")
    return accuracy

def _get_document_costs_from_reporting_db(document_id, completion_date):
    """Get actual costs from S3 Parquet files using provided completion date"""
    try:
        import boto3
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
    from concurrent.futures import ThreadPoolExecutor
    
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
        
        # Calculate percentage difference (negative = higher cost than baseline)
        if baseline_cost > 0:
            percentage_diff = ((test_cost - baseline_cost) / baseline_cost) * 100
            similarity = -percentage_diff  # Negative if test costs more (bad)
        else:
            similarity = 0.0 if test_cost > 0 else 0.0
        
        cost_comparison[f"{service}_cost_similarity"] = round(similarity, 1)
    
    # Overall cost similarity
    if baseline_total > 0:
        percentage_diff = ((test_total - baseline_total) / baseline_total) * 100
        overall_similarity = -percentage_diff
    else:
        overall_similarity = 0.0 if test_total > 0 else 0.0
    
    cost_comparison['overall_cost_similarity'] = round(overall_similarity, 1)
    cost_comparison['test_total_cost'] = round(test_total, 4)
    cost_comparison['baseline_total_cost'] = round(baseline_total, 4)
    
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
            
            # Calculate percentage difference (negative = higher usage than baseline)
            if baseline_value > 0:
                percentage_diff = ((test_value - baseline_value) / baseline_value) * 100
                similarity = -percentage_diff  # Negative if test uses more (bad)
            else:
                similarity = 0.0 if test_value > 0 else 0.0
            
            key = f"{service}_{metric_type}_usage_similarity"
            usage_comparison[key] = round(similarity, 3)
    
    return usage_comparison

def _get_test_run_config(test_run_id):
    """Get test run configuration"""
    table = dynamodb.Table(os.environ['TRACKING_TABLE'])
    response = table.get_item(
        Key={'PK': f'testrun#{test_run_id}', 'SK': 'config'}
    )
    return response.get('Item', {}).get('Config', {})

def _build_metrics_comparison(results):
    """Build metrics comparison table"""
    # Convert list to dict with testRunId as key
    results_dict = {result['testRunId']: result for result in results}
    
    return [
        {'metric': 'Overall Accuracy', 'values': {k: f"{v.get('overallAccuracy', 0)}%" for k, v in results_dict.items()}},
        {'metric': 'Average Confidence', 'values': {k: f"{v.get('averageConfidence', 0)}%" for k, v in results_dict.items()}},
        {'metric': 'Total Cost', 'values': {k: f"${v.get('totalCost', 0)}" for k, v in results_dict.items()}}
    ]

def _build_config_comparison(configs):
    """Build configuration differences table"""
    # Convert list to dict with testRunId as key
    configs_dict = {config['testRunId']: config['config'] for config in configs}
    
    all_keys = set()
    for config in configs_dict.values():
        all_keys.update(config.keys())
    
    return [{'setting': key, 'values': {k: str(v.get(key, 'N/A')) for k, v in configs_dict.items()}} 
            for key in all_keys]

def _build_cost_comparison(results):
    """Build cost comparison table"""
    # Convert list to dict with testRunId as key
    results_dict = {result['testRunId']: result for result in results}
    
    return [
        {'component': 'Processing Cost', 'values': {k: v.get('totalCost', 0) for k, v in results_dict.items()}},
        {'component': 'Storage Cost', 'values': {k: 0.5 for k in results_dict.keys()}},
        {'component': 'API Calls', 'values': {k: 1.2 for k in results_dict.keys()}}
    ]
