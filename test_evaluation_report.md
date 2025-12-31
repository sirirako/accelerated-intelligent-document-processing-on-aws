<style>
.eval-controls {
    background: #f5f5f5;
    padding: 15px;
    margin: 20px 0;
    border-radius: 5px;
    border: 1px solid #ddd;
}
.eval-toggle {
    padding: 10px 20px;
    margin: 5px;
    background: #007bff;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
    font-weight: bold;
}
.eval-toggle:hover {
    background: #0056b3;
}
.eval-toggle.active {
    background: #28a745;
}
.matched-row {
    background-color: #d4edda;
}
.unmatched-row {
    background-color: #f8d7da;
}
.aggregate-score {
    font-weight: bold;
    color: #007bff;
}
details {
    margin: 5px 0;
}
details summary {
    cursor: pointer;
    padding: 5px;
    background: #e9ecef;
    border-radius: 3px;
    user-select: none;
}
details summary:hover {
    background: #dee2e6;
}
</style>

<script>
function toggleUnmatchedOnly() {
    const button = document.getElementById('toggle-unmatched');
    const rows = document.querySelectorAll('tr.matched-row');
    
    if (button.classList.contains('active')) {
        // Show all rows
        rows.forEach(row => row.style.display = '');
        button.classList.remove('active');
        button.textContent = '🔍 Show Only Unmatched';
    } else {
        // Hide matched rows
        rows.forEach(row => row.style.display = 'none');
        button.classList.add('active');
        button.textContent = '📋 Show All';
    }
}

function expandAllDetails() {
    document.querySelectorAll('details').forEach(d => d.open = true);
}

function collapseAllDetails() {
    document.querySelectorAll('details').forEach(d => d.open = false);
}
</script>

# Evaluation Report

<div class="eval-controls">
    <h3>🎛️ Report Controls</h3>
    <button id="toggle-unmatched" class="eval-toggle" onclick="toggleUnmatchedOnly()">
        🔍 Show Only Unmatched
    </button>
    <button class="eval-toggle" onclick="expandAllDetails()">
        ➕ Expand All Details
    </button>
    <button class="eval-toggle" onclick="collapseAllDetails()">
        ➖ Collapse All Details
    </button>
</div>


## Summary

