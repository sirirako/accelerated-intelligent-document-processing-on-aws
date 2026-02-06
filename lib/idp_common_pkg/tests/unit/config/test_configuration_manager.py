"""Tests for ConfigurationManager activate_version functionality."""

from unittest.mock import Mock, patch

import pytest
from idp_common.config.configuration_manager import ConfigurationManager
from idp_common.config.models import ConfigurationRecord


@pytest.mark.unit
class TestConfigurationManagerActivateVersion:
    """Test activate_version method."""

    @patch("idp_common.config.configuration_manager.boto3")
    def test_activate_version_success(self, mock_boto3):
        """Test successful version activation."""
        # Setup mocks
        mock_table = Mock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        manager = ConfigurationManager(table_name="test-table")

        # Mock existing records
        target_record = Mock(spec=ConfigurationRecord)
        target_record.is_active = False

        other_record = Mock(spec=ConfigurationRecord)
        other_record.is_active = True

        # Mock methods
        manager._read_record = Mock(
            side_effect=[
                target_record,  # Target version exists
                other_record,  # Other active version
            ]
        )
        manager._write_record = Mock()
        manager.list_config_versions = Mock(
            return_value=[{"versionName": "other-version"}]
        )

        # Execute
        manager.activate_version("test-version")

        # Verify
        assert target_record.is_active is True
        assert other_record.is_active is False
        assert manager._write_record.call_count == 2

    @patch("idp_common.config.configuration_manager.boto3")
    def test_activate_version_not_found(self, mock_boto3):
        """Test activation of non-existent version."""
        mock_table = Mock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        manager = ConfigurationManager(table_name="test-table")
        manager._read_record = Mock(return_value=None)

        with pytest.raises(ValueError, match="Config version test-version not found"):
            manager.activate_version("test-version")
