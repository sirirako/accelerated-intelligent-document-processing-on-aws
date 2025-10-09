# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import boto3
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal

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
        return None
        
    metadata = response['Item']
    
    # Query reporting database for accuracy metrics
    accuracy_data = _query_accuracy_metrics(test_run_id)
    
    return {
        'testRunId': test_run_id,
        'testSetName': metadata.get('TestSetName'),
        'status': metadata.get('Status'),
        'filesCount': metadata.get('FilesCount', 0),
        'completedFiles': metadata.get('CompletedFiles', 0),
        'failedFiles': metadata.get('FailedFiles', 0),
        'overallAccuracy': accuracy_data.get('overall_accuracy'),
        'averageConfidence': accuracy_data.get('average_confidence'),
        'totalCost': accuracy_data.get('total_cost'),
        'costBreakdown': json.dumps(accuracy_data.get('cost_breakdown', {})),
        'createdAt': _format_datetime(metadata.get('CreatedAt')),
        'completedAt': _format_datetime(metadata.get('CompletedAt'))
    }

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
    
def _query_accuracy_metrics(test_run_id):
    """Query evaluation reports for accuracy metrics using EvaluationReportUri and bucket files"""
    import boto3
    import json
    from decimal import Decimal
    
    s3 = boto3.client('s3')
    table = dynamodb.Table(os.environ['TRACKING_TABLE'])
    
    try:
        baseline_bucket = os.environ.get('BASELINE_BUCKET')
        output_bucket = os.environ.get('OUTPUT_BUCKET')
        
        # Scan for documents for this test run
        response = table.scan(
            FilterExpression='begins_with(PK, :pk) AND SK = :sk',
            ExpressionAttributeValues={
                ':pk': f'doc#{test_run_id}/',
                ':sk': 'none'
            }
        )
        
        total_accuracy = 0
        doc_count = 0
        cost_breakdown = {
            'bedrock_tokens': {'input': 0, 'output': 0, 'total': 0},
            'bda_pages': {'standard': 0, 'custom': 0},
            'textract_pages': 0,
            'sagemaker_inference': 0,
            'lambda': {'invocations': 0, 'gb_seconds': 0},
            's3_requests': {'get': 0, 'put': 0},
            'stepfunctions_transitions': 0,
            'dynamodb': {'read_units': 0, 'write_units': 0}
        }
        
        for item in response['Items']:
            # Extract filename from document PK
            doc_key = item['PK'].replace('doc#', '')  # test_run_id/filename
            filename = doc_key.split('/', 1)[1]  # Extract filename
            
            # Get test document's EvaluationReportUri
            test_evaluation_uri = item.get('EvaluationReportUri')
            
            # Get baseline document record
            baseline_response = table.get_item(Key={'PK': f'doc#{filename}', 'SK': 'none'})
            if 'Item' not in baseline_response:
                continue
                
            baseline_doc = baseline_response['Item']
            baseline_evaluation_uri = baseline_doc.get('EvaluationReportUri')
            
            accuracy = None
            
            # Method 1: Compare evaluation reports if both exist
            if test_evaluation_uri and baseline_evaluation_uri:
                accuracy = _compare_evaluation_reports(s3, test_evaluation_uri, baseline_evaluation_uri)
            
            # Method 2: Compare files from buckets if evaluation reports not available
            if accuracy is None and baseline_bucket and output_bucket:
                accuracy = _compare_bucket_files(s3, output_bucket, baseline_bucket, test_run_id, filename)
            
            if accuracy is not None:
                total_accuracy += accuracy
                doc_count += 1
            
            # Process metering data
            metering = item.get('Metering', {})
            for service, metrics in metering.items():
                if 'bedrock' in service:
                    cost_breakdown['bedrock_tokens']['input'] += int(metrics.get('inputTokens', 0))
                    cost_breakdown['bedrock_tokens']['output'] += int(metrics.get('outputTokens', 0))
                    cost_breakdown['bedrock_tokens']['total'] += int(metrics.get('totalTokens', 0))
                elif 'bda/documents-standard' in service:
                    cost_breakdown['bda_pages']['standard'] += int(metrics.get('pages', 0))
                elif 'bda/documents-custom' in service:
                    cost_breakdown['bda_pages']['custom'] += int(metrics.get('pages', 0))
                elif 'lambda/requests' in service:
                    cost_breakdown['lambda']['invocations'] += int(metrics.get('invocations', 0))
                elif 'lambda/duration' in service:
                    cost_breakdown['lambda']['gb_seconds'] += float(metrics.get('gb_seconds', 0))
        
        if doc_count > 0:
            # Calculate total cost from breakdown
            bedrock_cost = (cost_breakdown['bedrock_tokens']['input'] * 0.00003 + 
                          cost_breakdown['bedrock_tokens']['output'] * 0.00015)
            bda_cost = (cost_breakdown['bda_pages']['standard'] * 0.05 + 
                       cost_breakdown['bda_pages']['custom'] * 0.10)
            lambda_cost = cost_breakdown['lambda']['gb_seconds'] * 0.0000166667
            
            total_calculated_cost = bedrock_cost + bda_cost + lambda_cost
            
            return {
                'overall_accuracy': round((total_accuracy / doc_count) * 100, 2),
                'average_confidence': round((total_accuracy / doc_count) * 100, 2),
                'total_cost': round(total_calculated_cost, 4),
                'cost_breakdown': cost_breakdown,
                'confidence_accuracy': []
            }
    
    except Exception as e:
        logger.error(f"Error querying accuracy metrics for {test_run_id}: {e}")
    
    return _get_empty_metrics()