**Document Extraction:**
- **Match Rate**: 🟠 3/5 attributes matched [████████████░░░░░░░░] 60%
- **Precision**: 0.80 | **Recall**: 0.75 | **F1 Score**: 🟡 0.77
- **Weighted Overall Score**: 🟡 0.8800 (Stickler's field-weighted aggregate)

## Overall Metrics

### Document Extraction Metrics
| Metric | Value | Rating |
| ------ | :----: | :----: |
| precision | 0.8000 | 🟡 Good |
| recall | 0.7500 | 🟡 Good |
| f1_score | 0.7700 | 🟡 Good |
| accuracy | 0.7800 | 🟡 Good |
| weighted_overall_score | 0.8800 | 🟡 Good |
| false_alarm_rate | 0.1000 | 🟢 Excellent |
| false_discovery_rate | 0.2000 | 🟡 Good |


## Extraction Attribute Evaluation

### Section: section-001 (Invoice)
#### Metrics
| Metric | Value | Rating |
| ------ | :----: | :----: |
| precision | 0.8000 | 🟡 Good |
| recall | 0.7500 | 🟡 Good |
| f1_score | 0.7700 | 🟡 Good |
| accuracy | 0.7800 | 🟡 Good |
| weighted_overall_score | 0.8800 | 🟡 Good |
| false_alarm_rate | 0.1000 | 🟢 Excellent |
| false_discovery_rate | 0.2000 | 🟡 Good |


#### Attributes
<table style="width: 100%; border-collapse: collapse;">
<thead><tr style="background: #f0f0f0;"><th style="padding: 8px; border: 1px solid #ddd; text-align: center;">Status</th><th style="padding: 8px; border: 1px solid #ddd;">Attribute</th><th style="padding: 8px; border: 1px solid #ddd;">Expected</th><th style="padding: 8px; border: 1px solid #ddd;">Actual</th><th style="padding: 8px; border: 1px solid #ddd; text-align: center;">Confidence</th><th style="padding: 8px; border: 1px solid #ddd; text-align: center;">Conf. Threshold</th><th style="padding: 8px; border: 1px solid #ddd; text-align: center;">Score</th><th style="padding: 8px; border: 1px solid #ddd; text-align: center;">Weight</th><th style="padding: 8px; border: 1px solid #ddd;">Method</th><th style="padding: 8px; border: 1px solid #ddd;">Reason</th></tr></thead><tbody>
<tr class="matched-row">
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">✅</td>
<td style="padding: 8px; border: 1px solid #ddd;"><strong>Agency</strong></td>
<td style="padding: 8px; border: 1px solid #ddd;">ABC Marketing Agency</td>
<td style="padding: 8px; border: 1px solid #ddd;">ABC Marketing Agency</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">0.95</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">0.90</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">1.00</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">2.00</td>
<td style="padding: 8px; border: 1px solid #ddd;">Exact</td>
<td style="padding: 8px; border: 1px solid #ddd;">Exact match</td>
</tr>
<tr class="unmatched-row">
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">❌</td>
<td style="padding: 8px; border: 1px solid #ddd;"><strong>AgencyAddress</strong></td>
<td style="padding: 8px; border: 1px solid #ddd;">{'Street': '123 Marketing Blvd', 'City': 'New York', 'State': 'NY', 'ZipCode': '10001'}</td>
<td style="padding: 8px; border: 1px solid #ddd;">{'Street': '123 Marketing Blvd', 'City': 'New York', 'State': 'NY', 'ZipCode': '10002'}</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">0.92</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">0.90</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;"><span class="aggregate-score">0.95</span> <em>(aggregate)</em></td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">1.00</td>
<td style="padding: 8px; border: 1px solid #ddd;">AggregateObject</td>
<td style="padding: 8px; border: 1px solid #ddd;">Partial match - 3/4 fields matched</td>
</tr>
<tr class="unmatched-row">
<td colspan="10" style="padding: 0; border: 1px solid #ddd;">
<details><summary style="padding: 8px;"><strong>🔍 View 4 Nested Field Comparisons</strong></summary>
<div style="padding: 10px;">
<table class="nested-comparison-table" style="width: 100%; border-collapse: collapse; font-size: 0.9em; margin: 10px 0;"><thead><tr style='background: #f0f0f0;'><th style='padding: 8px; border: 1px solid #ddd; text-align: left;'>Field Path</th><th style='padding: 8px; border: 1px solid #ddd; text-align: left;'>Expected</th><th style='padding: 8px; border: 1px solid #ddd; text-align: left;'>Actual</th><th style='padding: 8px; border: 1px solid #ddd; text-align: center;'>Match</th><th style='padding: 8px; border: 1px solid #ddd; text-align: center;'>Score</th></tr></thead><tbody><tr style='background: #d4edda;'><td style='padding: 8px; border: 1px solid #ddd;'><code>AgencyAddress.Street</code></td><td style='padding: 8px; border: 1px solid #ddd;'>123 Marketing Blvd</td><td style='padding: 8px; border: 1px solid #ddd;'>123 Marketing Blvd</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>✅</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>1.000</td></tr><tr style='background: #d4edda;'><td style='padding: 8px; border: 1px solid #ddd;'><code>AgencyAddress.City</code></td><td style='padding: 8px; border: 1px solid #ddd;'>New York</td><td style='padding: 8px; border: 1px solid #ddd;'>New York</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>✅</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>1.000</td></tr><tr style='background: #d4edda;'><td style='padding: 8px; border: 1px solid #ddd;'><code>AgencyAddress.State</code></td><td style='padding: 8px; border: 1px solid #ddd;'>NY</td><td style='padding: 8px; border: 1px solid #ddd;'>NY</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>✅</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>1.000</td></tr><tr style='background: #f8d7da;'><td style='padding: 8px; border: 1px solid #ddd;'><code>AgencyAddress.ZipCode</code></td><td style='padding: 8px; border: 1px solid #ddd;'>10001</td><td style='padding: 8px; border: 1px solid #ddd;'>10002</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>❌</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>0.800</td></tr></tbody></table>
</div></details>
</td></tr>
<tr class="unmatched-row">
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">❌</td>
<td style="padding: 8px; border: 1px solid #ddd;"><strong>LineItems</strong></td>
<td style="padding: 8px; border: 1px solid #ddd;">[{'Description': 'Advertising Services - Digital Campaign', 'Rate': 5000.0}, {'Description': 'Media ...</td>
<td style="padding: 8px; border: 1px solid #ddd;">[{'Description': 'Advertising Services - Digital Campaign', 'Rate': 5000.0}, {'Description': 'Media ...</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">0.88</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">0.90</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;"><span class="aggregate-score">0.88</span> <em>(aggregate)</em></td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">1.00</td>
<td style="padding: 8px; border: 1px solid #ddd;">Hungarian (threshold: 0.80)</td>
<td style="padding: 8px; border: 1px solid #ddd;">2 of 3 line items had mismatches in descriptions</td>
</tr>
<tr class="unmatched-row">
<td colspan="10" style="padding: 0; border: 1px solid #ddd;">
<details><summary style="padding: 8px;"><strong>🔍 View 6 Nested Field Comparisons</strong></summary>
<div style="padding: 10px;">
<table class="nested-comparison-table" style="width: 100%; border-collapse: collapse; font-size: 0.9em; margin: 10px 0;"><thead><tr style='background: #f0f0f0;'><th style='padding: 8px; border: 1px solid #ddd; text-align: left;'>Field Path</th><th style='padding: 8px; border: 1px solid #ddd; text-align: left;'>Expected</th><th style='padding: 8px; border: 1px solid #ddd; text-align: left;'>Actual</th><th style='padding: 8px; border: 1px solid #ddd; text-align: center;'>Match</th><th style='padding: 8px; border: 1px solid #ddd; text-align: center;'>Score</th></tr></thead><tbody><tr style='background: #d4edda;'><td style='padding: 8px; border: 1px solid #ddd;'><code>LineItems[0].LineItemDescription</code></td><td style='padding: 8px; border: 1px solid #ddd;'>Advertising Services - Digital Campaign</td><td style='padding: 8px; border: 1px solid #ddd;'>Advertising Services - Digital Campaign</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>✅</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>1.000</td></tr><tr style='background: #d4edda;'><td style='padding: 8px; border: 1px solid #ddd;'><code>LineItems[0].LineItemRate</code></td><td style='padding: 8px; border: 1px solid #ddd;'>5000.0</td><td style='padding: 8px; border: 1px solid #ddd;'>5000.0</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>✅</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>1.000</td></tr><tr style='background: #f8d7da;'><td style='padding: 8px; border: 1px solid #ddd;'><code>LineItems[1].LineItemDescription</code></td><td style='padding: 8px; border: 1px solid #ddd;'>Media Placement Fee</td><td style='padding: 8px; border: 1px solid #ddd;'>Media Placement Charge</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>❌</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>0.850</td></tr><tr style='background: #d4edda;'><td style='padding: 8px; border: 1px solid #ddd;'><code>LineItems[1].LineItemRate</code></td><td style='padding: 8px; border: 1px solid #ddd;'>2500.0</td><td style='padding: 8px; border: 1px solid #ddd;'>2500.0</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>✅</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>1.000</td></tr><tr style='background: #f8d7da;'><td style='padding: 8px; border: 1px solid #ddd;'><code>LineItems[2].LineItemDescription</code></td><td style='padding: 8px; border: 1px solid #ddd;'>Production Costs</td><td style='padding: 8px; border: 1px solid #ddd;'>Production Expenses</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>❌</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>0.700</td></tr><tr style='background: #d4edda;'><td style='padding: 8px; border: 1px solid #ddd;'><code>LineItems[2].LineItemRate</code></td><td style='padding: 8px; border: 1px solid #ddd;'>1500.0</td><td style='padding: 8px; border: 1px solid #ddd;'>1500.0</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>✅</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>1.000</td></tr></tbody></table>
</div></details>
</td></tr>
<tr class="matched-row">
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">✅</td>
<td style="padding: 8px; border: 1px solid #ddd;"><strong>GrossTotal</strong></td>
<td style="padding: 8px; border: 1px solid #ddd;">9000.0</td>
<td style="padding: 8px; border: 1px solid #ddd;">9000.0</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">0.98</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">0.90</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">1.00</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">2.00</td>
<td style="padding: 8px; border: 1px solid #ddd;">NumericExact</td>
<td style="padding: 8px; border: 1px solid #ddd;">Numeric exact match</td>
</tr>
<tr class="matched-row">
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">✅</td>
<td style="padding: 8px; border: 1px solid #ddd;"><strong>PaymentTerms</strong></td>
<td style="padding: 8px; border: 1px solid #ddd;">Net 30</td>
<td style="padding: 8px; border: 1px solid #ddd;">Net 30</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">0.97</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">0.90</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">1.00</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">1.00</td>
<td style="padding: 8px; border: 1px solid #ddd;">Exact</td>
<td style="padding: 8px; border: 1px solid #ddd;">Exact match</td>
</tr>
</tbody></table>

Execution time: 2.50 seconds

## Evaluation Methods Used

This evaluation uses Stickler-based comparison with the following methods:

### Field-Level Comparison Methods

1. **EXACT** - Exact string match (case-sensitive)
   - Use for: IDs, codes, exact text requiring character-for-character match

2. **NUMERIC_EXACT** - Numeric comparison with configurable tolerance
   - Tolerance specified via `x-aws-idp-evaluation-threshold`
   - Use for: Monetary amounts, percentages, numeric values

3. **FUZZY** - Fuzzy string matching using similarity metrics
   - Threshold specified via `x-aws-idp-evaluation-threshold` (0.0-1.0)
   - Use for: Names, addresses, text with minor variations

4. **LEVENSHTEIN** - Levenshtein distance-based string comparison
   - Configurable threshold for acceptable edit distance
   - Use for: Similar to FUZZY but using specific edit distance algorithm

5. **SEMANTIC** - Semantic similarity using embedding models
   - Threshold specified via `x-aws-idp-evaluation-threshold`
   - Use for: Text where meaning matters more than exact wording

6. **LLM** - Advanced semantic evaluation using **AWS Bedrock LLMs**
   - Configured via `evaluation.llm_method` section:
     - `model`: Bedrock model ID (e.g., Claude Haiku, Sonnet)
     - `task_prompt`: Custom prompt template with context placeholders
     - `system_prompt`: System instructions for the LLM
     - `temperature`, `top_k`, `top_p`, `max_tokens`: LLM generation parameters
   - Provides contextual evaluation with reasoning
   - Use for: Complex nested objects, structured data, semantic understanding

### Array-Level Matching

7. **HUNGARIAN** - Bipartite graph matching for arrays of structured objects
   - Finds optimal 1:1 mapping between expected and actual lists
   - Each matched item pair is then compared using field-level methods
   - Configured with `x-aws-idp-evaluation-method: "HUNGARIAN"` on array properties

8. **LLM for Arrays** - Semantic evaluation of entire list structures
   - Evaluates whether lists semantically match as a whole
   - Configured with `x-aws-idp-evaluation-method: "LLM"` on array properties

### Field Weighting

Fields can be assigned importance weights using `x-aws-stickler-weight` in the schema:
- **Default weight**: 1.0 (standard importance)
- **Higher weights** (e.g., 2.0, 3.0): Critical fields that matter more for overall quality
- **Lower weights** (e.g., 0.5): Less important optional fields
- **Impact**: Used in Stickler's weighted_overall_score calculation
- **Display**: Shown in the Weight column of attribute results

**Example field weights:**
- Account Number (weight: 3.0) - Critical identifier
- Phone Number (weight: 1.0) - Standard field
- Notes (weight: 0.5) - Optional supplementary info

The **Weighted Overall Score** aggregates individual field scores weighted by importance:
- **Formula**: `Σ(weight_i × score_i) / Σ(weight_i)`
- **Section-level**: Weighted score for that specific section
- **Document-level**: Average of all section weighted scores

---

**Note**: Each attribute specifies its evaluation method via `x-aws-idp-evaluation-method` in the schema.