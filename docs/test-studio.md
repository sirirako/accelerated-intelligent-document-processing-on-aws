# Test Studio

The Test Studio provides a comprehensive interface for managing test sets, running tests, and analyzing results directly from the web UI.

## Overview

The Test Studio consists of two main tabs:
1. **Test Sets**: Create and manage reusable collections of test documents
2. **Test Executions**: Execute tests, view results, and compare test runs

https://github.com/user-attachments/assets/7c5adf30-8d5c-4292-93b0-0149506322c7


## Pre-Deployed Test Sets

The accelerator automatically deploys **two benchmark datasets** from HuggingFace as ready-to-use test sets during stack deployment:

1. **RealKIE-FCC-Verified**: 75 FCC invoice documents
2. **OmniAI-OCR-Benchmark**: 293 diverse document images across 9 formats

Both datasets are deployed automatically with zero manual steps required.

---

### RealKIE-FCC-Verified

**Source**: https://huggingface.co/datasets/amazon-agi/RealKIE-FCC-Verified

This dataset contains 75 invoice documents sourced from the Federal Communications Commission (FCC).

https://github.com/user-attachments/assets/d952fd37-1bd0-437f-8f67-5a634e9422e0

#### Deployment Details

During stack deployment, the system automatically:

1. **Downloads Dataset Metadata** from HuggingFace parquet file (75 documents)
2. **Downloads PDFs** directly from HuggingFace's `pdfs/` directory
3. **Uploads PDFs** to `s3://TestSetBucket/realkie-fcc-verified/input/`
4. **Extracts Ground Truth** from `json_response` field (already in accelerator format!)
5. **Uploads Baselines** to `s3://TestSetBucket/realkie-fcc-verified/baseline/`
6. **Registers Test Set** in DynamoDB with metadata

#### Key Features

### Key Features

- **Fully Automatic**: Complete deployment during stack creation with zero user effort
- **Direct PDF Downloads**: PDFs are downloaded directly from HuggingFace's repository (no image conversion needed)
- **Complete Ground Truth**: Structured invoice attributes (Agency, Advertiser, GrossTotal, PaymentTerms, AgencyCommission, NetAmountDue, LineItems)
- **Benchmark Ready**: 75 FCC invoice documents ideal for extraction evaluation

#### Corresponding Config

Use with: `config_library/pattern-2/realkie-fcc-verified/config.yaml`

---

### OmniAI-OCR-Benchmark

**Source**: https://huggingface.co/datasets/getomni-ai/ocr-benchmark

This dataset contains 293 pre-selected document images across 9 diverse document formats, filtered from the OmniAI OCR benchmark dataset.

#### Document Classes

| Class | Count | Description |
|-------|-------|-------------|
| BANK_CHECK | 52 | Bank checks with MICR encoding |
| COMMERCIAL_LEASE_AGREEMENT | 52 | Commercial property leases |
| CREDIT_CARD_STATEMENT | 11 | Account statements with transactions |
| DELIVERY_NOTE | 8 | Shipping/delivery documents |
| EQUIPMENT_INSPECTION | 11 | Inspection reports with checkpoints |
| GLOSSARY | 31 | Alphabetized term lists |
| PETITION_FORM | 51 | Election petition forms |
| REAL_ESTATE | 59 | Real estate transaction data |
| SHIFT_SCHEDULE | 18 | Employee scheduling documents |

#### Deployment Details

During stack deployment, the system automatically:

1. **Downloads Metadata** from HuggingFace (metadata.jsonl)
2. **Downloads Images** for 293 pre-selected image IDs
3. **Converts to PNG** and uploads to `s3://TestSetBucket/ocr-benchmark/input/`
4. **Extracts Ground Truth** from `true_json_output` field
5. **Uploads Baselines** to `s3://TestSetBucket/ocr-benchmark/baseline/`
6. **Registers Test Set** in DynamoDB with format distribution metadata

