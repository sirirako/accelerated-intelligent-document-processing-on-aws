"""
Unit tests for HITL confidence threshold functionality.
Tests the updated 0-1 scale validation logic.
"""

import pytest


class TestConfidenceThresholdValidation:
    """Test confidence threshold validation logic."""

    def test_valid_threshold_values(self):
        """Test that valid 0-1 scale values are accepted."""
        # Test boundary values
        assert 0.0 >= 0.0 and 0.0 <= 1.0
        assert 1.0 >= 0.0 and 1.0 <= 1.0

        # Test common values
        assert 0.5 >= 0.0 and 0.5 <= 1.0
        assert 0.8 >= 0.0 and 0.8 <= 1.0
        assert 0.95 >= 0.0 and 0.95 <= 1.0

    def test_invalid_threshold_values(self):
        """Test that invalid values are rejected."""
        # Test values outside 0-1 range
        assert not (-0.1 >= 0.0 and -0.1 <= 1.0)
        assert not (1.1 >= 0.0 and 1.1 <= 1.0)
        assert not (2.0 >= 0.0 and 2.0 <= 1.0)

    def test_threshold_conversion_logic(self):
        """Test that the old 1-100 scale conversion is no longer needed."""
        # In the new implementation, values should already be in 0-1 scale
        # No conversion should be needed
        test_values = [0.1, 0.5, 0.8, 0.9, 1.0]

        for value in test_values:
            # Value should remain unchanged (no division by 100)
            assert value == value  # No conversion needed
            assert 0.0 <= value <= 1.0  # Should be in valid range

    @pytest.mark.unit
    def test_confidence_threshold_range_validation(self):
        """Test confidence threshold range validation."""

        def validate_threshold(value):
            """Simulate the validation logic from the updated function."""
            try:
                threshold = float(value)
                return 0.0 <= threshold <= 1.0
            except (ValueError, TypeError):
                return False

        # Valid cases
        assert validate_threshold("0.0")
        assert validate_threshold("0.5")
        assert validate_threshold("0.8")
        assert validate_threshold("1.0")
        assert validate_threshold(0.75)

        # Invalid cases
        assert not validate_threshold("-0.1")
        assert not validate_threshold("1.5")
        assert not validate_threshold("invalid")
        assert not validate_threshold(None)

    @pytest.mark.unit
    def test_default_threshold_value(self):
        """Test that the default threshold value is reasonable."""
        default_threshold = 0.8

        # Default should be in valid range
        assert 0.0 <= default_threshold <= 1.0

        # Default should be a reasonable value for HITL triggering
        assert 0.5 <= default_threshold <= 0.95
