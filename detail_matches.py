#!/usr/bin/env python3
"""
Test script to demonstrate current non-match collection behavior for IDP.
"""

import json
import os
from typing import Any, Dict, List, Optional

from stickler.comparators.exact import ExactComparator
from stickler.comparators.levenshtein import LevenshteinComparator
from stickler.comparators.numeric import NumericComparator
from stickler.structured_object_evaluator.models.comparable_field import ComparableField
from stickler.structured_object_evaluator.models.structured_model import StructuredModel


class LineItem(StructuredModel):
    """Invoice line item model matching the provided schema."""

    LineItemDescription: str = ComparableField(
        comparator=LevenshteinComparator(), threshold=0.8, weight=2.0
    )
    LineItemStartDate: Optional[str] = ComparableField(
        comparator=ExactComparator(), threshold=1.0, weight=1.0
    )
    LineItemEndDate: Optional[str] = ComparableField(
        comparator=ExactComparator(), threshold=1.0, weight=1.0
    )
    LineItemDays: Optional[int] = ComparableField(
        comparator=NumericComparator(), threshold=0.95, weight=1.0
    )
    LineItemRate: float = ComparableField(
        comparator=NumericComparator(), threshold=0.9, weight=1.5
    )


class DocumentClass(StructuredModel):
    """Document classification information."""

    type: str = ComparableField(comparator=ExactComparator(), threshold=1.0, weight=1.0)


class SplitDocument(StructuredModel):
    """Document page splitting information."""

    page_indices: List[int] = ComparableField(
        comparator=NumericComparator(), threshold=0.95, weight=1.0
    )


class InferenceResult(StructuredModel):
    """Invoice inference result matching the provided schema."""

    Agency: str = ComparableField(
        comparator=LevenshteinComparator(), threshold=0.8, weight=2.0
    )
    Advertiser: str = ComparableField(
        comparator=LevenshteinComparator(), threshold=0.8, weight=2.0
    )
    GrossTotal: float = ComparableField(
        comparator=NumericComparator(), threshold=0.95, weight=2.0
    )
    PaymentTerms: str = ComparableField(
        comparator=ExactComparator(), threshold=1.0, weight=1.0
    )
    AgencyCommission: float = ComparableField(
        comparator=NumericComparator(), threshold=0.95, weight=1.5
    )
    NetAmountDue: float = ComparableField(
        comparator=NumericComparator(), threshold=0.95, weight=2.0
    )
    LineItems: List[LineItem] = ComparableField(weight=1.0)


class Metadata(StructuredModel):
    """Processing metadata."""

    parsing_succeeded: bool = ComparableField(
        comparator=ExactComparator(), threshold=1.0, weight=1.0
    )
    extraction_time_seconds: float = ComparableField(
        comparator=NumericComparator(), threshold=0.8, weight=0.5
    )


class Invoice(StructuredModel):
    """Complete invoice model matching the provided schema."""

    document_class: DocumentClass = ComparableField(weight=1.0)

    split_document: SplitDocument = ComparableField(weight=0.5)

    inference_result: InferenceResult = ComparableField(weight=5.0)

    metadata: Metadata = ComparableField(weight=0.5)


def json_to_invoice(json_data: Dict[str, Any], label: str) -> Invoice:
    """Convert JSON data to Invoice object using Pydantic's built-in validation."""
    try:
        # Use Pydantic's model_validate for clean JSON to model conversion
        invoice = Invoice.model_validate(json_data)
        print(
            f"✓ Successfully created {label} Invoice object using Pydantic validation"
        )
        return invoice

    except Exception as e:
        print(f"Error creating {label} Invoice object: {e}")
        print(f"JSON data keys: {list(json_data.keys())}")

        # If direct validation fails, try the manual approach as fallback
        try:
            print(f"Attempting manual conversion for {label}...")

            # Extract the main sections
            doc_class_data = json_data.get("document_class", {})
            split_doc_data = json_data.get("split_document", {})
            inference_data = json_data.get("inference_result", {})
            metadata_data = json_data.get("metadata", {})

            # Create nested objects manually
            document_class = DocumentClass(**doc_class_data)
            split_document = SplitDocument(**split_doc_data)
            metadata = Metadata(**metadata_data)

            # Handle LineItems
            line_items = []
            for item_data in inference_data.get("LineItems", []):
                line_item = LineItem(**item_data)
                line_items.append(line_item)

            # Create InferenceResult with LineItems
            inference_result_data = inference_data.copy()
            inference_result_data["LineItems"] = line_items
            inference_result = InferenceResult(**inference_result_data)

            # Create Invoice
            invoice = Invoice(
                document_class=document_class,
                split_document=split_document,
                inference_result=inference_result,
                metadata=metadata,
            )

            print(
                f"✓ Successfully created {label} Invoice object using manual conversion"
            )
            return invoice

        except Exception as manual_error:
            print(f"Manual conversion also failed: {manual_error}")
            raise


