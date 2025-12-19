# OmniAI OCR Benchmark Configuration

This configuration is designed for the **OmniAI OCR Benchmark dataset** from HuggingFace (`getomni-ai/ocr-benchmark`), filtered to include only the most representative document formats with consistent schemas.

## Dataset Overview

The OCR Benchmark dataset contains diverse document types with ground truth JSON extraction data. This configuration includes the **9 document formats** with the most samples (formats with >5 samples per schema), totaling **293 pre-selected images**.

## Document Classes

| Class | Description | Key Fields |
|-------|-------------|------------|
| **BANK_CHECK** | Bank checks with MICR encoding | checks[] (bank, personal info, payee, amount, MICR) |
| **COMMERCIAL_LEASE_AGREEMENT** | Commercial property leases | lessor/lessee info, premises, lease terms, rent |
| **CREDIT_CARD_STATEMENT** | Account statements | accountNumber, period, transactions[] |
| **DELIVERY_NOTE** | Shipping/delivery documents | header (from/to), items[] with product specs |
| **EQUIPMENT_INSPECTION** | Inspection reports | equipmentInfo, checkpoints[], overallStatus |
| **GLOSSARY** | Alphabetized term lists | title, pageNumber, glossarySections[] |
| **PETITION_FORM** | Election petition forms | header, candidate, witness, signatures[] |
| **REAL_ESTATE** | Real estate transaction data | transactions[], transactionsByCity[] |
| **SHIFT_SCHEDULE** | Employee scheduling | title, facility, employees[] with shifts |

## Schema Design

Each class schema is derived from the original HuggingFace dataset JSON schemas with the following IDP-specific extensions:

### Evaluation Methods
- **EXACT**: Used for enumerated values, IDs, codes (e.g., bank names, states, account numbers)
- **NUMERIC_EXACT**: Used for numeric values (amounts, quantities, page numbers)
- **LEVENSHTEIN**: Used for text fields with threshold of 0.7 (names, addresses, descriptions)

### Confidence Thresholds
All fields use a default confidence threshold of **0.8**.

## Usage

### Deploy with Test Set
```bash
# The OCR benchmark dataset is automatically deployed during stack creation
# via the ocr_benchmark_deployer Lambda function
# 
# The deployer uses hardcoded image IDs (293 images across 9 formats)
# and downloads ground truth data from HuggingFace
```

### Load Configuration
```python
from idp_common import load_config

config = load_config("config_library/pattern-2/ocr-benchmark/config.yaml")
```

### Run Evaluation
This config is designed for use with the IDP evaluation framework:
```bash
# Run evaluation against the ocr-benchmark test set
python -m idp_cli evaluate --test-set ocr-benchmark --config config_library/pattern-2/ocr-benchmark/config.yaml
```

## Configuration Highlights

### OCR Settings
- **Backend**: Amazon Textract with LAYOUT and TABLES features
- **Max Workers**: 20 (for parallel processing)

### Classification
- **Model**: `us.amazon.nova-pro-v1:0`
- **Method**: Multimodal page-level classification

### Extraction  
- **Model**: `us.anthropic.claude-haiku-4-5-20251001-v1:0`
- **Max Tokens**: 10,000 (to handle complex nested structures)

### Evaluation
- **Enabled**: Yes
- **Model**: `us.anthropic.claude-3-haiku-20240307-v1:0`

## Related Resources

- **Dataset**: [getomni-ai/ocr-benchmark on HuggingFace](https://huggingface.co/datasets/getomni-ai/ocr-benchmark)
- **Deployer**: `src/lambda/ocr_benchmark_deployer/index.py`
- **Pattern Documentation**: `docs/pattern-2.md`

## Schema Field Reference

### Array Fields (with nested definitions)
- `BANK_CHECK.checks[]` - Check objects with MICR data
- `CREDIT_CARD_STATEMENT.transactions[]` - Financial transactions
- `DELIVERY_NOTE.items[]` - Delivered product items
- `EQUIPMENT_INSPECTION.checkpoints[]` - Inspection categories with items
- `GLOSSARY.glossarySections[]` - Letter-based sections with terms
- `PETITION_FORM.signatures[]` - Voter signatures
- `REAL_ESTATE.transactions[]` / `transactionsByCity[]` - Property transactions
- `SHIFT_SCHEDULE.employees[]` - Employee shift assignments

### Enum Values
- **BANK_CHECK.bank**: CHASE, BANK_OF_AMERICA, WELLS_FARGO, CITIBANK, US_BANK
- **COMMERCIAL_LEASE_AGREEMENT.spaceType**: Office Space, Retail Space, Warehouse, Industrial Space
- **DELIVERY_NOTE.Item.type**: LED Luminaire, Power Supply, Control System, etc.
- **DELIVERY_NOTE.Item.brand**: Philips, Osram, Schneider Electric, etc.
- **EQUIPMENT_INSPECTION.status**: functional, needsService, defective, pass, fail, na
- **SHIFT_SCHEDULE.Shift.type**: Morning, Afternoon, Night, Leave, empty
