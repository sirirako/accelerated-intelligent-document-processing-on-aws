# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal

import boto3


# Custom JSON encoder to handle Decimal objects from DynamoDB
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

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
    
    metrics_comparison = {result['testRunId']: result for result in results}
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
    table = dynamodb.Table(os.environ['TRACKING_TABLE'])  # type: ignore[attr-defined]  # type: ignore[attr-defined]
    
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
            # Refresh metadata after status update
            response = table.get_item(
                Key={'PK': f'testrun#{test_run_id}', 'SK': 'metadata'}
            )
            if 'Item' in response:
                metadata = response['Item']
            
    
    # Raise error if status is still not complete
    if current_status not in ['COMPLETE', 'PARTIAL_COMPLETE']:
        raise ValueError(f"Test run {test_run_id} is not complete. Current status: {current_status}")
    
    # Check if cached results exist
    cached_metrics = metadata.get('testRunResult')
    if cached_metrics is not None:
        logger.info(f"Retrieved cached metrics for test run: {test_run_id}")
        # Use cached metrics but get dynamic fields from current metadata
        return {
            'testRunId': test_run_id,
            'testSetName': metadata.get('TestSetName'),
            'status': current_status,
            'filesCount': metadata.get('FilesCount', 0),
            'completedFiles': metadata.get('CompletedFiles', 0),
            'failedFiles': metadata.get('FailedFiles', 0),
            'overallAccuracy': cached_metrics.get('overallAccuracy'),
            'averageConfidence': cached_metrics.get('averageConfidence'),
            'accuracyBreakdown': cached_metrics.get('accuracyBreakdown', {}),
            'totalCost': cached_metrics.get('totalCost', 0),
            'costBreakdown': cached_metrics.get('costBreakdown', {}),
            'usageBreakdown': cached_metrics.get('usageBreakdown', {}),
            'createdAt': _format_datetime(metadata.get('CreatedAt')),
            'completedAt': _format_datetime(metadata.get('CompletedAt')),
            'context': metadata.get('Context')
        }
    
    # Calculate aggregated metrics
    aggregated_metrics = _aggregate_test_run_metrics(test_run_id)
    
    result = {
        'testRunId': test_run_id,
        'testSetName': metadata.get('TestSetName'),
        'status': current_status,
        'filesCount': metadata.get('FilesCount', 0),
        'completedFiles': metadata.get('CompletedFiles', 0),
        'failedFiles': metadata.get('FailedFiles', 0),
        'overallAccuracy': aggregated_metrics.get('overall_accuracy'),
        'averageConfidence': aggregated_metrics.get('average_confidence'),
        'accuracyBreakdown': aggregated_metrics.get('accuracy_breakdown', {}),
        'totalCost': aggregated_metrics.get('total_cost', 0),
        'costBreakdown': aggregated_metrics.get('cost_breakdown', {}),
        'usageBreakdown': aggregated_metrics.get('usage_breakdown', {}),
        'createdAt': _format_datetime(metadata.get('CreatedAt')),
        'completedAt': _format_datetime(metadata.get('CompletedAt')),
        'context': metadata.get('Context')
    }

    # Cache only the static metrics (not status/counts)
    try:
        logger.info(f"Caching metrics for test run: {test_run_id}")
        
        def float_to_decimal(obj):
            if isinstance(obj, float):
                return Decimal(str(obj))
            elif isinstance(obj, dict):
                return {k: float_to_decimal(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [float_to_decimal(v) for v in obj]
            return obj
        
        # Cache only static metrics
        metrics_to_cache = {
            'overallAccuracy': aggregated_metrics.get('overall_accuracy'),
            'averageConfidence': aggregated_metrics.get('average_confidence'),
            'accuracyBreakdown': aggregated_metrics.get('accuracy_breakdown', {}),
            'totalCost': aggregated_metrics.get('total_cost', 0),
            'costBreakdown': aggregated_metrics.get('cost_breakdown', {}),
            'usageBreakdown': aggregated_metrics.get('usage_breakdown', {})
        }
        
        table.update_item(
            Key={'PK': f'testrun#{test_run_id}', 'SK': 'metadata'},
            UpdateExpression='SET testRunResult = :testRunResult',
            ExpressionAttributeValues={':testRunResult': float_to_decimal(metrics_to_cache)}
        )
        logger.info(f"Successfully cached metrics for test run: {test_run_id}")
    except Exception as e:
        logger.warning(f"Failed to cache results for {test_run_id}: {e}")
    
    return result

def get_test_runs(time_period_hours=2):
    """Get list of test runs within specified time period"""
    table = dynamodb.Table(os.environ['TRACKING_TABLE'])  # type: ignore[attr-defined]  # type: ignore[attr-defined]
    
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
        'completedAt': _format_datetime(item.get('CompletedAt')),
        'context': item.get('Context')
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
    table = dynamodb.Table(os.environ['TRACKING_TABLE'])  # type: ignore[attr-defined]
    
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
                doc_status = doc_response['Item'].get('ObjectStatus', 'QUEUED')
                eval_status = doc_response['Item'].get('EvaluationStatus')
                logger.info(f"File {file_key}: ObjectStatus={doc_status}, EvaluationStatus={eval_status}")
                
                if doc_status == 'COMPLETED':
                    # Check if evaluation is also complete
                    if eval_status == 'COMPLETED':
                        completed_files += 1
                        logger.info(f"File {file_key}: counted as completed")
                    elif eval_status == 'RUNNING':
                        evaluating_files += 1
                        logger.info(f"File {file_key}: counted as evaluating")
                    elif eval_status is None:
                        # Document completed but evaluation not started yet
                        evaluating_files += 1
                        logger.info(f"File {file_key}: counted as evaluating (eval not started)")
                    elif eval_status == 'FAILED':
                        # Evaluation failed - count as failed
                        failed_files += 1
                        logger.info(f"File {file_key}: counted as failed (eval failed)")
                    elif eval_status == 'NO_BASELINE':
                        # No baseline data available - count as completed
                        completed_files += 1
                        logger.info(f"File {file_key}: counted as completed (no baseline data)")
                    else:
                        # Unknown evaluation status - count as evaluating
                        evaluating_files += 1
                        logger.info(f"File {file_key}: counted as evaluating (unknown eval status: {eval_status})")
                elif doc_status == 'FAILED':
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

def _aggregate_test_run_metrics(test_run_id):
    """Aggregate metrics from evaluation reports for all documents in test run"""
    table = dynamodb.Table(os.environ['TRACKING_TABLE'])  # type: ignore[attr-defined]
    
    # Get all documents for this test run
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
    
    if not items:
        return {}
    
    # Aggregate metrics from evaluation reports
    total_accuracy = 0
    total_confidence = 0
    total_cost = 0
    accuracy_count = 0
    confidence_count = 0
    cost_breakdown = {}
    usage_breakdown = {}
    
    # Accuracy metrics aggregation
    total_precision = 0
    total_recall = 0
    total_f1_score = 0
    total_false_alarm_rate = 0
    total_false_discovery_rate = 0
    precision_count = 0
    recall_count = 0
    f1_count = 0
    far_count = 0
    fdr_count = 0
    
    s3 = boto3.client('s3')
    
    for item in items:
        evaluation_uri = item.get('EvaluationReportUri')
        if not evaluation_uri:
            continue
            
        try:
            # Get evaluation report data
            json_uri = evaluation_uri.replace('report.md', 'results.json')
            bucket, key = _parse_s3_uri(json_uri)
            if bucket and key:
                obj = s3.get_object(Bucket=bucket, Key=key)
                data = json.loads(obj['Body'].read())
                
                # Extract accuracy from overall_metrics
                overall_metrics = data.get('overall_metrics', {})
                if overall_metrics.get('accuracy'):
                    total_accuracy += overall_metrics['accuracy']
                    accuracy_count += 1
                
                # Extract additional accuracy metrics
                if overall_metrics.get('precision'):
                    total_precision += overall_metrics['precision']
                    precision_count += 1
                if overall_metrics.get('recall'):
                    total_recall += overall_metrics['recall']
                    recall_count += 1
                if overall_metrics.get('f1_score'):
                    total_f1_score += overall_metrics['f1_score']
                    f1_count += 1
                if overall_metrics.get('false_alarm_rate'):
                    total_false_alarm_rate += overall_metrics['false_alarm_rate']
                    far_count += 1
                if overall_metrics.get('false_discovery_rate'):
                    total_false_discovery_rate += overall_metrics['false_discovery_rate']
                    fdr_count += 1
                
                # Extract confidence from section results
                confidences = []
                for section in data.get('section_results', []):
                    for attr in section.get('attributes', []):
                        if attr.get('confidence') is not None:
                            confidences.append(float(attr['confidence']))
                
                if confidences:
                    avg_confidence = sum(confidences) / len(confidences)
                    total_confidence += avg_confidence
                    confidence_count += 1
                
        except Exception as e:
            logger.warning(f"Failed to process evaluation report for {item['PK']}: {e}")
            continue
        
        # Get cost and usage from document metering
        metering = item.get('Metering', {})
        if metering:
            # Aggregate usage metrics
            for service, metrics in metering.items():
                if service not in usage_breakdown:
                    usage_breakdown[service] = {}
                for metric, value in metrics.items():
                    usage_breakdown[service][metric] = usage_breakdown[service].get(metric, 0) + value
        
        # Get cost from completion date if available
        if item.get('CompletionTime'):
            completion_date = datetime.fromisoformat(item['CompletionTime']).strftime('%Y-%m-%d')
            doc_key = item['PK'].replace('doc#', '')
            doc_costs = _get_document_costs_from_reporting_db(doc_key, completion_date)
            
            for service, cost in doc_costs.items():
                total_cost += cost
                # Group by service context with nested structure
                context = service.split('_')[0] if '_' in service else service
                service_api = service.split('_')[1] if '_' in service and len(service.split('_')) > 1 else 'total'
                
                if context not in cost_breakdown:
                    cost_breakdown[context] = {}
                if service_api not in cost_breakdown[context]:
                    cost_breakdown[context][service_api] = 0
                cost_breakdown[context][service_api] += cost
    
    return {
        'overall_accuracy': total_accuracy / accuracy_count if accuracy_count > 0 else None,
        'average_confidence': total_confidence / confidence_count if confidence_count > 0 else None,
        'accuracy_breakdown': {
            'precision': total_precision / precision_count if precision_count > 0 else None,
            'recall': total_recall / recall_count if recall_count > 0 else None,
            'f1_score': total_f1_score / f1_count if f1_count > 0 else None,
            'false_alarm_rate': total_false_alarm_rate / far_count if far_count > 0 else None,
            'false_discovery_rate': total_false_discovery_rate / fdr_count if fdr_count > 0 else None
        },
        'total_cost': total_cost,
        'cost_breakdown': cost_breakdown,
        'usage_breakdown': usage_breakdown
    }



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
                    mask = pc.equal(table_data['document_id'], document_id)  # type: ignore[attr-defined]
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
    table = dynamodb.Table(os.environ['TRACKING_TABLE'])  # type: ignore[attr-defined]
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
