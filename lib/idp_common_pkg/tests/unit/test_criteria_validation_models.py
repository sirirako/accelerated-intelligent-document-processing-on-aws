# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for criteria validation models after Pydantic to dataclasses migration.
"""

import sys
from unittest.mock import MagicMock

# Mock s3fs to prevent import errors during testing
sys.modules['s3fs'] = MagicMock()

import pytest
import idp_common.criteria_validation.models as models

BedrockInput = models.BedrockInput
LLMResponse = models.LLMResponse
CriteriaValidationResult = models.CriteriaValidationResult


class TestBedrockInput:
    """Test BedrockInput dataclass."""

    def test_basic_creation(self):
        """Test basic object creation with required fields."""
        input_obj = BedrockInput(
            question="Test question",
            prompt="Test prompt",
            system_prompt="Test system prompt",
            criteria_type="test_type",
            recommendation="Pass",
        )

        assert input_obj.question == "Test question"
        assert input_obj.prompt == "Test prompt"
        assert input_obj.system_prompt == "Test system prompt"
        assert input_obj.criteria_type == "test_type"
        assert input_obj.recommendation == "Pass"
        assert input_obj.user_history is None
        assert input_obj.txt_file_uri is None
        assert input_obj.initial_response is None

    def test_whitespace_stripping(self):
        """Test that whitespace is stripped from string fields."""
        input_obj = BedrockInput(
            question="  Test question  ",
            prompt="  Test prompt  ",
            system_prompt="  Test system prompt  ",
            criteria_type="  test_type  ",
            recommendation="  Pass  ",
            user_history="  User history  ",
            txt_file_uri="  s3://bucket/file.txt  ",
        )

        assert input_obj.question == "Test question"
        assert input_obj.prompt == "Test prompt"
        assert input_obj.system_prompt == "Test system prompt"
        assert input_obj.criteria_type == "test_type"
        assert input_obj.recommendation == "Pass"
        assert input_obj.user_history == "User history"
        assert input_obj.txt_file_uri == "s3://bucket/file.txt"

    def test_to_dict_method(self):
        """Test conversion to dictionary."""
        input_obj = BedrockInput(
            question="Test question",
            prompt="Test prompt",
            system_prompt="Test system prompt",
            criteria_type="test_type",
            recommendation="Pass",
        )

        result = input_obj.to_dict()
        assert isinstance(result, dict)
        assert result["question"] == "Test question"
        assert result["prompt"] == "Test prompt"
        assert result["system_prompt"] == "Test system prompt"
        assert result["criteria_type"] == "test_type"
        assert result["recommendation"] == "Pass"
        assert result["user_history"] is None


class TestLLMResponse:
    """Test LLMResponse dataclass."""

    def test_basic_creation(self):
        """Test basic object creation with required fields."""
        response = LLMResponse(
            criteria_type="test_type",
            question="Test question",
            Recommendation="Pass",
            Reasoning="Test reasoning",
        )

        assert response.criteria_type == "test_type"
        assert response.question == "Test question"
        assert response.Recommendation == "Pass"
        assert response.Reasoning == "Test reasoning"
        assert response.source_file == []

    def test_recommendation_validation(self):
        """Test that Recommendation field validates allowed values."""
        # Valid values
        for valid_value in ["Pass", "Fail", "Information Not Found"]:
            response = LLMResponse(
                criteria_type="test_type",
                question="Test question",
                Recommendation=valid_value,
                Reasoning="Test reasoning",
            )
            assert response.Recommendation == valid_value

        # Invalid value
        with pytest.raises(ValueError, match="Recommendation must be one of"):
            LLMResponse(
                criteria_type="test_type",
                question="Test question",
                Recommendation="Invalid",
                Reasoning="Test reasoning",
            )

    def test_reasoning_cleaning(self):
        """Test that Reasoning field is cleaned properly."""
        # Test removing line breaks and extra spaces
        response = LLMResponse(
            criteria_type="test_type",
            question="Test question",
            Recommendation="Pass",
            Reasoning="Test\nreasoning\nwith   multiple\tspaces",
        )
        assert response.Reasoning == "Test reasoning with multiple spaces"

        # Test removing markdown bullets
        response = LLMResponse(
            criteria_type="test_type",
            question="Test question",
            Recommendation="Pass",
            Reasoning="- Test reasoning",
        )
        assert response.Reasoning == "Test reasoning"

        # Test removing numbered lists
        response = LLMResponse(
            criteria_type="test_type",
            question="Test question",
            Recommendation="Pass",
            Reasoning="1. Test reasoning",
        )
        assert response.Reasoning == "Test reasoning"

    def test_source_file_validation(self):
        """Test that source_file URLs are properly validated."""
        # Test with s3:// prefix
        response = LLMResponse(
            criteria_type="test_type",
            question="Test question",
            Recommendation="Pass",
            Reasoning="Test reasoning",
            source_file=["s3://bucket/file1.txt", "s3://bucket/file2.txt"],
        )
        assert response.source_file == [
            "s3://bucket/file1.txt",
            "s3://bucket/file2.txt",
        ]

        # Test without s3:// prefix - should be added
        response = LLMResponse(
            criteria_type="test_type",
            question="Test question",
            Recommendation="Pass",
            Reasoning="Test reasoning",
            source_file=["bucket/file1.txt", "s3://bucket/file2.txt"],
        )
        assert response.source_file == [
            "s3://bucket/file1.txt",
            "s3://bucket/file2.txt",
        ]

    def test_extra_fields_forbidden(self):
        """Test that extra fields are not allowed."""
        with pytest.raises(TypeError, match="Unexpected keyword arguments"):
            LLMResponse(
                criteria_type="test_type",
                question="Test question",
                Recommendation="Pass",
                Reasoning="Test reasoning",
                extra_field="not allowed",
            )

    def test_dict_method(self):
        """Test conversion to dictionary using dict() method."""
        response = LLMResponse(
            criteria_type="test_type",
            question="Test question",
            Recommendation="Pass",
            Reasoning="Test reasoning",
            source_file=["s3://bucket/file.txt"],
        )

        result = response.dict()
        assert isinstance(result, dict)
        assert result["criteria_type"] == "test_type"
        assert result["question"] == "Test question"
        assert result["Recommendation"] == "Pass"
        assert result["Reasoning"] == "Test reasoning"
        assert result["source_file"] == ["s3://bucket/file.txt"]

    def test_whitespace_stripping(self):
        """Test that whitespace is stripped from string fields."""
        response = LLMResponse(
            criteria_type="  test_type  ",
            question="  Test question  ",
            Recommendation="  Pass  ",
            Reasoning="  Test reasoning  ",
        )

        assert response.criteria_type == "test_type"
        assert response.question == "Test question"
        assert response.Recommendation == "Pass"
        assert response.Reasoning == "Test reasoning"


class TestCriteriaValidationResult:
    """Test CriteriaValidationResult dataclass."""

    def test_basic_creation(self):
        """Test basic object creation."""
        result = CriteriaValidationResult(
            request_id="test-123",
            criteria_type="test_type",
            validation_responses=[{"test": "response"}],
        )

        assert result.request_id == "test-123"
        assert result.criteria_type == "test_type"
        assert result.validation_responses == [{"test": "response"}]
        assert result.summary is None
        assert result.metering is None
        assert result.metadata is None
        assert result.output_uri is None
        assert result.errors is None
        assert result.cost_tracking is None

    def test_all_fields(self):
        """Test creation with all optional fields."""
        result = CriteriaValidationResult(
            request_id="test-123",
            criteria_type="test_type",
            validation_responses=[{"test": "response"}],
            summary={"summary": "data"},
            metering={"tokens": 100},
            metadata={"files_processed": 2},
            output_uri="s3://bucket/output.json",
            errors=["error1", "error2"],
            cost_tracking={"cost": 0.01},
        )

        assert result.request_id == "test-123"
        assert result.criteria_type == "test_type"
        assert result.validation_responses == [{"test": "response"}]
        assert result.summary == {"summary": "data"}
        assert result.metering == {"tokens": 100}
        assert result.metadata == {"files_processed": 2}
        assert result.output_uri == "s3://bucket/output.json"
        assert result.errors == ["error1", "error2"]
        assert result.cost_tracking == {"cost": 0.01}
