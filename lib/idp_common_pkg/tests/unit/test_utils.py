# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for the utils module.
"""

import json

import pytest
from idp_common.utils import extract_json_from_text


@pytest.mark.unit
class TestExtractJsonFromText:
    """Tests for the extract_json_from_text function."""

    def test_extract_json_code_block(self):
        """Test extracting JSON from ```json code block."""
        text = 'Here is the result:\n```json\n{"class": "invoice"}\n```\nEnd of result.'
        result = extract_json_from_text(text)
        assert result == '{"class": "invoice"}'

        # Verify it's valid JSON
        parsed = json.loads(result)
        assert parsed["class"] == "invoice"

    def test_extract_json_generic_code_block(self):
        """Test extracting JSON from generic ``` code block."""
        text = 'Here is the result:\n```\n{"invoice_number": "INV-123"}\n```\nEnd of result.'
        result = extract_json_from_text(text)
        assert result == '{"invoice_number": "INV-123"}'

        # Verify it's valid JSON
        parsed = json.loads(result)
        assert parsed["invoice_number"] == "INV-123"

    def test_extract_json_simple(self):
        """Test extracting JSON without code blocks."""
        text = 'The classification is {"class": "receipt"} based on the content.'
        result = extract_json_from_text(text)
        assert result == '{"class": "receipt"}'

        # Verify it's valid JSON
        parsed = json.loads(result)
        assert parsed["class"] == "receipt"

    def test_extract_json_nested(self):
        """Test extracting nested JSON."""
        text = 'Result: {"class": "letter", "metadata": {"confidence": 0.9}}'
        result = extract_json_from_text(text)
        assert result == '{"class": "letter", "metadata": {"confidence": 0.9}}'

        # Verify it's valid JSON
        parsed = json.loads(result)
        assert parsed["class"] == "letter"
        assert parsed["metadata"]["confidence"] == 0.9

    def test_extract_json_no_json(self):
        """Test with text containing no JSON."""
        text = "No JSON here"
        result = extract_json_from_text(text)
        assert result == "No JSON here"

    def test_extract_json_empty_text(self):
        """Test with empty text."""
        result = extract_json_from_text("")
        assert result == ""

    def test_extract_json_multiline_in_code_block(self):
        """Test extracting JSON with literal newlines in string values within code blocks."""
        text = """Here is the extracted data:
```json
{
    "summary": "This is a multi-line
summary that spans
multiple lines",
    "key_points": [
        "Point 1 with
newline",
        "Point 2"
    ],
    "description": "Another field
with newlines"
}
```
End of response."""

        result = extract_json_from_text(text)

        # Should be able to parse the result as valid JSON
        parsed = json.loads(result)
        assert "summary" in parsed
        assert "key_points" in parsed
        assert "description" in parsed
        assert len(parsed["key_points"]) == 2

    def test_extract_json_multiline_without_code_blocks(self):
        """Test extracting JSON with newlines but without code blocks."""
        text = """The result is {
    "invoice_number": "INV-123",
    "description": "This is a long
description that spans
multiple lines",
    "amount": 100.50
} based on the document analysis."""

        result = extract_json_from_text(text)

        # Should be able to parse the result as valid JSON
        parsed = json.loads(result)
        assert parsed["invoice_number"] == "INV-123"
        assert "description" in parsed
        assert parsed["amount"] == 100.50

    def test_extract_json_complex_nested_with_newlines(self):
        """Test extracting complex nested JSON with newlines."""
        text = """```json
{
    "document_type": "invoice",
    "extracted_fields": {
        "vendor_info": {
            "name": "ACME Corp",
            "address": "123 Main St
Suite 100
Anytown, ST 12345"
        },
        "line_items": [
            {
                "description": "Product A
with detailed specs",
                "quantity": 2,
                "price": 50.00
            }
        ]
    },
    "notes": "This invoice contains
multiple line items
with complex descriptions"
}
```"""

        result = extract_json_from_text(text)

        # Should be able to parse the result as valid JSON
        parsed = json.loads(result)
        assert parsed["document_type"] == "invoice"
        assert "vendor_info" in parsed["extracted_fields"]
        assert "line_items" in parsed["extracted_fields"]
        assert len(parsed["extracted_fields"]["line_items"]) == 1
        assert parsed["extracted_fields"]["line_items"][0]["quantity"] == 2

    def test_extract_json_with_escaped_quotes(self):
        """Test extracting JSON with escaped quotes and newlines."""
        text = """{
    "text": "He said \\"Hello world\\" to everyone",
    "multiline": "Line 1\\nLine 2\\nLine 3"
}"""

        result = extract_json_from_text(text)

        # Should be able to parse the result as valid JSON
        parsed = json.loads(result)
        assert 'He said "Hello world" to everyone' in parsed["text"]
        assert "Line 1\nLine 2\nLine 3" == parsed["multiline"]

    def test_extract_json_malformed_fallback(self):
        """Test that malformed JSON falls back to original text."""
        text = 'Here is malformed JSON: { "key": "value" missing closing brace'
        result = extract_json_from_text(text)
        # Should return original text when JSON is malformed
        assert result == text

    def test_extract_json_multiple_json_objects(self):
        """Test extracting the first valid JSON object when multiple exist."""
        text = 'First: {"a": 1} and second: {"b": 2}'
        result = extract_json_from_text(text)

        # Should extract the first complete JSON object
        parsed = json.loads(result)
        assert parsed["a"] == 1

    def test_extract_json_with_arrays(self):
        """Test extracting JSON containing arrays."""
        text = """The extracted data is:
```json
{
    "items": [
        {"name": "Item 1", "value": 10},
        {"name": "Item 2", "value": 20}
    ],
    "total": 30
}
```"""

        result = extract_json_from_text(text)

        # Should be able to parse the result as valid JSON
        parsed = json.loads(result)
        assert len(parsed["items"]) == 2
        assert parsed["items"][0]["name"] == "Item 1"
        assert parsed["total"] == 30
