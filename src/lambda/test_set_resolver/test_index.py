import pytest
from unittest.mock import Mock, patch
import os

# Mock environment variables and boto3 before importing
with patch.dict(os.environ, {'TRACKING_TABLE': 'test-table', 'INPUT_BUCKET': 'test-bucket', 'AWS_REGION': 'us-east-1'}):
    with patch('boto3.resource'):
        import index


@pytest.mark.unit
class TestTestSetResolver:
    
    def test_handler_field_routing(self):
        """Test that handler routes to correct functions"""
        with patch('index.add_test_set') as mock_add:
            mock_add.return_value = {'id': 'test'}
            event = {'info': {'fieldName': 'addTestSet'}, 'arguments': {}}
            result = index.handler(event, {})
            mock_add.assert_called_once()
            
        with patch('index.get_test_sets') as mock_get:
            mock_get.return_value = []
            event = {'info': {'fieldName': 'getTestSets'}}
            result = index.handler(event, {})
            mock_get.assert_called_once()

    def test_handler_unknown_field(self):
        """Test handler with unknown field"""
        event = {'info': {'fieldName': 'unknown'}, 'arguments': {}}
        with pytest.raises(Exception, match='Unknown field: unknown'):
            index.handler(event, {})

    @patch('uuid.uuid4')
    @patch('datetime.datetime')
    def test_add_test_set_structure(self, mock_datetime, mock_uuid):
        """Test add_test_set returns correct structure"""
        mock_uuid.return_value = 'test-id'
        mock_datetime.utcnow.return_value.isoformat.return_value = '2025-10-17T16:00:00'
        
        with patch.object(index.db_client, 'put_item') as mock_put:
            args = {'name': 'test', 'filePattern': '*.pdf', 'fileCount': 5}
            result = index.add_test_set(args)
            
            mock_put.assert_called_once()
            assert result['id'] == 'test-id'
            assert result['name'] == 'test'
            assert result['filePattern'] == '*.pdf'
            assert result['fileCount'] == 5
            assert 'createdAt' in result

    def test_delete_test_sets_calls_client(self):
        """Test delete_test_sets uses DynamoDB client"""
        with patch.object(index.db_client, 'delete_item') as mock_delete:
            args = {'testSetIds': ['id1', 'id2']}
            result = index.delete_test_sets(args)
            
            assert mock_delete.call_count == 2
            assert result is True

    def test_get_test_sets_uses_scan_all(self):
        """Test get_test_sets uses scan_all method"""
        with patch.object(index.db_client, 'scan_all') as mock_scan:
            mock_scan.return_value = [{
                'id': 'test-id',
                'name': 'test-name',
                'filePattern': '*.pdf',
                'fileCount': 5,
                'createdAt': '2025-10-17T16:00:00Z'
            }]
            
            result = index.get_test_sets()
            
            mock_scan.assert_called_once()
            assert len(result) == 1
            assert result[0]['id'] == 'test-id'

    @patch('index.find_matching_files')
    @patch.dict('os.environ', {'INPUT_BUCKET': 'test-bucket'})
    def test_list_input_bucket_files(self, mock_find):
        """Test list_input_bucket_files calls find_matching_files"""
        mock_find.return_value = ['file1.pdf', 'file2.pdf']
        
        args = {'filePattern': '*.pdf'}
        result = index.list_input_bucket_files(args)
        
        mock_find.assert_called_once_with('test-bucket', '*.pdf', root_only=True)
        assert result == ['file1.pdf', 'file2.pdf']
