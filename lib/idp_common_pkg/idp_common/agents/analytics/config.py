# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Configuration management for analytics agents.
"""

import logging
from typing import Any, Dict

from ..common.config import configure_logging, get_environment_config

logger = logging.getLogger(__name__)


def get_analytics_config() -> Dict[str, Any]:
    """
    Get analytics-specific configuration from environment variables.

    Returns:
        Dict containing analytics configuration values

    Raises:
        ValueError: If required environment variables are missing
    """
    # Define required environment variables for analytics
    required_keys = [
        "ATHENA_DATABASE",
        "ATHENA_OUTPUT_LOCATION",
    ]

    # Get base configuration
    config = get_environment_config(required_keys)

    # Add analytics-specific defaults
    config.setdefault(
        "max_polling_attempts", 30
    )  # 2 seconds per attempt, Athena queries can take a while
    config.setdefault("query_timeout_seconds", 300)  # 5 minutes

    # Configure logging based on the configuration
    configure_logging(
        log_level=config.get("log_level"),
        strands_log_level=config.get("strands_log_level"),
    )

    logger.info("Analytics configuration loaded successfully")
    return config


def load_db_description() -> str:
    """
    Load the database description from the assets directory.
    TODO: this is hard coded for now because the assets directory was hard to find in the lambda environment.

    Returns:
        String containing the database description
    """

    return """
# Athena Table Information

## Overview 

1. Document Evaluations Table (document_evaluations)
   * Only useful if users have run "evaluation" jobs, which are not run by default.
   * Contains document-level evaluation metrics
   * Columns include: document_id, input_key, evaluation_date, accuracy, precision, recall, f1_score, false_alarm_rate, false_discovery_rate, execution_time
   * Partitioned by date (YYYY-MM-DD format)

2. Section Evaluations Table (section_evaluations)
   * Only useful if users have run "evaluation" jobs, which are not run by default.
   * Contains section-level evaluation metrics
   * Columns include: document_id, section_id, section_type, accuracy, precision, recall, f1_score, false_alarm_rate, false_discovery_rate, evaluation_date
   * Partitioned by date (YYYY-MM-DD format)

3. Attribute Evaluations Table (attribute_evaluations)
   * Only useful if users have run "evaluation" jobs, which are not run by default.
   * Contains attribute-level evaluation metrics
   * Columns include: document_id, section_id, section_type, attribute_name, expected, actual, matched, score, reason, evaluation_method, confidence, confidence_threshold, evaluation_date
   * Partitioned by date (YYYY-MM-DD format)

4. Metering Table (metering)
   * Captures detailed usage metrics for document processing operations
   * Useful for monitoring IDP application usage (document processing throughput, costs, token usage, etc)
   * Populated every time a document is processed (even if no evaluations are run)
   * Columns include: document_id, context, service_api, unit, value, number_of_pages, timestamp
   * Partitioned by date (YYYY-MM-DD format)

### Dynamic Document Section Tables

In addition to the predefined tables, the solution also creates dynamic tables for document sections:

* Tables are automatically created by an AWS Glue Crawler based on the section classification
* Each section type gets its own table (e.g., document_sections_invoice, document_sections_receipt)
* Common columns include: section_id, document_id, section_classification, section_confidence, timestamp
* Additional columns are dynamically inferred from the JSON extraction results
* Tables are partitioned by date (YYYY-MM-DD format)
* When querying columns with a period in their name (e.g. inference_result.currentnetpay) the column name must be included in quotation marks to be compatible with Athena querying, for example `SELECT "inference_result.currentnetpay" FROM document_sections_payslip`.


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

This table is partitioned by date (YYYY-MM-DD format).

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

This table is partitioned by date (YYYY-MM-DD format).

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

This table is partitioned by date (YYYY-MM-DD format).

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

This table is partitioned by date (YYYY-MM-DD format).

The metering table is particularly valuable for:
- Cost analysis and allocation
- Usage pattern identification
- Resource optimization
- Performance benchmarking across different document types and sizes

## Document Sections Tables

The document sections tables store the actual extracted data from document sections in a structured format suitable for analytics. These tables are automatically discovered by AWS Glue Crawler and are organized by section type (classification).

### Dynamic Section Tables

Document sections are stored in dynamically created tables based on the section classification. Each section type gets its own table (e.g., `document_sections_invoice`, `document_sections_receipt`, `document_sections_bank_statement`, etc.) with the following characteristics:

**Common Metadata Columns:**
| Column | Type | Description |
|--------|------|-------------|
| section_id | string | Unique identifier for the section |
| document_id | string | Unique identifier for the document |
| section_classification | string | Type/class of the section |
| section_confidence | double | Confidence score for the section classification |
| timestamp | timestamp | When the document was processed |

**Dynamic Data Columns:**
The remaining columns are dynamically inferred from the JSON extraction results and vary by section type. Common patterns include:
- Nested JSON objects are flattened using dot notation (e.g., `customer.name`, `customer.address.street`)
- Arrays are converted to JSON strings
- Primitive values (strings, numbers, booleans) are preserved as their native types

**Partitioning:**
Each section type table is partitioned by date (YYYY-MM-DD format) for efficient querying.

Since the columns and data types in the document section tables are dynamic, you may want to run a query to learn more about them before writing any other queries. Consider e.g. executing `describe document_sections_payslip` to learn more about that table.
## Sample Athena SQL Queries

Here are some example queries to get you started:

**List tables available, including dynamic ones**
```sql
SHOW TABLES
```