#### Key Features

- **Multi-Format**: 9 different document types for comprehensive testing
- **Nested Schemas**: Complex JSON schemas with nested objects and arrays
- **Pre-Selected**: 293 images filtered for formats with >5 samples per schema
- **Deterministic**: Same images deployed every time for reproducible benchmarks

#### Corresponding Config

Use with: `config_library/pattern-2/ocr-benchmark/config.yaml`

---

### Common Features

Both datasets share these deployment characteristics:

- **Fully Automatic**: Complete deployment during stack creation with zero user effort
- **Version Control**: Dataset version pinned in CloudFormation, updateable via parameter
- **Smart Updates**: Skips re-download on stack updates unless version changes
- **Single Public Source**: Everything from HuggingFace - fully reproducible anywhere

### Deployment Time

<<<<<<< HEAD
- **First Deployment**: Adds ~10-15 minutes to stack deployment (downloads both datasets)
- **Stack Updates**: Near-instant (skips if versions unchanged)
=======
- **First Deployment**: Adds ~5-10 minutes to stack deployment (downloads PDFs and metadata)
- **Stack Updates**: Near-instant (skips if version unchanged)
>>>>>>> develop
- **Version Updates**: Re-downloads and re-processes when DatasetVersion changes

### Usage

Both test sets are immediately available after stack deployment:

1. Navigate to **Test Executions** tab
2. Select the test set from the **Select Test Set** dropdown:
   - "RealKIE-FCC-Verified" for invoice extraction testing
   - "OmniAI-OCR-Benchmark" for multi-format document testing
3. Enter a description in the **Context** field
4. Click **Run Test** to start processing
5. Monitor progress and view results when complete

**RealKIE-FCC-Verified** is ideal for:
- Evaluating extraction accuracy on invoice documents
- Comparing different model configurations
- Testing prompt engineering improvements

**OmniAI-OCR-Benchmark** is ideal for:
- Testing classification across diverse document types
- Evaluating extraction on complex nested schemas
- Benchmarking multi-format document processing pipelines

## Architecture

### Backend Components

#### TestSetResolver Lambda
- **Location**: `src/lambda/test_set_resolver/index.py`
- **Purpose**: Handles GraphQL operations for test set management
- **Features**: Creates test sets, scans TestSetBucket for direct uploads, validates file matching, manages test set status

#### TestSetZipExtractor Lambda
- **Location**: `src/lambda/test_set_zip_extractor/index.py`
- **Purpose**: Extracts and validates uploaded zip files
- **Features**: S3 event triggered extraction, file validation, status updates

#### TestRunner Lambda
- **Location**: `src/lambda/test_runner/index.py`
- **Purpose**: Initiates test runs and queues file processing jobs
- **Features**: Test validation, SQS message queuing, fast response optimization

#### TestFileCopier Lambda
- **Location**: `src/lambda/test_file_copier/index.py`
- **Purpose**: Handles asynchronous file copying and processing initiation
- **Features**: SQS message processing, file copying, status management

#### TestResultsResolver Lambda
- **Location**: `src/lambda/test_results_resolver/index.py`
- **Purpose**: Handles GraphQL queries for test results and comparisons, plus asynchronous cache updates
- **Features**: 
  - Result retrieval with cached metrics
  - Comparison logic and metrics aggregation
  - Dual event handling (GraphQL + SQS)
  - Asynchronous cache update processing
  - Progress-aware status updates

#### TestResultCacheUpdateQueue
- **Type**: AWS SQS Queue
- **Purpose**: Decouples heavy metric calculations from synchronous API calls
- **Features**: 
  - Encrypted message storage
  - 15-minute visibility timeout for long-running calculations
  - Automatic retry handling

### GraphQL Schema
- **Location**: `src/api/schema.graphql`
- **Operations**: `getTestSets`, `addTestSet`, `addTestSetFromUpload`, `deleteTestSets`, `getTestRuns`, `startTestRun`, `compareTestRuns`

