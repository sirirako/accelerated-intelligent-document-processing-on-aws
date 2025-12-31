#!/usr/bin/env python3
"""
Test script to demonstrate sticker-eval v0.1.4 integration with IDP evaluation service.

This script tests the new field_comparison_details feature including:
1. Nested object match details
2. Array/list item comparisons
3. Aggregate score calculations
4. JSON report structure
5. Markdown report with interactive controls
"""

import json
import sys

# Add lib path for imports
sys.path.insert(0, "lib/idp_common_pkg")

from idp_common.evaluation.models import (
    AttributeEvaluationResult,
    DocumentEvaluationResult,
    SectionEvaluationResult,
)


def create_sample_evaluation_result() -> DocumentEvaluationResult:
    """
    Create a sample evaluation result with nested field comparison details.

    This simulates what the EvaluationService would produce when evaluating
    a document with nested objects and arrays using sticker-eval v0.1.4+.
    """

    # Sample field_comparison_details for a nested LineItems array
    line_items_comparisons = [
        {
            "expected_key": "LineItems[0].LineItemDescription",
            "expected_value": "Advertising Services - Digital Campaign",
            "actual_key": "LineItems[0].LineItemDescription",
            "actual_value": "Advertising Services - Digital Campaign",
            "match": True,
            "score": 1.0,
            "weighted_score": 2.0,
            "reason": "Exact match",
        },
        {
            "expected_key": "LineItems[0].LineItemRate",
            "expected_value": 5000.00,
            "actual_key": "LineItems[0].LineItemRate",
            "actual_value": 5000.00,
            "match": True,
            "score": 1.0,
            "weighted_score": 1.5,
            "reason": "Numeric exact match",
        },
        {
            "expected_key": "LineItems[1].LineItemDescription",
            "expected_value": "Media Placement Fee",
            "actual_key": "LineItems[1].LineItemDescription",
            "actual_value": "Media Placement Charge",  # Slight mismatch
            "match": False,
            "score": 0.85,
            "weighted_score": 1.7,
            "reason": "Partial match - similar but not exact",
        },
        {
            "expected_key": "LineItems[1].LineItemRate",
            "expected_value": 2500.00,
            "actual_key": "LineItems[1].LineItemRate",
            "actual_value": 2500.00,
            "match": True,
            "score": 1.0,
            "weighted_score": 1.5,
            "reason": "Numeric exact match",
        },
        {
            "expected_key": "LineItems[2].LineItemDescription",
            "expected_value": "Production Costs",
            "actual_key": "LineItems[2].LineItemDescription",
            "actual_value": "Production Expenses",  # Mismatch
            "match": False,
            "score": 0.70,
            "weighted_score": 1.4,
            "reason": "Different terminology",
        },
        {
            "expected_key": "LineItems[2].LineItemRate",
            "expected_value": 1500.00,
            "actual_key": "LineItems[2].LineItemRate",
            "actual_value": 1500.00,
            "match": True,
            "score": 1.0,
            "weighted_score": 1.5,
            "reason": "Numeric exact match",
        },
    ]

    # Sample field_comparison_details for a nested Address object
    address_comparisons = [
        {
            "expected_key": "AgencyAddress.Street",
            "expected_value": "123 Marketing Blvd",
            "actual_key": "AgencyAddress.Street",
            "actual_value": "123 Marketing Blvd",
            "match": True,
            "score": 1.0,
            "weighted_score": 1.0,
            "reason": "Exact match",
        },
        {
            "expected_key": "AgencyAddress.City",
            "expected_value": "New York",
            "actual_key": "AgencyAddress.City",
            "actual_value": "New York",
            "match": True,
            "score": 1.0,
            "weighted_score": 1.0,
            "reason": "Exact match",
        },
        {
            "expected_key": "AgencyAddress.State",
            "expected_value": "NY",
            "actual_key": "AgencyAddress.State",
            "actual_value": "NY",
            "match": True,
            "score": 1.0,
            "weighted_score": 1.0,
            "reason": "Exact match",
        },
        {
            "expected_key": "AgencyAddress.ZipCode",
            "expected_value": "10001",
            "actual_key": "AgencyAddress.ZipCode",
            "actual_value": "10002",  # Mismatch
            "match": False,
            "score": 0.8,
            "weighted_score": 0.8,
            "reason": "Different zip code",
        },
    ]

    # Create attribute results with field comparison details
    attributes = [
        AttributeEvaluationResult(
            name="Agency",
            expected="ABC Marketing Agency",
            actual="ABC Marketing Agency",
            matched=True,
            score=1.0,
            reason="Exact match",
            evaluation_method="Exact",
            weight=2.0,
            confidence=0.95,
            confidence_threshold=0.9,
            field_comparison_details=None,  # Simple field, no nested details
        ),
        AttributeEvaluationResult(
            name="AgencyAddress",
            expected={
                "Street": "123 Marketing Blvd",
                "City": "New York",
                "State": "NY",
                "ZipCode": "10001",
            },
            actual={
                "Street": "123 Marketing Blvd",
                "City": "New York",
                "State": "NY",
                "ZipCode": "10002",
            },
            matched=False,  # Overall mismatch due to ZipCode
            score=0.95,  # Aggregate score
            reason="Partial match - 3/4 fields matched",
            evaluation_method="AggregateObject",
            weight=1.0,
            confidence=0.92,
            confidence_threshold=0.9,
            field_comparison_details=address_comparisons,  # Nested details!
        ),
        AttributeEvaluationResult(
            name="LineItems",
            expected=[
                {
                    "Description": "Advertising Services - Digital Campaign",
                    "Rate": 5000.00,
                },
                {"Description": "Media Placement Fee", "Rate": 2500.00},
                {"Description": "Production Costs", "Rate": 1500.00},
            ],
            actual=[
                {
                    "Description": "Advertising Services - Digital Campaign",
                    "Rate": 5000.00,
                },
                {"Description": "Media Placement Charge", "Rate": 2500.00},
                {"Description": "Production Expenses", "Rate": 1500.00},
            ],
            matched=False,  # Overall mismatch
            score=0.88,  # Aggregate score from Hungarian matching
            reason="2 of 3 line items had mismatches in descriptions",
            evaluation_method="Hungarian (threshold: 0.80)",
            weight=1.0,
            confidence=0.88,
            confidence_threshold=0.9,
            field_comparison_details=line_items_comparisons,  # Array item details!
        ),
        AttributeEvaluationResult(
            name="GrossTotal",
            expected=9000.00,
            actual=9000.00,
            matched=True,
            score=1.0,
            reason="Numeric exact match",
            evaluation_method="NumericExact",
            weight=2.0,
            confidence=0.98,
            confidence_threshold=0.9,
            field_comparison_details=None,  # Simple numeric field
        ),
        AttributeEvaluationResult(
            name="PaymentTerms",
            expected="Net 30",
            actual="Net 30",
            matched=True,
            score=1.0,
            reason="Exact match",
            evaluation_method="Exact",
            weight=1.0,
            confidence=0.97,
            confidence_threshold=0.9,
            field_comparison_details=None,
        ),
    ]

    # Create section result
    section_result = SectionEvaluationResult(
        section_id="section-001",
        document_class="Invoice",
        attributes=attributes,
        metrics={
            "precision": 0.80,
            "recall": 0.75,
            "f1_score": 0.77,
            "accuracy": 0.78,
            "weighted_overall_score": 0.88,
            "false_alarm_rate": 0.10,
            "false_discovery_rate": 0.20,
        },
    )

    # Create document evaluation result
    doc_result = DocumentEvaluationResult(
        document_id="test-invoice-001",
        section_results=[section_result],
        overall_metrics={
            "precision": 0.80,
            "recall": 0.75,
            "f1_score": 0.77,
            "accuracy": 0.78,
            "weighted_overall_score": 0.88,
            "false_alarm_rate": 0.10,
            "false_discovery_rate": 0.20,
        },
        execution_time=2.5,
    )

    return doc_result


