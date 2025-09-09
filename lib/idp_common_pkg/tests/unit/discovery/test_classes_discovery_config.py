# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for Discovery module configuration functionality.
Tests the new configuration-based approach for ClassesDiscovery.
"""

import json
import unittest
from unittest.mock import Mock, patch

from idp_common.discovery.classes_discovery import ClassesDiscovery


class TestClassesDiscoveryConfig(unittest.TestCase):
    """Test configuration functionality in ClassesDiscovery."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_bucket = "test-bucket"
        self.test_prefix = "test-document.pdf"
        self.test_region = "us-west-2"
        
        # Sample configuration
        self.sample_config = {
            "discovery": {
                "without_ground_truth": {
                    "model_id": "test-model-without-gt",
                    "temperature": 0.5,
                    "top_p": 0.2,
                    "max_tokens": 5000,
                    "system_prompt": "Test system prompt without GT",
                    "user_prompt": "Test user prompt without GT"
                },
                "with_ground_truth": {
                    "model_id": "test-model-with-gt",
                    "temperature": 0.7,
                    "top_p": 0.3,
                    "max_tokens": 7000,
                    "system_prompt": "Test system prompt with GT",
                    "user_prompt": "Test user prompt with GT: {ground_truth_json}"
                },
                "output_format": {
                    "sample_json": '{"test": "format"}'
                }
            }
        }
        
        # Sample ground truth data
        self.sample_ground_truth = {
            "document_class": "TestForm",
            "groups": [
                {
                    "name": "TestGroup",
                    "attributes": [
                        {"name": "TestField", "type": "string"}
                    ]
                }
            ]
        }

    @patch('idp_common.discovery.classes_discovery.boto3.resource')
    @patch('idp_common.discovery.classes_discovery.bedrock.BedrockClient')
    def test_init_with_config(self, mock_bedrock_client, mock_boto3_resource):
        """Test initialization with custom configuration."""
        # Setup mocks
        mock_table = Mock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        
        # Initialize with custom config
        discovery = ClassesDiscovery(
            input_bucket=self.test_bucket,
            input_prefix=self.test_prefix,
            config=self.sample_config,
            region=self.test_region
        )
        
        # Verify configuration is loaded correctly
        self.assertEqual(discovery.config, self.sample_config)
        self.assertEqual(discovery.discovery_config, self.sample_config["discovery"])
        self.assertEqual(
            discovery.without_gt_config, 
            self.sample_config["discovery"]["without_ground_truth"]
        )
        self.assertEqual(
            discovery.with_gt_config, 
            self.sample_config["discovery"]["with_ground_truth"]
        )

    @patch('idp_common.discovery.classes_discovery.boto3.resource')
    @patch('idp_common.discovery.classes_discovery.bedrock.BedrockClient')
    def test_init_without_config_uses_defaults(self, mock_bedrock_client, mock_boto3_resource):
        """Test initialization without config uses default configuration."""
        # Setup mocks
        mock_table = Mock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        
        # Initialize without config
        discovery = ClassesDiscovery(
            input_bucket=self.test_bucket,
            input_prefix=self.test_prefix,
            region=self.test_region
        )
        
        # Verify default configuration is loaded
        self.assertIsNotNone(discovery.config)
        self.assertIn("discovery", discovery.config)
        self.assertIn("without_ground_truth", discovery.discovery_config)
        self.assertIn("with_ground_truth", discovery.discovery_config)
        self.assertIn("output_format", discovery.discovery_config)

    @patch('idp_common.discovery.classes_discovery.boto3.resource')
    @patch('idp_common.discovery.classes_discovery.bedrock.BedrockClient')
    def test_backward_compatibility_with_bedrock_model_id(self, mock_bedrock_client, mock_boto3_resource):
        """Test backward compatibility when bedrock_model_id is provided."""
        # Setup mocks
        mock_table = Mock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        
        test_model_id = "legacy-model-id"
        
        # Initialize with legacy bedrock_model_id parameter
        discovery = ClassesDiscovery(
            input_bucket=self.test_bucket,
            input_prefix=self.test_prefix,
            config=self.sample_config,
            bedrock_model_id=test_model_id,
            region=self.test_region
        )
        
        # Verify legacy model_id overrides config
        self.assertEqual(discovery.without_gt_config["model_id"], test_model_id)
        self.assertEqual(discovery.with_gt_config["model_id"], test_model_id)

    @patch('idp_common.discovery.classes_discovery.boto3.resource')
    @patch('idp_common.discovery.classes_discovery.bedrock.BedrockClient')
    @patch('idp_common.discovery.classes_discovery.bedrock.extract_text_from_response')
    @patch('idp_common.discovery.classes_discovery.S3Util.get_bytes')
    def test_extract_data_from_document_uses_config(
        self, mock_s3_get_bytes, mock_extract_text, mock_bedrock_client, mock_boto3_resource
    ):
        """Test that _extract_data_from_document uses configuration parameters."""
        # Setup mocks
        mock_table = Mock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        
        mock_bedrock_instance = Mock()
        mock_bedrock_client.return_value = mock_bedrock_instance
        
        mock_response = {"response": "test"}
        mock_bedrock_instance.invoke_model.return_value = mock_response
        
        test_response_text = '{"document_class": "TestDoc", "groups": []}'
        mock_extract_text.return_value = test_response_text
        
        # Initialize discovery with config
        discovery = ClassesDiscovery(
            input_bucket=self.test_bucket,
            input_prefix=self.test_prefix,
            config=self.sample_config,
            region=self.test_region
        )
        
        # Test document content
        test_content = b"test document content"
        test_extension = "pdf"
        
        # Call the method
        result = discovery._extract_data_from_document(test_content, test_extension)
        
        # Verify invoke_model was called with config parameters
        mock_bedrock_instance.invoke_model.assert_called_once()
        call_args = mock_bedrock_instance.invoke_model.call_args
        
        self.assertEqual(call_args[1]["model_id"], "test-model-without-gt")
        self.assertEqual(call_args[1]["system_prompt"], "Test system prompt without GT")
        self.assertEqual(call_args[1]["temperature"], 0.5)
        self.assertEqual(call_args[1]["top_p"], 0.2)
        self.assertEqual(call_args[1]["max_tokens"], 5000)
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result["document_class"], "TestDoc")

    @patch('idp_common.discovery.classes_discovery.boto3.resource')
    @patch('idp_common.discovery.classes_discovery.bedrock.BedrockClient')
    @patch('idp_common.discovery.classes_discovery.bedrock.extract_text_from_response')
    def test_extract_data_with_ground_truth_uses_config(
        self, mock_extract_text, mock_bedrock_client, mock_boto3_resource
    ):
        """Test that _extract_data_from_document_with_ground_truth uses configuration parameters."""
        # Setup mocks
        mock_table = Mock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        
        mock_bedrock_instance = Mock()
        mock_bedrock_client.return_value = mock_bedrock_instance
        
        mock_response = {"response": "test"}
        mock_bedrock_instance.invoke_model.return_value = mock_response
        
        test_response_text = '{"document_class": "TestDoc", "groups": []}'
        mock_extract_text.return_value = test_response_text
        
        # Initialize discovery with config
        discovery = ClassesDiscovery(
            input_bucket=self.test_bucket,
            input_prefix=self.test_prefix,
            config=self.sample_config,
            region=self.test_region
        )
        
        # Test document content
        test_content = b"test document content"
        test_extension = "pdf"
        
        # Call the method
        result = discovery._extract_data_from_document_with_ground_truth(
            test_content, test_extension, self.sample_ground_truth
        )
        
        # Verify invoke_model was called with config parameters
        mock_bedrock_instance.invoke_model.assert_called_once()
        call_args = mock_bedrock_instance.invoke_model.call_args
        
        self.assertEqual(call_args[1]["model_id"], "test-model-with-gt")
        self.assertEqual(call_args[1]["system_prompt"], "Test system prompt with GT")
        self.assertEqual(call_args[1]["temperature"], 0.7)
        self.assertEqual(call_args[1]["top_p"], 0.3)
        self.assertEqual(call_args[1]["max_tokens"], 7000)
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertEqual(result["document_class"], "TestDoc")

    @patch('idp_common.discovery.classes_discovery.boto3.resource')
    @patch('idp_common.discovery.classes_discovery.bedrock.BedrockClient')
    def test_ground_truth_prompt_placeholder_replacement(self, mock_bedrock_client, mock_boto3_resource):
        """Test that ground truth JSON is properly inserted into user prompt."""
        # Setup mocks
        mock_table = Mock()
        mock_boto3_resource.return_value.Table.return_table = mock_table
        
        # Initialize discovery with config
        discovery = ClassesDiscovery(
            input_bucket=self.test_bucket,
            input_prefix=self.test_prefix,
            config=self.sample_config,
            region=self.test_region
        )
        
        # Test ground truth data
        ground_truth_data = {"test": "data"}
        
        # Get the configured user prompt
        user_prompt = discovery.with_gt_config.get("user_prompt", "")
        
        # Verify placeholder exists
        self.assertIn("{ground_truth_json}", user_prompt)
        
        # Test placeholder replacement logic
        if "{ground_truth_json}" in user_prompt:
            ground_truth_json = json.dumps(ground_truth_data, indent=2)
            replaced_prompt = user_prompt.replace("{ground_truth_json}", ground_truth_json)
            
            # Verify replacement worked
            self.assertNotIn("{ground_truth_json}", replaced_prompt)
            self.assertIn('"test": "data"', replaced_prompt)

    @patch('idp_common.discovery.classes_discovery.boto3.resource')
    @patch('idp_common.discovery.classes_discovery.bedrock.BedrockClient')
    def test_default_config_structure(self, mock_bedrock_client, mock_boto3_resource):
        """Test that default configuration has the expected structure."""
        # Setup mocks
        mock_table = Mock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        
        # Initialize without config to get defaults
        discovery = ClassesDiscovery(
            input_bucket=self.test_bucket,
            input_prefix=self.test_prefix,
            region=self.test_region
        )
        
        # Verify default config structure
        self.assertIn("discovery", discovery.config)
        
        discovery_config = discovery.config["discovery"]
        self.assertIn("without_ground_truth", discovery_config)
        self.assertIn("with_ground_truth", discovery_config)
        self.assertIn("output_format", discovery_config)
        
        # Verify required fields in without_ground_truth config
        without_gt = discovery_config["without_ground_truth"]
        required_fields = ["model_id", "temperature", "top_p", "max_tokens", "system_prompt", "user_prompt"]
        for field in required_fields:
            self.assertIn(field, without_gt)
        
        # Verify required fields in with_ground_truth config
        with_gt = discovery_config["with_ground_truth"]
        for field in required_fields:
            self.assertIn(field, with_gt)
        
        # Verify output format
        self.assertIn("sample_json", discovery_config["output_format"])

    @patch('idp_common.discovery.classes_discovery.boto3.resource')
    @patch('idp_common.discovery.classes_discovery.bedrock.BedrockClient')
    @patch('idp_common.discovery.classes_discovery.bedrock.extract_text_from_response')
    def test_error_handling_in_extraction(self, mock_extract_text, mock_bedrock_client, mock_boto3_resource):
        """Test error handling in extraction methods."""
        # Setup mocks
        mock_table = Mock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        
        mock_bedrock_instance = Mock()
        mock_bedrock_client.return_value = mock_bedrock_instance
        
        # Make bedrock call raise an exception
        mock_bedrock_instance.invoke_model.side_effect = Exception("Bedrock error")
        
        # Initialize discovery
        discovery = ClassesDiscovery(
            input_bucket=self.test_bucket,
            input_prefix=self.test_prefix,
            config=self.sample_config,
            region=self.test_region
        )
        
        # Test document content
        test_content = b"test document content"
        test_extension = "pdf"
        
        # Call the method and verify it handles errors gracefully
        result = discovery._extract_data_from_document(test_content, test_extension)
        self.assertIsNone(result)
        
        # Test with ground truth
        result_gt = discovery._extract_data_from_document_with_ground_truth(
            test_content, test_extension, self.sample_ground_truth
        )
        self.assertIsNone(result_gt)


if __name__ == "__main__":
    unittest.main()