**View the dynamic columns of a table named "document_sections_payslip"**
```sql
DESCRIBE document_sections_payslip
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
GROUP BY 
  service_api
ORDER BY 
  total_tokens DESC;
```

**Total net pay added across all paystub type documents**
``sql
SELECT SUM(CAST(REPLACE(REPLACE("inference_result.currentnetpay", '$', ''), ',', '') AS DECIMAL(10,2))) as total_net_pay
FROM document_sections_payslip;
```
(note the double quotation marks around the column name, because the column name has a period in it)

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


"""


def load_result_format_description() -> str:
    """
    Load the result format description from the assets directory.
    TODO: this is hard coded for now because the assets directory was hard to find in the lambda environment.


    Returns:
        String containing the result format description
    """

    return """
# Result Format Description

The output of your analysis should be formatted as a JSON object with a `responseType` field and appropriate data fields. The `responseType` field indicates the type of visualization or output.

## Response Schema
```schema.graphql
type AnalyticsResponse @aws_cognito_user_pools @aws_iam {
  responseType: String!  # "text", "table", "plotData"
  content: String        # Text response if applicable
  tableData: AWSJSON     # For table responses
  plotData: AWSJSON      # For interactive plot data
}
```

## Output Types

### 1. Text Output
For simple text responses:

```json
{
  "responseType": "text",
  "content": "Your text response here. For example: The average accuracy across all documents is 0.85."
}
```

Another example:
```json
{
  "responseType": "text",
  "content": "There were no results found from the SQL query."
}
```

### 2. Table Output
For tabular data:

```json
{
  "responseType": "table",
  "headers": [
    {
      "id": "documentId",
      "label": "Document ID",
      "sortable": true
    },
    {
      "id": "documentType",
      "label": "Document Type",
      "sortable": true
    },
    {
      "id": "confidence",
      "label": "Confidence Score",
      "sortable": true
    }
  ],
  "rows": [
    {
      "data": {
        "confidence": 0.95,
        "documentId": "doc-001",
        "documentType": "Invoice"
      },
      "id": "doc-001"
    },
    {
      "data": {
        "confidence": 0.87,
        "documentId": "doc-002",
        "documentType": "Receipt"
      },
      "id": "doc-002"
    }
  ]
}
```

### 3. Plot Output
For visualization data (follows Chart.js format):

```json
{
  "responseType": "plotData",
  "data": {
    "datasets": [
      {
        "backgroundColor": [
          "rgba(255, 99, 132, 0.2)",
          "rgba(54, 162, 235, 0.2)",
          "rgba(255, 206, 86, 0.2)",
          "rgba(75, 192, 192, 0.2)"
        ],
        "borderColor": [
          "rgba(255, 99, 132, 1)",
          "rgba(54, 162, 235, 1)",
          "rgba(255, 206, 86, 1)",
          "rgba(75, 192, 192, 1)"
        ],
        "data": [65, 59, 80, 81],
        "borderWidth": 1,
        "label": "Document Count"
      }
    ],
    "labels": [
      "Document Type A",
      "Document Type B",
      "Document Type C",
      "Document Type D"
    ]
  },
  "options": {
    "scales": {
      "y": {
        "beginAtZero": true
      }
    },
    "responsive": true,
    "title": {
      "display": true,
      "text": "Document Distribution by Type"
    },
    "maintainAspectRatio": false
  },
  "type": "bar"
}
```
"""


def load_python_plot_generation_examples() -> str:
    """
    Load sample python plot generation examples.
    TODO: this is hard coded for now because the assets directory was hard to find in the lambda environment.


    Returns:
        String containing sample python code generation examples
    """

    return """
## Python Libraries and Code Examples

When generating Python code for visualization, you can use the following libraries:
- `json`: For JSON serialization
- `pandas`: For data manipulation
- Standard Python libraries (math, datetime, etc.)

### Example Python Code for Table Generation

```python
import json
import pandas as pd

# Read query results from local "query_results.csv" file into a dataframe
df = pd.read_csv("query_results.csv")

# Create table data
table_data = {
    "responseType": "table",
    "headers": [
        {"id": col, "label": col.replace('_', ' ').title(), "sortable": True}
        for col in df.columns
    ],
    "rows": [
        {
            "id": row.get('document_id', f"row-{i}"),
            "data": row
        }
        for i, row in enumerate(df.to_dict('records'))
    ]
}

# Output as JSON
print(json.dumps(table_data))
```

### Example Python Code for Plot Generation

```python
import json
import pandas as pd
import random

# Read query results from local "query_results.csv" file into a dataframe
df = pd.read_csv("query_results.csv")

# Generate colors
def generate_colors(n):
    colors = []
    for i in range(n):
        r = random.randint(0, 255)
        g = random.randint(0, 255)
        b = random.randint(0, 255)
        colors.append(f"rgba({r}, {g}, {b}, 0.2)")
    return colors

bg_colors = generate_colors(len(df))
border_colors = [color.replace("0.2", "1") for color in bg_colors]

# Create plot data
plot_data = {
    "responseType": "plotData",
    "data": {
        "datasets": [
            {
                "backgroundColor": bg_colors,
                "borderColor": border_colors,
                "data": df['count'].tolist(),
                "borderWidth": 1,
                "label": "Document Count"
            }
        ],
        "labels": df['document_type'].tolist()
    },
    "options": {
        "scales": {
            "y": {
                "beginAtZero": True
            }
        },
        "responsive": True,
        "title": {
            "display": True,
            "text": "Document Distribution by Type"
        },
        "maintainAspectRatio": False
    },
    "type": "bar"
}

# Output as JSON
print(json.dumps(plot_data))
```
"""
