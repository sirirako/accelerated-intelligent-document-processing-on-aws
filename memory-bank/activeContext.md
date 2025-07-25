# GenAI IDP Accelerator - Active Context

## Current Task Focus

**User Question**: Understanding OCR processing architecture for large PDFs (500+ pages) in the IDP accelerator, specifically:
1. Is OCR processing sequential or distributed by page?
2. How does Bedrock-only OCR deployment differ?
3. What parts of the system run sequentially vs distributed?
4. Handling massive PDFs with hundreds of forms without clear page boundaries

## Key Findings

### OCR Processing Models

The IDP accelerator uses **different processing models depending on the pattern**:

#### Pattern 1 (BDA): Sequential Internal Processing
- **OCR Approach**: Bedrock Data Automation handles everything internally
- **Processing**: Entire document processed as single unit by BDA service
- **Concurrency**: Not user-controllable, managed by BDA
- **Large Documents**: Subject to BDA service limits and timeouts

#### Pattern 2/3 (Textract + Bedrock): Distributed Page Processing
- **OCR Approach**: AWS Textract with concurrent page processing
- **Processing**: **Pages processed in parallel** using ThreadPoolExecutor
- **Concurrency**: Configurable (default: 20 concurrent workers)
- **Large Documents**: Optimal for 500+ page documents

### Sequential vs Distributed Components

#### Sequential Processing:
1. **Step Functions Workflow**: OCR → Classification → Extraction → Assessment → Summarization
2. **Classification**: Analyzes all pages to create document boundaries
3. **BDA Internal Processing**: Everything handled as single unit

#### Distributed Processing:
1. **OCR Pages (Pattern 2/3)**: Up to 20 pages processed simultaneously
2. **Extraction Sections**: Up to 10 document sections processed in parallel
3. **Independent API Calls**: Each page makes separate Textract calls

## Customer Scenario Analysis

### 500+ Page PDF with Multiple Forms

**Challenge**: Single PDF containing hundreds of forms without clear page boundaries

**Recommended Approach**: Pattern 2 or 3 for optimal performance

**Why Pattern 2/3 is Better**:
- **Page-Level Parallelism**: 500 pages processed 20 at a time
- **Memory Efficiency**: Individual pages loaded, not entire document
- **Fault Tolerance**: Page failures don't stop entire processing
- **Granular Control**: Can optimize per-page processing

**Classification Strategy**:
- Use "holistic" classification method to analyze entire document
- Creates logical sections grouping related pages
- Handles form boundaries that don't align with page boundaries

## Technical Implementation Details

### OCR Service Configuration for Large Documents

```yaml
ocr:
  backend: "textract"
  max_workers: 20  # Increase for more parallelism
  image:
    dpi: 150      # Balance quality vs processing time
    target_width: 1024
    target_height: 1024
  features:
    - name: "LAYOUT"
    - name: "TABLES" 
    - name: "FORMS"
```

### Processing Flow for Large PDFs

1. **Document Load**: PyMuPDF loads PDF structure
2. **Page Distribution**: ThreadPoolExecutor creates 20 concurrent workers
3. **Parallel OCR**: Each page processed independently via Textract
4. **Result Assembly**: Pages sorted and combined into document structure
5. **Classification**: Holistic analysis creates logical document sections
6. **Parallel Extraction**: Sections processed concurrently (MaxConcurrency: 10)

## Performance Implications

### For 500-Page Document:
- **Pattern 1 (BDA)**: Single job, BDA-managed processing
- **Pattern 2/3**: ~25 batches of 20 pages each, highly parallelized

### Bottlenecks to Consider:
1. **Textract Rate Limits**: May need to adjust max_workers
2. **Memory Usage**: 20 concurrent pages require significant memory
3. **S3 Operations**: Parallel uploads/downloads for page results
4. **Lambda Timeouts**: Ensure sufficient timeout for large documents

## Next Steps and Considerations

### For Customer Implementation:
1. **Choose Pattern 2 or 3** for large document processing
2. **Configure max_workers** based on Textract limits and memory
3. **Use holistic classification** to handle form boundaries
4. **Monitor memory usage** during processing
5. **Consider document splitting** if single PDF approach is problematic

### Optimization Opportunities:
- **Adaptive Concurrency**: Adjust workers based on document size
- **Progressive Processing**: Start classification while OCR continues
- **Caching Strategy**: Cache page images for reprocessing
- **Error Recovery**: Implement page-level retry with exponential backoff