### Frontend Components

#### TestStudioLayout
- **Location**: `src/ui/src/components/test-studio/TestStudioLayout.jsx`
- **Purpose**: Main container with two-tab navigation and global state management

#### TestSets
- **Location**: `src/ui/src/components/test-studio/TestSets.jsx`
- **Purpose**: Manage test set collections
- **Features**: Pattern-based creation, zip upload, direct upload detection, dual polling (3s active, 30s discovery)

#### TestExecutions
- **Location**: `src/ui/src/components/test-studio/TestExecutions.jsx`
- **Purpose**: Unified interface combining TestRunner and TestResultsList
- **Features**: Test execution, results viewing, comparison, export, delete operations

## Component Structure

```
components/
└── test-studio/
    ├── TestStudioLayout.jsx
    ├── TestSets.jsx
    ├── TestExecutions.jsx
    ├── TestRunner.jsx
    ├── TestResultsList.jsx
    ├── TestResults.jsx
    ├── TestComparison.jsx
    ├── TestRunnerStatus.jsx
    ├── DeleteTestModal.jsx
    └── index.js
```

## Test Sets

### Creating Test Sets
1. **Pattern-based**: Define file patterns (e.g., `*.pdf`) with bucket type selection
   - **Input Bucket**: Scan main processing bucket for matching files
   - **Test Set Bucket**: Scan dedicated test set bucket for matching files
2. **Zip Upload**: Upload zip containing `input/` and `baseline/` folders
3. **Direct Upload**: Files uploaded directly to TestSetBucket are auto-detected

### File Structure Requirements
```
my-test-set/
├── input/
│   ├── document1.pdf
│   └── document2.pdf
└── baseline/
    ├── document1.pdf/
    │   └── [ground truth files]
    └── document2.pdf/
        └── [ground truth files]
```

### Validation Rules
- Each input file must have corresponding baseline folder
- Baseline folder name must match input filename exactly
- Status: COMPLETED (valid), FAILED (validation errors), PROCESSING (uploading)

### Upload Methods
1. **UI Zip Upload**: S3 event → Lambda extraction → Validation → Status update
2. **Direct S3 Upload**: Detected via refresh button or automatic polling

## Test Executions

### Running Tests
1. Select test set from dropdown
2. Click "Run Test" (single test execution only)
3. Monitor progress via TestRunnerStatus
4. View results in integrated listing

### Test States
- **QUEUED**: File copying jobs queued in SQS
- **RUNNING**: Files being copied and processed
- **COMPLETED**: Test finished successfully
- **FAILED**: Errors during processing

### Results Management
- Filter and paginate test runs
- Multi-select for comparison
- Navigate to detailed results view
- Delete and export functionality

## Key Features

### Test Set Management
- Reusable collections with file patterns across multiple buckets
- Dual bucket support (Input Bucket and Test Set Bucket)
- Zip upload with automatic extraction
- Direct upload detection via dual polling
- File structure validation with error reporting

### Test Execution
- Single test concurrency prevention
- Real-time status monitoring
- Global state persistence across navigation
- SQS-based asynchronous processing

### Results Analysis
- Comprehensive metrics display including:
  - **Overall accuracy and confidence metrics**
  - **Accuracy breakdown** (precision, recall, F1-score, false alarm rate, false discovery rate)
  - **Average Document Split Classification Metrics**:
    - Page Level Accuracy (average across documents)
    - Split Accuracy Without Order (average across documents)
    - Split Accuracy With Order (average across documents)  
    - Total Pages, Total Splits (sums across documents)
    - Correctly Classified Pages, Correctly Split counts (sums across documents)
  - **Cost breakdown** by service and context
- Side-by-side test comparison with all metrics
- Export capabilities (JSON/CSV downloads include all metrics)
- Integrated delete operations
