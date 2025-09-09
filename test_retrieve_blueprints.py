#!/usr/bin/env python3
"""
Test script to verify the _retrieve_all_blueprints method implementation.
"""

import sys
import os
from unittest.mock import Mock, patch, MagicMock

# Add the path to the idp_common package
sys.path.insert(0, 'lib/idp_common_pkg')

def test_retrieve_all_blueprints():
    """Test the _retrieve_all_blueprints method."""
    
    # Mock environment variables
    with patch.dict(os.environ, {
        'CONFIGURATION_TABLE_NAME': 'test-config-table',
        'STACK_NAME': 'test-stack',
        'AWS_REGION': 'us-west-2'
    }):
        
        # Mock boto3 resources and clients
        with patch('boto3.resource') as mock_resource, \
             patch('boto3.client') as mock_client:
            
            # Mock DynamoDB table
            mock_table = Mock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock Bedrock client
            mock_bedrock_client = Mock()
            
            # Mock project response
            mock_project_response = {
                'project': {
                    'customOutputConfiguration': {
                        'blueprints': [
                            {
                                'blueprintArn': 'arn:aws:bedrock:us-west-2:123456789012:blueprint/test-blueprint-1',
                                'blueprintStage': 'LIVE',
                                'blueprintVersion': '1'
                            },
                            {
                                'blueprintArn': 'arn:aws:bedrock:us-west-2:123456789012:blueprint/test-blueprint-2',
                                'blueprintStage': 'LIVE'
                            }
                        ]
                    }
                }
            }
            
            # Mock blueprint responses
            mock_blueprint_1 = {
                'blueprint': {
                    'blueprintName': 'test-stack-Document1-abc123',
                    'blueprintArn': 'arn:aws:bedrock:us-west-2:123456789012:blueprint/test-blueprint-1'
                }
            }
            
            mock_blueprint_2 = {
                'blueprint': {
                    'blueprintName': 'test-stack-Document2-def456',
                    'blueprintArn': 'arn:aws:bedrock:us-west-2:123456789012:blueprint/test-blueprint-2'
                }
            }
            
            # Configure mock responses
            mock_bedrock_client.get_data_automation_project.return_value = mock_project_response
            mock_bedrock_client.get_blueprint.side_effect = [mock_blueprint_1, mock_blueprint_2]
            
            # Import and create service instance
            from idp_common.bda.bda_blueprint_service import BdaBlueprintService
            
            # Mock the blueprint_creator's bedrock_client
            with patch('idp_common.bda.bda_blueprint_creator.BDABlueprintCreator') as mock_creator_class:
                mock_creator = Mock()
                mock_creator.bedrock_client = mock_bedrock_client
                mock_creator_class.return_value = mock_creator
                
                # Create service instance
                service = BdaBlueprintService(
                    dataAutomationProjectArn='arn:aws:bedrock:us-west-2:123456789012:project/test-project',
                    region='us-west-2'
                )
                
                # Test the method
                result = service._retrieve_all_blueprints('arn:aws:bedrock:us-west-2:123456789012:project/test-project')
                
                # Verify results
                assert len(result) == 2, f"Expected 2 blueprints, got {len(result)}"
                
                # Check first blueprint
                bp1 = result[0]
                assert bp1['blueprintArn'] == 'arn:aws:bedrock:us-west-2:123456789012:blueprint/test-blueprint-1'
                assert bp1['blueprintName'] == 'test-stack-Document1-abc123'
                assert bp1['blueprintStage'] == 'LIVE'
                assert bp1['blueprintVersion'] == '1'
                
                # Check second blueprint
                bp2 = result[1]
                assert bp2['blueprintArn'] == 'arn:aws:bedrock:us-west-2:123456789012:blueprint/test-blueprint-2'
                assert bp2['blueprintName'] == 'test-stack-Document2-def456'
                assert bp2['blueprintStage'] == 'LIVE'
                assert bp2['blueprintVersion'] is None
                
                print("✓ _retrieve_all_blueprints with project ARN test passed")