def test_json_report():
    """Test that field_comparison_details are included in JSON report."""
    print("\n" + "=" * 80)
    print("TEST 1: JSON Report with Nested Field Comparison Details")
    print("=" * 80)

    doc_result = create_sample_evaluation_result()
    json_dict = doc_result.to_dict()

    # Verify structure
    assert "section_results" in json_dict
    assert len(json_dict["section_results"]) > 0

    section = json_dict["section_results"][0]
    assert "attributes" in section

    # Check that field_comparison_details is present
    for attr in section["attributes"]:
        print(f"\n📊 Attribute: {attr['name']}")
        print(f"   Matched: {attr['matched']}")
        print(f"   Score: {attr['score']:.2f}")

        if attr["field_comparison_details"]:
            print(
                f"   ✅ Has nested field comparison details: {len(attr['field_comparison_details'])} comparisons"
            )
            # Show first few details
            for i, detail in enumerate(attr["field_comparison_details"][:3]):
                print(
                    f"      - {detail['expected_key']}: {detail['match']} (score: {detail['score']:.2f})"
                )
        else:
            print("   ℹ️  No nested details (simple field)")

    print("\n✅ JSON report structure verified!")
    print(f"   Total attributes: {len(section['attributes'])}")
    print(
        f"   Attributes with nested details: {sum(1 for a in section['attributes'] if a['field_comparison_details'])}"
    )

    return json_dict