def _compare_bucket_files(s3, output_bucket, baseline_bucket, test_run_id, filename):
    """Compare files from output and baseline buckets for additional evaluation"""
    try:
        # Look for evaluation files in output bucket for this test run
        test_prefix = f"{test_run_id}/{filename}/"
        test_objects = s3.list_objects_v2(Bucket=output_bucket, Prefix=test_prefix)
        
        # Look for baseline files
        baseline_prefix = f"{filename}/"
        baseline_objects = s3.list_objects_v2(Bucket=baseline_bucket, Prefix=baseline_prefix)
        
        if 'Contents' not in test_objects or 'Contents' not in baseline_objects:
            return None
        
        # Find matching evaluation files
        test_files = {obj['Key'].split('/')[-1]: obj['Key'] for obj in test_objects['Contents'] 
                     if obj['Key'].endswith('.json')}
        baseline_files = {obj['Key'].split('/')[-1]: obj['Key'] for obj in baseline_objects['Contents'] 
                         if obj['Key'].endswith('.json')}
        
        # Compare common files
        common_files = set(test_files.keys()) & set(baseline_files.keys())
        if not common_files:
            return None
        
        total_accuracy = 0
        file_count = 0
        
        for file_name in common_files:
            try:
                # Download test file
                test_obj = s3.get_object(Bucket=output_bucket, Key=test_files[file_name])
                test_data = json.loads(test_obj['Body'].read())
                
                # Download baseline file
                baseline_obj = s3.get_object(Bucket=baseline_bucket, Key=baseline_files[file_name])
                baseline_data = json.loads(baseline_obj['Body'].read())
                
                # Compare the files
                file_accuracy = _calculate_file_accuracy(baseline_data, test_data)
                if file_accuracy is not None:
                    total_accuracy += file_accuracy
                    file_count += 1
                    
            except Exception as e:
                logger.warning(f"Could not compare file {file_name}: {e}")
                continue
        
        return (total_accuracy / file_count) if file_count > 0 else None
        
    except Exception as e:
        logger.warning(f"Could not compare bucket files for {filename}: {e}")
        return None

def _calculate_file_accuracy(baseline_data, test_data):
    """Calculate accuracy between baseline and test file data"""
    if not baseline_data or not test_data:
        return None
    
    # Try different comparison strategies based on file structure
    
    # Strategy 1: Compare extraction results
    if 'extraction_results' in baseline_data and 'extraction_results' in test_data:
        return _calculate_extraction_accuracy(baseline_data['extraction_results'], test_data['extraction_results'])
    
    # Strategy 2: Compare evaluation metrics
    if 'evaluation_metrics' in baseline_data and 'evaluation_metrics' in test_data:
        return _calculate_evaluation_accuracy(baseline_data, test_data)
    
    # Strategy 3: Direct field comparison
    if isinstance(baseline_data, dict) and isinstance(test_data, dict):
        total_fields = 0
        matching_fields = 0
        
        for key in baseline_data:
            if key in test_data:
                total_fields += 1
                if baseline_data[key] == test_data[key]:
                    matching_fields += 1
        
        return (matching_fields / total_fields) if total_fields > 0 else None
    
    return None

def _compare_evaluation_reports(s3, test_report_uri, baseline_report_uri):
    """Compare evaluation reports from S3 URIs"""
    try:
        # Parse S3 URIs
        def parse_s3_uri(uri):
            if uri.startswith('s3://'):
                parts = uri[5:].split('/', 1)
                return parts[0], parts[1]
            return None, None
        
        test_bucket, test_key = parse_s3_uri(test_report_uri)
        baseline_bucket, baseline_key = parse_s3_uri(baseline_report_uri)
        
        if not all([test_bucket, test_key, baseline_bucket, baseline_key]):
            logger.warning(f"Invalid S3 URIs: {test_report_uri}, {baseline_report_uri}")
            return None
        
        # Download evaluation reports
        try:
            test_report = s3.get_object(Bucket=test_bucket, Key=test_key)
            test_content = test_report['Body'].read().decode('utf-8').strip()
            if not test_content:
                logger.warning(f"Empty test report file: {test_report_uri}")
                return None
            test_data = json.loads(test_content)
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in test report {test_report_uri}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error reading test report {test_report_uri}: {e}")
            return None
        
        try:
            baseline_report = s3.get_object(Bucket=baseline_bucket, Key=baseline_key)
            baseline_content = baseline_report['Body'].read().decode('utf-8').strip()
            if not baseline_content:
                logger.warning(f"Empty baseline report file: {baseline_report_uri}")
                return None
            baseline_data = json.loads(baseline_content)
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in baseline report {baseline_report_uri}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error reading baseline report {baseline_report_uri}: {e}")
            return None
        
        # Compare evaluation results
        return _calculate_evaluation_accuracy(baseline_data, test_data)
        
    except Exception as e:
        logger.warning(f"Could not compare evaluation reports: {e}")
        return None