def test_retrieve_blueprints_no_project():
    """Test _retrieve_all_blueprints without project ARN (fallback to list all)."""
    
    with patch.dict(os.environ, {
        'CONFIGURATION_TABLE_NAME': 'test-config-table',
        'STACK_NAME': 'test-stack',
        'AWS_REGION': 'us-west-2'
    }):
        
        with patch('boto3.resource') as mock_resource, \
             patch('boto3.client') as mock_client:
            
            mock_table = Mock()
            mock_resource.return_value.Table.return_value = mock_table
            
            mock_bedrock_client = Mock()
            
            # Mock paginator for list_blueprints
            mock_paginator = Mock()
            mock_page_iterator = [
                {
                    'blueprints': [
                        {
                            'blueprintArn': 'arn:aws:bedrock:us-west-2:123456789012:blueprint/bp1',
                            'blueprintName': 'blueprint-1',
                            'blueprintStage': 'LIVE'
                        }
                    ]
                },
                {
                    'blueprints': [
                        {
                            'blueprintArn': 'arn:aws:bedrock:us-west-2:123456789012:blueprint/bp2',
                            'blueprintName': 'blueprint-2',
                            'blueprintStage': 'LIVE'
                        }
                    ]
                }
            ]
            
            mock_paginator.paginate.return_value = mock_page_iterator
            mock_bedrock_client.get_paginator.return_value = mock_paginator
            
            from idp_common.bda.bda_blueprint_service import BdaBlueprintService
            
            with patch('idp_common.bda.bda_blueprint_creator.BDABlueprintCreator') as mock_creator_class:
                mock_creator = Mock()
                mock_creator.bedrock_client = mock_bedrock_client
                mock_creator_class.return_value = mock_creator
                
                service = BdaBlueprintService(region='us-west-2')
                
                # Test without project ARN
                result = service._retrieve_all_blueprints()
                
                assert len(result) == 2, f"Expected 2 blueprints, got {len(result)}"
                assert result[0]['blueprintName'] == 'blueprint-1'
                assert result[1]['blueprintName'] == 'blueprint-2'
                
                print("✓ _retrieve_all_blueprints without project ARN test passed")

def test_retrieve_blueprints_error_handling():
    """Test error handling in _retrieve_all_blueprints."""
    
    with patch.dict(os.environ, {
        'CONFIGURATION_TABLE_NAME': 'test-config-table',
        'STACK_NAME': 'test-stack',
        'AWS_REGION': 'us-west-2'
    }):
        
        with patch('boto3.resource') as mock_resource:
            
            mock_table = Mock()
            mock_resource.return_value.Table.return_value = mock_table
            
            from idp_common.bda.bda_blueprint_service import BdaBlueprintService
            
            with patch('idp_common.bda.bda_blueprint_creator.BDABlueprintCreator') as mock_creator_class:
                mock_creator = Mock()
                # Simulate client error
                from botocore.exceptions import ClientError
                mock_creator.bedrock_client.get_data_automation_project.side_effect = ClientError(
                    {'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
                    'GetDataAutomationProject'
                )
                mock_creator.bedrock_client.get_paginator.side_effect = ClientError(
                    {'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
                    'ListBlueprints'
                )
                mock_creator_class.return_value = mock_creator
                
                service = BdaBlueprintService(region='us-west-2')
                
                # Should return empty list on error
                result = service._retrieve_all_blueprints('arn:aws:bedrock:us-west-2:123456789012:project/test')
                
                assert result == [], f"Expected empty list on error, got {result}"
                
                print("✓ Error handling test passed")

if __name__ == '__main__':
    print("Testing _retrieve_all_blueprints implementation...")
    
    try:
        test_retrieve_all_blueprints()
        test_retrieve_blueprints_no_project()
        test_retrieve_blueprints_error_handling()
        
        print("\n🎉 All tests passed! _retrieve_all_blueprints implementation is working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)