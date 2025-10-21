#!/usr/bin/env python
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Unit tests for few-shot example migration from legacy to JSON Schema format."""

import pytest
from idp_common.config.migration import is_legacy_format, migrate_legacy_to_schema
from idp_common.config.schema_constants import (
    LEGACY_ATTRIBUTES_PROMPT,
    LEGACY_CLASS_PROMPT,
    LEGACY_IMAGE_PATH,
    SCHEMA_EXAMPLES,
    X_AWS_IDP_ATTRIBUTES_PROMPT,
    X_AWS_IDP_CLASS_PROMPT,
    X_AWS_IDP_IMAGE_PATH,
)


@pytest.mark.unit
class TestExampleMigration:
    """Tests for migrating few-shot examples from legacy to JSON Schema format."""

    @pytest.fixture
    def sample_legacy_config_with_examples(self):
        """Load the actual sample config with few-shot examples."""
        # Use a simplified version based on the actual config structure
        return {
            "classes": [
                {
                    "name": "letter",
                    "description": "A formal written correspondence with sender/recipient addresses",
                    "attributes": [
                        {
                            "name": "sender_name",
                            "description": "The name of the person who sent the letter",
                            "attributeType": "simple",
                        },
                        {
                            "name": "recipient_name",
                            "description": "The name of the person receiving the letter",
                            "attributeType": "simple",
                        },
                    ],
                    "examples": [
                        {
                            "classPrompt": "This is an example of the class 'letter'",
                            "name": "Letter1",
                            "attributesPrompt": '''expected attributes are:
                                "sender_name": "Will E. Clark",
                                "sender_address": "206 Maple Street P.O. Box 1056 Murray Kentucky 42071-1056",
                                "recipient_name": "The Honorable Wendell H. Ford",
                                "recipient_address": "United States Senate Washington, D. C. 20510",
                                "date": "10/31/1995",
                                "subject": null,
                                "letter_type": "opposition letter",
                                "signature": "Will E. Clark",
                                "cc": null,
                                "reference_number": "TNJB 0008497"''',
                            "imagePath": "config_library/pattern-2/example-images/letter1.jpg",
                        },
                        {
                            "classPrompt": "This is an example of the class 'letter'",
                            "name": "Letter2",
                            "attributesPrompt": '''expected attributes are:
                                "sender_name": "William H. W. Anderson",
                                "recipient_name": "Mr. Addison Y. Yeaman",
                                "date": "10/14/1970"''',
                            "imagePath": "config_library/pattern-2/example-images/letter2.png",
                        },
                    ],
                }
            ]
        }

    @pytest.fixture
    def legacy_config_without_examples(self):
        """Legacy config without examples to ensure backward compatibility."""
        return {
            "classes": [
                {
                    "name": "invoice",
                    "description": "A commercial document",
                    "attributes": [
                        {
                            "name": "invoice_number",
                            "description": "The invoice number",
                            "attributeType": "simple",
                        }
                    ],
                }
            ]
        }

    def test_detects_legacy_format_with_examples(
        self, sample_legacy_config_with_examples
    ):
        """Test that configurations with examples are detected as legacy format."""
        assert is_legacy_format(sample_legacy_config_with_examples["classes"])

    def test_migrates_examples_to_json_schema(self, sample_legacy_config_with_examples):
        """Test that examples are properly migrated to JSON Schema format."""
        migrated = migrate_legacy_to_schema(
            sample_legacy_config_with_examples["classes"]
        )

        assert len(migrated) == 1, "Should have one schema"
        schema = migrated[0]

        # Check that examples field exists
        assert SCHEMA_EXAMPLES in schema, "Schema should contain examples field"
        examples = schema[SCHEMA_EXAMPLES]

        # Check correct number of examples
        assert len(examples) == 2, "Should have 2 examples"

        # Check first example structure
        example1 = examples[0]
        assert example1.get("name") == "Letter1"
        assert X_AWS_IDP_CLASS_PROMPT in example1
        assert (
            example1[X_AWS_IDP_CLASS_PROMPT]
            == "This is an example of the class 'letter'"
        )
        assert X_AWS_IDP_ATTRIBUTES_PROMPT in example1
        assert X_AWS_IDP_IMAGE_PATH in example1
        assert (
            example1[X_AWS_IDP_IMAGE_PATH]
            == "config_library/pattern-2/example-images/letter1.jpg"
        )

        # Check second example
        example2 = examples[1]
        assert example2.get("name") == "Letter2"
        assert X_AWS_IDP_CLASS_PROMPT in example2
        assert X_AWS_IDP_IMAGE_PATH in example2

    def test_extracts_attribute_values_from_prompt(
        self, sample_legacy_config_with_examples
    ):
        """Test that attribute values are extracted from the attributes prompt."""
        migrated = migrate_legacy_to_schema(
            sample_legacy_config_with_examples["classes"]
        )
        schema = migrated[0]
        examples = schema[SCHEMA_EXAMPLES]

        example1 = examples[0]

        # Check if values were extracted from the prompt
        # The migration should attempt to parse JSON-like values from the prompt
        if "sender_name" in example1:
            assert example1["sender_name"] == "Will E. Clark"
        if "recipient_name" in example1:
            assert example1["recipient_name"] == "The Honorable Wendell H. Ford"
        if "date" in example1:
            assert example1["date"] == "10/31/1995"

    def test_extracts_values_when_prompt_contains_json_block(self):
        """Ensure JSON blocks inside prompts are parsed into example values."""
        config = {
            "classes": [
                {
                    "name": "json_example",
                    "description": "Test class with JSON prompt",
                    "attributes": [],
                    "examples": [
                        {
                            "name": "JsonPrompt",
                            "classPrompt": "Example with embedded JSON",
                            "attributesPrompt": 'Expected output:\\n{ "foo": "bar", "count": 3 }\\nEnd.',
                            "imagePath": "config_library/example.jpg",
                        }
                    ],
                }
            ]
        }

        migrated = migrate_legacy_to_schema(config["classes"])
        examples = migrated[0][SCHEMA_EXAMPLES]

        assert len(examples) == 1
        example = examples[0]
        assert example.get("foo") == "bar"
        assert example.get("count") == 3

    def test_migration_without_examples(self, legacy_config_without_examples):
        """Test that migration works for configs without examples."""
        migrated = migrate_legacy_to_schema(legacy_config_without_examples["classes"])

        assert len(migrated) == 1
        schema = migrated[0]

        # Schema should not have examples field if none were provided
        # or it should have an empty array
        if SCHEMA_EXAMPLES in schema:
            assert schema[SCHEMA_EXAMPLES] == [] or schema[SCHEMA_EXAMPLES] is None

    def test_preserves_example_metadata(self, sample_legacy_config_with_examples):
        """Test that all example metadata is preserved during migration."""
        legacy_examples = sample_legacy_config_with_examples["classes"][0]["examples"]
        migrated = migrate_legacy_to_schema(
            sample_legacy_config_with_examples["classes"]
        )
        migrated_examples = migrated[0][SCHEMA_EXAMPLES]

        for i, legacy_ex in enumerate(legacy_examples):
            migrated_ex = migrated_examples[i]

            # Check that all legacy fields are preserved with new names
            assert migrated_ex["name"] == legacy_ex["name"]
            assert migrated_ex[X_AWS_IDP_CLASS_PROMPT] == legacy_ex[LEGACY_CLASS_PROMPT]
            assert (
                migrated_ex[X_AWS_IDP_ATTRIBUTES_PROMPT]
                == legacy_ex[LEGACY_ATTRIBUTES_PROMPT]
            )
            assert migrated_ex[X_AWS_IDP_IMAGE_PATH] == legacy_ex[LEGACY_IMAGE_PATH]

    def test_json_schema_structure_with_examples(
        self, sample_legacy_config_with_examples
    ):
        """Test that the overall JSON Schema structure is correct with examples."""
        migrated = migrate_legacy_to_schema(
            sample_legacy_config_with_examples["classes"]
        )
        schema = migrated[0]

        # Verify basic JSON Schema structure
        assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        assert schema.get("$id") == "letter"
        assert schema.get("type") == "object"
        assert "properties" in schema

        # Verify examples are at the correct level
        assert SCHEMA_EXAMPLES in schema
        assert isinstance(schema[SCHEMA_EXAMPLES], list)

    def test_handles_malformed_attributes_prompt(self):
        """Test that migration handles malformed attributes prompts gracefully."""
        config = {
            "classes": [
                {
                    "name": "test",
                    "description": "Test class",
                    "attributes": [],
                    "examples": [
                        {
                            "name": "Test1",
                            "classPrompt": "Test example",
                            "attributesPrompt": "This is not valid JSON or key-value pairs",
                            "imagePath": "test.jpg",
                        }
                    ],
                }
            ]
        }

        # Should not raise an exception
        migrated = migrate_legacy_to_schema(config["classes"])
        examples = migrated[0][SCHEMA_EXAMPLES]

        assert len(examples) == 1
        assert (
            examples[0][X_AWS_IDP_ATTRIBUTES_PROMPT]
            == "This is not valid JSON or key-value pairs"
        )

    def test_handles_empty_examples_array(self):
        """Test that migration handles empty examples array."""
        config = {
            "classes": [
                {
                    "name": "test",
                    "description": "Test class",
                    "attributes": [],
                    "examples": [],
                }
            ]
        }

        migrated = migrate_legacy_to_schema(config["classes"])
        schema = migrated[0]

        # Should either not have examples field or have empty array
        if SCHEMA_EXAMPLES in schema:
            assert schema[SCHEMA_EXAMPLES] == []