def _calculate_evaluation_accuracy(baseline_data, test_data):
    """Calculate accuracy between baseline and test evaluation reports"""
    if not baseline_data or not test_data:
        return 0
    
    # Compare key metrics from evaluation reports
    baseline_metrics = baseline_data.get('evaluation_metrics', {})
    test_metrics = test_data.get('evaluation_metrics', {})
    
    if not baseline_metrics or not test_metrics:
        # Fallback to comparing extraction results if evaluation_metrics not available
        baseline_results = baseline_data.get('extraction_results', {})
        test_results = test_data.get('extraction_results', {})
        return _calculate_extraction_accuracy(baseline_results, test_results)
    
    # Simple accuracy calculation based on matching fields
    total_fields = 0
    matching_fields = 0
    
    for key in baseline_metrics:
        if key in test_metrics:
            total_fields += 1
            if baseline_metrics[key] == test_metrics[key]:
                matching_fields += 1
    
    return (matching_fields / total_fields) if total_fields > 0 else 0

def _compare_with_baseline(s3, baseline_bucket, test_run_id, filename, doc_item):
    """Compare document results and metering with baseline"""
    try:
        table = dynamodb.Table(os.environ['TRACKING_TABLE'])
        
        baseline_response = table.get_item(Key={'PK': f'doc#{filename}', 'SK': 'none'})
        
        if 'Item' not in baseline_response:
            logger.warning(f"No baseline document record found for {filename}")
            return None
            
        baseline_doc = baseline_response['Item']
        
        # Compare extraction results
        baseline_results = baseline_doc.get('ExtractionResults', {})
        actual_results = doc_item.get('ExtractionResults', {})
        
        accuracy = _calculate_extraction_accuracy(baseline_results, actual_results)
        
        # Compare metering data
        baseline_metering = baseline_doc.get('Metering', {})
        actual_metering = doc_item.get('Metering', {})
        
        metering_comparison = _compare_metering(baseline_metering, actual_metering)
        
        return {
            'accuracy': accuracy,
            'metering_comparison': metering_comparison
        }
        
    except Exception as e:
        logger.warning(f"Could not compare with baseline for {filename}: {e}")
        return None

def _calculate_extraction_accuracy(baseline_results, actual_results):
    """Calculate accuracy between baseline and actual extraction results"""
    if not baseline_results or not actual_results:
        return 0
        
    # Compare section summaries if available
    baseline_sections = baseline_results.get('section_summaries', {})
    actual_sections = actual_results.get('section_summaries', {})
    
    if baseline_sections and actual_sections:
        total_sections = len(baseline_sections)
        matching_sections = 0
        
        for section_name in baseline_sections:
            if section_name in actual_sections:
                baseline_class = section_name.split('_')[0]
                actual_class = actual_sections[section_name].get('classification', '')
                if baseline_class == actual_class:
                    matching_sections += 1
        
        return matching_sections / total_sections if total_sections > 0 else 0
    
    return 0

def _compare_metering(baseline_metering, actual_metering):
    """Compare metering data between baseline and actual"""
    comparison = {}
    
    # Get all unique service keys
    all_services = set(baseline_metering.keys()) | set(actual_metering.keys())
    
    for service in all_services:
        baseline_metrics = baseline_metering.get(service, {})
        actual_metrics = actual_metering.get(service, {})
        
        service_comparison = {}
        
        # Compare common metrics
        all_metric_keys = set(baseline_metrics.keys()) | set(actual_metrics.keys())
        
        for metric_key in all_metric_keys:
            baseline_value = baseline_metrics.get(metric_key, 0)
            actual_value = actual_metrics.get(metric_key, 0)
            
            if baseline_value > 0:
                change_percent = ((actual_value - baseline_value) / baseline_value) * 100
            else:
                change_percent = 100 if actual_value > 0 else 0
                
            service_comparison[metric_key] = {
                'baseline': baseline_value,
                'actual': actual_value,
                'change_percent': round(change_percent, 2)
            }
        
        comparison[service] = service_comparison
    
    return comparison

def _get_empty_metrics():
    """Return empty metrics structure"""
    return {
        'overall_accuracy': None,
        'average_confidence': None,
        'total_cost': None,
        'cost_breakdown': {},
        'confidence_accuracy': []
    }

def _get_file_results(file_items, test_run_id):
    """Get individual file results"""
    return [{
        'fileName': item['FileKey'],
        'status': item.get('Status', 'PROCESSING'),
        'accuracy': 85.0,  # Would query from reporting DB
        'confidence': 78.5,
        'cost': 2.15
    } for item in file_items]

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
