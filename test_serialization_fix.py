#!/usr/bin/env python3
"""
Test script to verify that the JSON serialization fix resolves the DynamicModel error.

This test simulates the exact scenario that caused the Lambda failure:
- Creating Pydantic models with nested structures
- Serializing them to JSON
- Ensuring no "Object of type DynamicModel is not JSON serializable" errors
"""

import json
import sys
from typing import List

sys.path.insert(0, "lib/idp_common_pkg")

from idp_common.evaluation.service import _convert_numpy_types


def test_pydantic_model_serialization():
    """Test that nested Pydantic models serialize correctly."""
    print("\n" + "=" * 80)
    print("TEST: Pydantic Model Serialization with _convert_numpy_types")
    print("=" * 80)

    from pydantic import create_model

    # Create nested Pydantic models similar to what Stickler creates
    AddressModel = create_model(
        "AddressModel",
        street=(str, ...),
        city=(str, ...),
        state=(str, ...),
        zip_code=(str, ...),
    )

    LineItemModel = create_model(
        "LineItemModel",
        description=(str, ...),
        amount=(float, ...),
        quantity=(int, ...),
    )

    InvoiceModel = create_model(
        "InvoiceModel",
        invoice_number=(str, ...),
        total=(float, ...),
        address=(AddressModel, ...),
        line_items=(List[LineItemModel], ...),
    )

    # Create test data with nested models
    address = AddressModel(
        street="123 Main St", city="Seattle", state="WA", zip_code="98101"
    )

    line_items = [
        LineItemModel(description="Widget A", amount=100.50, quantity=2),
        LineItemModel(description="Widget B", amount=250.75, quantity=1),
    ]

    invoice = InvoiceModel(
        invoice_number="INV-12345", total=451.75, address=address, line_items=line_items
    )

    print("\n✅ Created nested Pydantic models successfully")

    # Test 1: Serialize using model_dump with mode='python'
    print("\n📊 Test 1: model_dump(mode='python')")
    try:
        serialized = invoice.model_dump(mode="python")
        print("   ✅ model_dump(mode='python') succeeded")
        print(f"   Type of address in result: {type(serialized['address'])}")
        print(
            f"   Type of line_items[0] in result: {type(serialized['line_items'][0])}"
        )

        # Verify it's plain dicts/lists
        assert isinstance(serialized, dict), "Result should be dict"
        assert isinstance(serialized["address"], dict), "Nested object should be dict"
        assert isinstance(serialized["line_items"], list), "Array should be list"
        assert isinstance(serialized["line_items"][0], dict), (
            "Array items should be dict"
        )

        print("   ✅ All nested models converted to plain Python types")

    except Exception as e:
        print(f"   ❌ model_dump(mode='python') failed: {e}")
        return False

    # Test 2: JSON serialize the result
    print("\n📊 Test 2: JSON serialization")
    try:
        json_str = json.dumps(serialized)
        print("   ✅ JSON serialization succeeded")
        print(f"   JSON length: {len(json_str)} bytes")

        # Verify we can load it back
        loaded = json.loads(json_str)
        assert loaded["invoice_number"] == "INV-12345"
        assert loaded["address"]["city"] == "Seattle"
        assert len(loaded["line_items"]) == 2

        print("   ✅ JSON roundtrip successful")

    except Exception as e:
        print(f"   ❌ JSON serialization failed: {e}")
        return False

    # Test 3: Use _convert_numpy_types on result_dict structure
    print("\n📊 Test 3: _convert_numpy_types on evaluation result structure")
    try:
        # Simulate evaluation result structure
        eval_result = {
            "document_id": "test-doc",
            "overall_metrics": {"precision": 0.95, "recall": 0.92},
            "section_results": [
                {
                    "section_id": "section-1",
                    "document_class": "Invoice",
                    "attributes": [
                        {
                            "name": "address",
                            "expected": address,  # Pydantic model
                            "actual": address,  # Pydantic model
                            "matched": True,
                            "score": 1.0,
                        }
                    ],
                }
            ],
        }

        # Apply conversion
        converted = _convert_numpy_types(eval_result)

        print("   ✅ _convert_numpy_types succeeded")

        # Verify Pydantic models were converted
        attr = converted["section_results"][0]["attributes"][0]
        print(f"   Type of expected: {type(attr['expected'])}")
        print(f"   Type of actual: {type(attr['actual'])}")

        assert isinstance(attr["expected"], dict), "Expected should be dict"
        assert isinstance(attr["actual"], dict), "Actual should be dict"

        print("   ✅ Pydantic models converted to dicts")

        # Try JSON serialization
        json_str = json.dumps(converted)
        print("   ✅ Full evaluation result structure serializes to JSON")
        print(f"   JSON length: {len(json_str)} bytes")

    except Exception as e:
        print(f"   ❌ _convert_numpy_types failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    print("\n" + "=" * 80)
    print("✅ ALL SERIALIZATION TESTS PASSED")
    print("=" * 80)
    print("\n🎯 Fix verified:")
    print("   1. model_dump(mode='python') properly serializes nested models")
    print("   2. JSON serialization works without DynamicModel errors")
    print("   3. _convert_numpy_types handles Pydantic models recursively")
    print("\n   The Lambda error should be resolved!")

    return True


def main():
    """Run serialization tests."""
    print("\n" + "=" * 80)
    print("🔧 TESTING JSON SERIALIZATION FIX FOR LAMBDA ERROR")
    print("   Error: Object of type DynamicModel is not JSON serializable")
    print("=" * 80)

    try:
        success = test_pydantic_model_serialization()
        return 0 if success else 1
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