def test_field_comparisons_with_real_data():
    """Test the new field comparison collection feature with real JSON data."""
    print("\n" + "=" * 70)
    print("TESTING FIELD COMPARISON COLLECTION WITH REAL DATA")
    print("=" * 70)

    # Try to load the JSON files from the root directory
    expected_file = "expected-cee75ca6adb0224732696bff7ee5dc32.pdf.json"
    actual_file = "actual-cee75ca6adb0224732696bff7ee5dc32.pdf.json.json"

    try:
        # Load expected (ground truth) file
        if os.path.exists(expected_file):
            with open(expected_file, "r") as f:
                expected_data = json.load(f)
            print(f"Loaded expected file: {expected_file}")
        else:
            print(f"Expected file not found: {expected_file}")
            print("Please copy the expected JSON file to the root directory")
            return []

        # Load actual (prediction) file
        if os.path.exists(actual_file):
            with open(actual_file, "r") as f:
                actual_data = json.load(f)
            print(f"Loaded actual file: {actual_file}")
        else:
            print(f"Actual file not found: {actual_file}")
            print("Please copy the actual JSON file to the root directory")
            return []

        # Create Invoice objects from the JSON data
        print("\nCreating Invoice objects from JSON data...")

        # Convert JSON to Invoice objects
        gt_invoice = json_to_invoice(expected_data, "Ground Truth")
        pred_invoice = json_to_invoice(actual_data, "Prediction")

        # Run comparison with field comparison documentation
        print("\nRunning comparison with field comparison collection...")
        result = gt_invoice.compare_with(
            pred_invoice, document_field_comparisons=True, include_confusion_matrix=True
        )

        print(f"\nOverall Score: {result['overall_score']:.3f}")
        print(f"Field Scores: {result.get('field_scores', {})}")

        # Show the field comparisons
        field_comparisons = result.get("field_comparisons", [])
        print_field_comparisons(field_comparisons, "Real JSON Files Field Comparisons")

        return field_comparisons

    except Exception as e:
        print(f"Error loading JSON files: {e}")


def print_field_comparisons(field_comparisons: List[dict], title: str):
    """Print field comparisons in a readable format."""
    print(f"\n{title}:")
    print(f"Found {len(field_comparisons)} field comparisons")

    for i, fc in enumerate(field_comparisons):
        print(f"\nField Comparison #{i + 1}:")
        print(f"  Expected Key: {fc.get('expected_key', 'N/A')}")
        print(f"  Expected Value: {fc.get('expected_value', 'N/A')}")
        print(f"  Actual Key: {fc.get('actual_key', 'N/A')}")
        print(f"  Actual Value: {fc.get('actual_value', 'N/A')}")
        print(f"  Match: {fc.get('match', 'N/A')}")
        print(f"  Score: {fc.get('score', 'N/A')}")
        print(f"  Weighted Score: {fc.get('weighted_score', 'N/A')}")
        print(f"  Reason: {fc.get('reason', 'N/A')}")


def main():
    """Run all tests and analyze the results."""
    print("Testing Current Non-Match Collection Behavior for Invoice Processing")
    print("=" * 70)

    try:
        # Test the new field comparison collection feature
        field_comparisons = test_field_comparisons_with_real_data()

        if field_comparisons:
            print(
                f"\nField comparison collection feature working! Collected {len(field_comparisons)} field comparisons"
            )
        else:
            print(
                "\nField comparison collection feature not working or no comparisons found"
            )

    except Exception as e:
        print(f"Error running tests: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