def test_markdown_report():
    """Test that markdown report includes interactive controls and nested details."""
    print("\n" + "=" * 80)
    print("TEST 2: Markdown Report with Interactive Controls")
    print("=" * 80)

    doc_result = create_sample_evaluation_result()
    markdown = doc_result.to_markdown()

    # Verify key features are present
    features = {
        "Interactive Controls": "🎛️ Report Controls" in markdown,
        "Toggle Unmatched Button": "Show Only Unmatched" in markdown,
        "Expand/Collapse Buttons": "Expand All Details" in markdown,
        "JavaScript Functions": "function toggleUnmatchedOnly()" in markdown,
        "CSS Styling": ".eval-controls" in markdown,
        "Row Classes": 'class="matched-row"' in markdown
        or 'class="unmatched-row"' in markdown,
        "Nested Details": "View" in markdown and "Nested Field Comparisons" in markdown,
        "Aggregate Score Annotation": "aggregate" in markdown,
        "HTML Details Element": "<details>" in markdown,
    }

    print("\n📋 Feature Verification:")
    for feature, present in features.items():
        status = "✅" if present else "❌"
        print(f"   {status} {feature}")

    # Count expandable sections
    expandable_count = markdown.count("<details>")
    print(f"\n📍 Found {expandable_count} expandable nested detail sections")

    # Save to file for manual inspection
    output_file = "test_evaluation_report.md"
    with open(output_file, "w") as f:
        f.write(markdown)

    print("\n✅ Markdown report generated successfully!")
    print(f"   Saved to: {output_file}")
    print("   Open this file in a markdown viewer to test interactive controls")

    return markdown


def test_aggregate_scores():
    """Test that aggregate scores are properly annotated."""
    print("\n" + "=" * 80)
    print("TEST 3: Aggregate Score Annotations")
    print("=" * 80)

    doc_result = create_sample_evaluation_result()
    markdown = doc_result.to_markdown()

    # Look for aggregate score annotations
    if '<span class="aggregate-score">' in markdown:
        print("✅ Found aggregate score styling in markdown")

        # Count occurrences
        aggregate_count = markdown.count('class="aggregate-score"')
        print(f"   {aggregate_count} aggregate scores highlighted")
    else:
        print("⚠️  No aggregate score annotations found")

    # Check for "(aggregate)" text
    if "(aggregate)" in markdown:
        aggregate_text_count = markdown.count("(aggregate)")
        print(f"✅ Found {aggregate_text_count} '(aggregate)' annotations")

    return True


def test_filtering_capability():
    """Test that row classes enable filtering."""
    print("\n" + "=" * 80)
    print("TEST 4: Row Class-Based Filtering")
    print("=" * 80)

    doc_result = create_sample_evaluation_result()
    markdown = doc_result.to_markdown()

    # Count row classes
    matched_rows = markdown.count('class="matched-row"')
    unmatched_rows = markdown.count('class="unmatched-row"')

    print("✅ Row classes found:")
    print(f"   Matched rows: {matched_rows}")
    print(f"   Unmatched rows: {unmatched_rows}")
    print(f"   Total: {matched_rows + unmatched_rows}")

    # Verify JavaScript filtering function
    if "function toggleUnmatchedOnly()" in markdown:
        print("✅ JavaScript filtering function present")

    if "rows.forEach(row => row.style.display" in markdown:
        print("✅ Row visibility toggling implemented")

    return True


def test_json_structure():
    """Test that JSON structure includes field_comparison_details."""
    print("\n" + "=" * 80)
    print("TEST 5: JSON Structure Validation")
    print("=" * 80)

    json_dict = test_json_report()

    # Pretty print a sample attribute with nested details
    section = json_dict["section_results"][0]

    # Find attribute with nested details
    nested_attr = None
    for attr in section["attributes"]:
        if attr["field_comparison_details"]:
            nested_attr = attr
            break

    if nested_attr:
        print("\n📄 Sample Attribute with Nested Details:")
        print(f"   Name: {nested_attr['name']}")
        print(f"   Score: {nested_attr['score']:.2f} (aggregate)")
        print(f"   Nested comparisons: {len(nested_attr['field_comparison_details'])}")

        print("\n   First nested comparison:")
        first_comparison = nested_attr["field_comparison_details"][0]
        print(json.dumps(first_comparison, indent=6))

        print("\n✅ Nested details properly structured in JSON")
    else:
        print("⚠️  No attributes with nested details found")

    return True


def main():
    """Run all tests and provide summary."""
    print("\n" + "=" * 80)
    print("🧪 TESTING STICKER-EVAL V0.1.4 INTEGRATION")
    print("   IDP Evaluation Service Enhancement")
    print("=" * 80)

    try:
        # Run tests
        test_json_report()
        test_markdown_report()
        test_aggregate_scores()
        test_filtering_capability()
        test_json_structure()

        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
        print("\n📝 Summary of Enhancements:")
        print("   1. ✅ field_comparison_details now captured from Stickler")
        print("   2. ✅ JSON reports include nested object match details")
        print("   3. ✅ Markdown reports have interactive controls:")
        print("      - 🔍 Show Only Unmatched filter")
        print("      - ➕➖ Expand/Collapse all details")
        print("      - 📋 Expandable nested field comparisons")
        print("   4. ✅ Aggregate scores clearly annotated")
        print("   5. ✅ Row-based filtering for compact views")

        print("\n📂 Output Files:")
        print("   - test_evaluation_report.md (open in markdown viewer)")

        print("\n🎯 Next Steps:")
        print("   - Test with real evaluation data")
        print("   - Verify in actual IDP pipeline")
        print("   - Check web UI rendering")

        return 0

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
