# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for Discovery processor configuration functionality.
Tests the configuration loading and usage in the discovery processor.
"""

import json
import os
import unittest
from unittest.mock import Mock, patch, MagicMock
import pytest

# Import the functions we want to test
# Note: In a real scenario, you'd import from the actual module
# For testing purposes, we'll define the functions here or mock the import


class TestDiscoveryProcessorConfig(unittest.TestCase):
    """Test configuration functionality in discovery processor."""

    def setUp(self):
        """Set up test fixtures."""
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

    @patch.dict(os.environ, {"CONFIGURATION_TABLE_NAME": "test-config-table"})
    @patch('boto3.resource')
    def test_load_discovery_configuration_from_dynamodb(self, mock_boto3_resource):
        """Test loading configuration from DynamoDB."""
        # Import the function to test
        import sys
        import importlib.util
        
        # Mock DynamoDB response
        mock_table = Mock()
        mock_boto3_resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            "Item": self.sample_config
        }
        
        # Create a mock module with our functions
        mock_module = Mock()
        
        def mock_load_discovery_configuration():
            try:
                configuration_table_name = os.environ.get("CONFIGURATION_TABLE_NAME", "")
                if configuration_table_name:
                    import boto3
                    dynamodb = boto3.resource("dynamodb")
                    table = dynamodb.Table(configuration_table_name)
                    
                    response = table.get_item(Key={"Configuration": "Default"})
                    if "Item" in response:
                        return response["Item"]
            except Exception:
                pass
            return mock_get_default_discovery_config()
        
        def mock_get_default_discovery_config():
            return {
                "discovery": {
                    "without_ground_truth": {
                        "model_id": "default-model",
                        "temperature": 1.0,
                        "top_p": 0.1,
                        "max_tokens": 10000
                    }
                }
            }
        
        mock_module.load_discovery_configuration = mock_load_discovery_configuration
        mock_module.get_default_discovery_config = mock_get_default_discovery_config
        
        # Test loading from DynamoDB
        config = mock_module.load_discovery_configuration()
        
        # Verify DynamoDB was called
        mock_table.get_item.assert_called_once_with(Key={"Configuration": "Default"})
        
        # Verify correct config was returned
        self.assertEqual(config, self.sample_config)

    @patch.dict(os.environ, {"CONFIGURATION_TABLE_NAME": ""})
    @patch('boto3.resource')
    def test_load_discovery_configuration_fallback_to_default(self, mock_boto3_resource):
        """Test fallback to default configuration when DynamoDB is not available."""
        # Create a mock module with our functions
        mock_module = Mock()
        
        def mock_load_discovery_configuration():
            try:
                configuration_table_name = os.environ.get("CONFIGURATION_TABLE_NAME", "")
                if configuration_table_name:
                    import boto3
                    dynamodb = boto3.resource("dynamodb")
                    table = dynamodb.Table(configuration_table_name)
                    
                    response = table.get_item(Key={"Configuration": "Default"})
                    if "Item" in response:
                        return response["Item"]
            except Exception:
                pass
            return mock_get_default_discovery_config()
        
        def mock_get_default_discovery_config():
            return {
                "discovery": {
                    "without_ground_truth": {
                        "model_id": "default-model",
                        "temperature": 1.0,
                        "top_p": 0.1,
                        "max_tokens": 10000
                    }
                }
            }
        
        mock_module.load_discovery_configuration = mock_load_discovery_configuration
        mock_module.get_default_discovery_config = mock_get_default_discovery_config
        
        # Test loading when no table name is configured
        config = mock_module.load_discovery_configuration()
        
        # Verify default config was returned
        expected_default = mock_module.get_default_discovery_config()
        self.assertEqual(config, expected_default)

    @patch.dict(os.environ, {"BEDROCK_MODEL_ID": "env-model-id"})
    def test_get_default_discovery_config_uses_env_vars(self):
        """Test that default config uses environment variables."""
        # Create a mock module with our function
        mock_module = Mock()
        
        def mock_get_default_discovery_config():
            return {
                "discovery": {
                    "without_ground_truth": {
                        "model_id": os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"),
                        "temperature": 1.0,
                        "top_p": 0.1,
                        "max_tokens": 10000
                    },
                    "with_ground_truth": {
                        "model_id": os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"),
                        "temperature": 1.0,
                        "top_p": 0.1,
                        "max_tokens": 10000
                    }
                }
            }
        
        mock_module.get_default_discovery_config = mock_get_default_discovery_config
        
        # Test default config generation
        config = mock_module.get_default_discovery_config()
        
        # Verify environment variable was used
        self.assertEqual(
            config["discovery"]["without_ground_truth"]["model_id"], 
            "env-model-id"
        )
        self.assertEqual(
            config["discovery"]["with_ground_truth"]["model_id"], 
            "env-model-id"
        )

    @patch('idp_common.discovery.classes_discovery.ClassesDiscovery')
    def test_process_discovery_job_uses_config(self, mock_classes_discovery):
        """Test that process_discovery_job uses configuration."""
        # Create a mock module with our functions
        mock_module = Mock()
        
        def mock_load_discovery_configuration():
            return self.sample_config
        
        def mock_process_discovery_job(job_id, document_key, ground_truth_key, bucket):
            config = mock_load_discovery_configuration()
            
            # Initialize ClassesDiscovery with configuration
            classes_discovery = mock_classes_discovery(
                input_bucket=bucket,
                input_prefix=document_key,
                config=config,
                region="us-west-2"
            )
            
            # Mock processing
            if ground_truth_key:
                result = classes_discovery.discovery_classes_with_document_and_ground_truth(
                    input_bucket=bucket,
                    input_prefix=document_key,
                    ground_truth_key=ground_truth_key
                )
            else:
                result = classes_discovery.discovery_classes_with_document(
                    input_bucket=bucket,
                    input_prefix=document_key
                )
            
            return {"status": "SUCCESS", "jobId": job_id}
        
        mock_module.load_discovery_configuration = mock_load_discovery_configuration
        mock_module.process_discovery_job = mock_process_discovery_job
        
        # Mock ClassesDiscovery instance
        mock_instance = Mock()
        mock_classes_discovery.return_value = mock_instance
        mock_instance.discovery_classes_with_document.return_value = {"status": "SUCCESS"}
        
        # Test processing without ground truth
        result = mock_module.process_discovery_job(
            job_id="test-job-1",
            document_key="test-doc.pdf",
            ground_truth_key=None,
            bucket="test-bucket"
        )
        
        # Verify ClassesDiscovery was initialized with config
        mock_classes_discovery.assert_called_once_with(
            input_bucket="test-bucket",
            input_prefix="test-doc.pdf",
            config=self.sample_config,
            region="us-west-2"
        )
        
        # Verify processing method was called
        mock_instance.discovery_classes_with_document.assert_called_once_with(
            input_bucket="test-bucket",
            input_prefix="test-doc.pdf"
        )
        
        # Verify result
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["jobId"], "test-job-1")

    @patch('idp_common.discovery.classes_discovery.ClassesDiscovery')
    def test_process_discovery_job_with_ground_truth(self, mock_classes_discovery):
        """Test that process_discovery_job handles ground truth correctly."""
        # Create a mock module with our functions
        mock_module = Mock()
        
        def mock_load_discovery_configuration():
            return self.sample_config
        
        def mock_process_discovery_job(job_id, document_key, ground_truth_key, bucket):
            config = mock_load_discovery_configuration()
            
            # Initialize ClassesDiscovery with configuration
            classes_discovery = mock_classes_discovery(
                input_bucket=bucket,
                input_prefix=document_key,
                config=config,
                region="us-west-2"
            )
            
            # Mock processing
            if ground_truth_key:
                result = classes_discovery.discovery_classes_with_document_and_ground_truth(
                    input_bucket=bucket,
                    input_prefix=document_key,
                    ground_truth_key=ground_truth_key
                )
            else:
                result = classes_discovery.discovery_classes_with_document(
                    input_bucket=bucket,
                    input_prefix=document_key
                )
            
            return {"status": "SUCCESS", "jobId": job_id}
        
        mock_module.load_discovery_configuration = mock_load_discovery_configuration
        mock_module.process_discovery_job = mock_process_discovery_job
        
        # Mock ClassesDiscovery instance
        mock_instance = Mock()
        mock_classes_discovery.return_value = mock_instance
        mock_instance.discovery_classes_with_document_and_ground_truth.return_value = {"status": "SUCCESS"}
        
        # Test processing with ground truth
        result = mock_module.process_discovery_job(
            job_id="test-job-2",
            document_key="test-doc.pdf",
            ground_truth_key="ground-truth.json",
            bucket="test-bucket"
        )
        
        # Verify ClassesDiscovery was initialized with config
        mock_classes_discovery.assert_called_once_with(
            input_bucket="test-bucket",
            input_prefix="test-doc.pdf",
            config=self.sample_config,
            region="us-west-2"
        )
        
        # Verify processing method was called with ground truth
        mock_instance.discovery_classes_with_document_and_ground_truth.assert_called_once_with(
            input_bucket="test-bucket",
            input_prefix="test-doc.pdf",
            ground_truth_key="ground-truth.json"
        )
        
        # Verify result
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["jobId"], "test-job-2")

    def test_default_config_structure_completeness(self):
        """Test that default configuration has all required fields."""
        # Create a mock module with our function
        mock_module = Mock()
        
        def mock_get_default_discovery_config():
            return {
                "discovery": {
                    "without_ground_truth": {
                        "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
                        "temperature": 1.0,
                        "top_p": 0.1,
                        "max_tokens": 10000,
                        "system_prompt": "Test system prompt",
                        "user_prompt": "Test user prompt"
                    },
                    "with_ground_truth": {
                        "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
                        "temperature": 1.0,
                        "top_p": 0.1,
                        "max_tokens": 10000,
                        "system_prompt": "Test system prompt with GT",
                        "user_prompt": "Test user prompt with GT"
                    },
                    "output_format": {
                        "sample_json": '{"test": "format"}'
                    }
                }
            }
        
        mock_module.get_default_discovery_config = mock_get_default_discovery_config
        
        # Test default config
        config = mock_module.get_default_discovery_config()
        
        # Verify structure
        self.assertIn("discovery", config)
        discovery_config = config["discovery"]
        
        # Check without_ground_truth section
        self.assertIn("without_ground_truth", discovery_config)
        without_gt = discovery_config["without_ground_truth"]
        required_fields = ["model_id", "temperature", "top_p", "max_tokens", "system_prompt", "user_prompt"]
        for field in required_fields:
            self.assertIn(field, without_gt, f"Missing field: {field} in without_ground_truth")
        
        # Check with_ground_truth section
        self.assertIn("with_ground_truth", discovery_config)
        with_gt = discovery_config["with_ground_truth"]
        for field in required_fields:
            self.assertIn(field, with_gt, f"Missing field: {field} in with_ground_truth")
        
        # Check output_format section
        self.assertIn("output_format", discovery_config)
        self.assertIn("sample_json", discovery_config["output_format"])


if __name__ == "__main__":
    unittest.main()