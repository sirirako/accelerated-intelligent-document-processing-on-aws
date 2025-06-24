# Reporting Database

Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

The GenAI IDP Accelerator includes a comprehensive reporting database that captures detailed metrics about document processing. This database is implemented as AWS Glue tables over Amazon S3 data in Parquet format, making it queryable through Amazon Athena for analytics and reporting purposes.

## Table of Contents

- [Evaluation Tables](#evaluation-tables)
  - [Document Evaluations](#document-evaluations)
  - [Section Evaluations](#section-evaluations)
  - [Attribute Evaluations](#attribute-evaluations)
- [Metering Table](#metering-table)
- [Using the Reporting Database with Athena](#using-the-reporting-database-with-athena)
  - [Sample Queries](#sample-queries)
  - [Creating Dashboards](#creating-dashboards)

## Evaluation Tables

The evaluation tables store metrics and results from comparing extracted document data against baseline (ground truth) data. These tables provide insights into the accuracy and performance of the document processing system.

### Document Evaluations

The `document_evaluations` table contains document-level evaluation metrics:

| Column | Type | Description |
|--------|------|-------------|
| document_id | string | Unique identifier for the document |
| input_key | string | S3 key of the input document |
| evaluation_date | timestamp | When the evaluation was performed |
| accuracy | double | Overall accuracy score (0-1) |
| precision | double | Precision score (0-1) |
| recall | double | Recall score (0-1) |
| f1_score | double | F1 score (0-1) |
| false_alarm_rate | double | False alarm rate (0-1) |
| false_discovery_rate | double | False discovery rate (0-1) |
| execution_time | double | Time taken to evaluate (seconds) |

This table is partitioned by year, month (YYYY-MM format), day (YYYY-MM-DD format), and document ID.

### Section Evaluations

The `section_evaluations` table contains section-level evaluation metrics:

| Column | Type | Description |
|--------|------|-------------|
| document_id | string | Unique identifier for the document |
| section_id | string | Identifier for the section |
| section_type | string | Type/class of the section |
| accuracy | double | Section accuracy score (0-1) |
| precision | double | Section precision score (0-1) |
| recall | double | Section recall score (0-1) |
| f1_score | double | Section F1 score (0-1) |
| false_alarm_rate | double | Section false alarm rate (0-1) |
| false_discovery_rate | double | Section false discovery rate (0-1) |
| evaluation_date | timestamp | When the evaluation was performed |

This table is partitioned by year, month (YYYY-MM format), day (YYYY-MM-DD format), and document ID.

### Attribute Evaluations

The `attribute_evaluations` table contains attribute-level evaluation metrics:

| Column | Type | Description |
|--------|------|-------------|
| document_id | string | Unique identifier for the document |
| section_id | string | Identifier for the section |
| section_type | string | Type/class of the section |
| attribute_name | string | Name of the attribute |
| expected | string | Expected (ground truth) value |
| actual | string | Actual extracted value |
| matched | boolean | Whether the values matched |
| score | double | Match score (0-1) |
| reason | string | Explanation for the match result |
| evaluation_method | string | Method used for comparison |
| confidence | string | Confidence score from extraction |
| confidence_threshold | string | Confidence threshold used |
| evaluation_date | timestamp | When the evaluation was performed |

This table is partitioned by year, month (YYYY-MM format), day (YYYY-MM-DD format), and document ID.

## Metering Table

The `metering` table captures detailed usage metrics for each document processing operation:

| Column | Type | Description |
|--------|------|-------------|
| document_id | string | Unique identifier for the document |
| context | string | Processing context (OCR, Classification, Extraction, etc.) |
| service_api | string | Specific API or model used (e.g., textract/analyze_document, bedrock/claude-3) |
| unit | string | Unit of measurement (pages, inputTokens, outputTokens, etc.) |
| value | double | Quantity of the unit consumed |
| number_of_pages | int | Number of pages in the document |
| timestamp | timestamp | When the operation was performed |

This table is partitioned by year, month (YYYY-MM format), day (YYYY-MM-DD format), and document ID.

The metering table is particularly valuable for:
- Cost analysis and allocation
- Usage pattern identification
- Resource optimization
- Performance benchmarking across different document types and sizes

## Using the Reporting Database with Athena

Amazon Athena provides a serverless query service to analyze data directly in Amazon S3. The reporting database tables are automatically registered in the AWS Glue Data Catalog, making them immediately available for querying in Athena.

To use the reporting database with Athena:

1. Open the [Amazon Athena console](https://console.aws.amazon.com/athena/)
2. Select the database named after your stack (e.g., `idp_reporting`)
3. Start querying the tables using standard SQL

### Sample Queries

Here are some example queries to get you started:

**Overall accuracy by document type:**
```sql
SELECT 
  section_type, 
  AVG(accuracy) as avg_accuracy, 
  COUNT(*) as document_count
FROM 
  section_evaluations
GROUP BY 
  section_type
ORDER BY 
  avg_accuracy DESC;
```

**Token usage by model:**
```sql
SELECT 
  service_api, 
  SUM(CASE WHEN unit = 'inputTokens' THEN value ELSE 0 END) as total_input_tokens,
  SUM(CASE WHEN unit = 'outputTokens' THEN value ELSE 0 END) as total_output_tokens,
  SUM(CASE WHEN unit = 'totalTokens' THEN value ELSE 0 END) as total_tokens,
  COUNT(DISTINCT document_id) as document_count
FROM 
  metering
WHERE 
  context = 'Extraction'
GROUP BY 
  service_api
ORDER BY 
  total_tokens DESC;
```

**Extraction confidence vs. accuracy:**
```sql
SELECT 
  CASE 
    WHEN CAST(confidence AS double) < 0.7 THEN 'Low (<0.7)'
    WHEN CAST(confidence AS double) < 0.9 THEN 'Medium (0.7-0.9)'
    ELSE 'High (>0.9)'
  END as confidence_band,
  AVG(CASE WHEN matched THEN 1.0 ELSE 0.0 END) as accuracy,
  COUNT(*) as attribute_count
FROM 
  attribute_evaluations
WHERE 
  confidence IS NOT NULL
GROUP BY 
  CASE 
    WHEN CAST(confidence AS double) < 0.7 THEN 'Low (<0.7)'
    WHEN CAST(confidence AS double) < 0.9 THEN 'Medium (0.7-0.9)'
    ELSE 'High (>0.9)'
  END
ORDER BY 
  confidence_band;
```

**Token usage per page by document type:**
```sql
SELECT 
  se.section_type,
  AVG(m.value / m.number_of_pages) as avg_tokens_per_page
FROM 
  metering m
JOIN 
  section_evaluations se ON m.document_id = se.document_id
WHERE 
  m.unit = 'totalTokens'
  AND m.number_of_pages > 0
GROUP BY 
  se.section_type
ORDER BY 
  avg_tokens_per_page DESC;
```

### Creating Dashboards

For more advanced visualization and dashboarding:

1. Use [Amazon QuickSight](https://aws.amazon.com/quicksight/) to connect to your Athena queries
2. Create interactive dashboards to monitor:
   - Extraction accuracy over time
   - Cost trends by document type
   - Performance metrics by model
   - Resource utilization patterns

You can also export query results to CSV or other formats for use with external business intelligence tools.
