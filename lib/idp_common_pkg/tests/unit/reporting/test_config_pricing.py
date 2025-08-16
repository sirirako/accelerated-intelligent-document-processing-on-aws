#!/usr/bin/env python3
"""
Unit tests for configuration-based pricing functionality in SaveReportingData
"""

import pytest
from unittest.mock import patch, MagicMock
from idp_common.reporting.save_reporting_data import SaveReportingData


@pytest.mark.unit
def test_pricing_from_config_with_valid_configuration():
    """Test that pricing is loaded correctly from DynamoDB configuration"""
    
    # Mock configuration data that matches the expected format
    mock_config = {
        'pricing': [
            {
                'name': 'textract/detect_document_text',
                'units': [
                    {'name': 'pages', 'price': '0.002'}  # Different from hardcoded value
                ]
            },
            {
                'name': 'bedrock/us.amazon.nova-lite-v1:0',
                'units': [
                    {'name': 'inputTokens', 'price': '7.0E-8'},  # Different from hardcoded value
                    {'name': 'outputTokens', 'price': '3.0E-7'}
                ]
            }
        ]
    }
    
    with patch('idp_common.reporting.save_reporting_data.get_config') as mock_get_config:
        mock_get_config.return_value = mock_config
        
        # Create SaveReportingData instance with config table name
        reporter = SaveReportingData("test-bucket", config_table_name="test-config-table")
        
        # Test that pricing is loaded from configuration
        textract_cost = reporter._get_unit_cost("textract/detect_document_text", "pages")
        nova_input_cost = reporter._get_unit_cost("bedrock/us.amazon.nova-lite-v1:0", "inputTokens")
        nova_output_cost = reporter._get_unit_cost("bedrock/us.amazon.nova-lite-v1:0", "outputTokens")
        
        # Verify the costs match the configuration values, not hardcoded values
        assert textract_cost == 0.002, f"Expected 0.002, got {textract_cost}"
        assert nova_input_cost == 7.0e-8, f"Expected 7.0e-8, got {nova_input_cost}"
        assert nova_output_cost == 3.0e-7, f"Expected 3.0e-7, got {nova_output_cost}"
        
        # Verify get_config was called with the correct table name
        mock_get_config.assert_called_once_with("test-config-table")


@pytest.mark.unit
def test_pricing_fallback_to_hardcoded_when_config_fails():
    """Test that pricing falls back to hardcoded values when configuration loading fails"""
    
    with patch('idp_common.reporting.save_reporting_data.get_config') as mock_get_config:
        # Simulate configuration loading failure
        mock_get_config.side_effect = Exception("DynamoDB connection failed")
        
        # Create SaveReportingData instance with config table name
        reporter = SaveReportingData("test-bucket", config_table_name="test-config-table")
        
        # Test that pricing falls back to hardcoded values
        textract_cost = reporter._get_unit_cost("textract/detect_document_text", "pages")
        nova_input_cost = reporter._get_unit_cost("bedrock/us.amazon.nova-lite-v1:0", "inputTokens")
        
        # Verify the costs match the hardcoded fallback values
        assert textract_cost == 0.0015, f"Expected 0.0015 (hardcoded fallback), got {textract_cost}"
        assert nova_input_cost == 6.0e-8, f"Expected 6.0e-8 (hardcoded fallback), got {nova_input_cost}"


@pytest.mark.unit
def test_pricing_without_config_table_uses_hardcoded():
    """Test that pricing uses hardcoded values when no config table is provided"""
    
    # Create SaveReportingData instance without config table name
    reporter = SaveReportingData("test-bucket")
    
    # Test that pricing uses hardcoded values
    textract_cost = reporter._get_unit_cost("textract/detect_document_text", "pages")
    nova_input_cost = reporter._get_unit_cost("bedrock/us.amazon.nova-lite-v1:0", "inputTokens")
    
    # Verify the costs match the hardcoded values
    assert textract_cost == 0.0015, f"Expected 0.0015 (hardcoded), got {textract_cost}"
    assert nova_input_cost == 6.0e-8, f"Expected 6.0e-8 (hardcoded), got {nova_input_cost}"


@pytest.mark.unit
def test_pricing_cache_functionality():
    """Test that pricing data is cached to avoid repeated configuration calls"""
    
    mock_config = {
        'pricing': [
            {
                'name': 'textract/detect_document_text',
                'units': [
                    {'name': 'pages', 'price': '0.002'}
                ]
            }
        ]
    }
    
    with patch('idp_common.reporting.save_reporting_data.get_config') as mock_get_config:
        mock_get_config.return_value = mock_config
        
        reporter = SaveReportingData("test-bucket", config_table_name="test-config-table")
        
        # Call _get_unit_cost multiple times
        cost1 = reporter._get_unit_cost("textract/detect_document_text", "pages")
        cost2 = reporter._get_unit_cost("textract/detect_document_text", "pages")
        cost3 = reporter._get_unit_cost("textract/detect_document_text", "pages")
        
        # Verify all calls return the same value
        assert cost1 == cost2 == cost3 == 0.002
        
        # Verify get_config was only called once (due to caching)
        assert mock_get_config.call_count == 1


@pytest.mark.unit
def test_clear_pricing_cache():
    """Test that clearing the cache forces reload of configuration"""
    
    mock_config = {
        'pricing': [
            {
                'name': 'textract/detect_document_text',
                'units': [
                    {'name': 'pages', 'price': '0.002'}
                ]
            }
        ]
    }
    
    with patch('idp_common.reporting.save_reporting_data.get_config') as mock_get_config:
        mock_get_config.return_value = mock_config
        
        reporter = SaveReportingData("test-bucket", config_table_name="test-config-table")
        
        # First call loads from config
        cost1 = reporter._get_unit_cost("textract/detect_document_text", "pages")
        assert cost1 == 0.002
        assert mock_get_config.call_count == 1
        
        # Clear cache
        reporter.clear_pricing_cache()
        
        # Second call should reload from config
        cost2 = reporter._get_unit_cost("textract/detect_document_text", "pages")
        assert cost2 == 0.002
        assert mock_get_config.call_count == 2  # Called again after cache clear


@pytest.mark.unit
def test_pricing_with_invalid_price_values():
    """Test handling of invalid price values in configuration"""
    
    mock_config = {
        'pricing': [
            {
                'name': 'textract/detect_document_text',
                'units': [
                    {'name': 'pages', 'price': 'invalid_price'},  # Invalid price
                    {'name': 'documents', 'price': '0.002'}  # Valid price
                ]
            }
        ]
    }
    
    with patch('idp_common.reporting.save_reporting_data.get_config') as mock_get_config:
        mock_get_config.return_value = mock_config
        
        reporter = SaveReportingData("test-bucket", config_table_name="test-config-table")
        
        # Test that invalid price is skipped and fallback is used
        invalid_cost = reporter._get_unit_cost("textract/detect_document_text", "pages")
        valid_cost = reporter._get_unit_cost("textract/detect_document_text", "documents")
        
        # Invalid price should fall back to hardcoded value
        assert invalid_cost == 0.0015  # Hardcoded fallback
        # Valid price should use config value
        assert valid_cost == 0.002
