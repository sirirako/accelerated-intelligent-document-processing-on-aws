# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for the BdaBlueprintService class.
"""

# ruff: noqa: E402, I001
# The above line disables E402 (module level import not at top of file) and I001 (import block sorting) for this file

import pytest

# Import standard library modules first
import json
from copy import deepcopy
from unittest.mock import MagicMock, patch

# Import third-party modules
from botocore.exceptions import ClientError

# Import application modules
from idp_common.bda.bda_blueprint_service import BdaBlueprintService


def build_json_schema(
    doc_id="W-4",
    description="Employee's Withholding Certificate form",
    properties=None,
    defs=None,
):
    """Helper to construct JSON Schema documents for tests."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": doc_id,
        "x-aws-idp-document-type": doc_id,
        "description": description,
        "type": "object",
    }

    if properties is not None:
        schema["properties"] = properties
    if defs is not None:
        schema["$defs"] = defs

    return schema


@pytest.mark.unit
class TestBdaBlueprintService:
    """Tests for the BdaBlueprintService class."""

    @pytest.fixture
    def mock_custom_configuration(self):
        """Fixture providing mock custom configuration data."""
        w4_properties = {
            "personalInformation": {
                "type": "object",
                "description": "Personal information of employee",
                "properties": {
                    "firstName": {
                        "type": "string",
                        "description": "First Name of Employee",
                    },
                    "lastName": {
                        "type": "string",
                        "description": "Last Name of Employee",
                    },
                },
            }
        }

        i9_properties = {
            "employeeInfo": {
                "type": "object",
                "description": "Employee information section",
                "properties": {
                    "fullName": {
                        "type": "string",
                        "description": "Employee full name",
                    }
                },
            }
        }

        return {
            "Configuration": "Custom",
            "classes": [
                build_json_schema(
                    doc_id="W-4",
                    description="Employee's Withholding Certificate form",
                    properties=w4_properties,
                ),
                {
                    **build_json_schema(
                        doc_id="I-9",
                        description="Employment Eligibility Verification",
                        properties=i9_properties,
                    ),
                    "blueprint_arn": "arn:aws:bedrock:us-west-2:123456789012:blueprint/existing-i9-blueprint",
                },
            ],
        }

    @pytest.fixture
    def mock_blueprint_schema(self):
        """Fixture providing mock blueprint schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "description": "Employee's Withholding Certificate form",
            "class": "W-4",
            "type": "object",
            "definitions": {
                "PersonalInformation": {
                    "type": "object",
                    "properties": {
                        "firstname": {
                            "type": "string",
                            "instruction": "First Name of Employee",
                        },
                        "lastname": {
                            "type": "string",
                            "instruction": "Last Name of Employee",
                        },
                    },
                }
            },
            "properties": {
                "PersonalInformation": {"$ref": "#/definitions/PersonalInformation"}
            },
        }

    @pytest.fixture
    def mock_blueprint_response(self):
        """Fixture providing mock blueprint creation response."""
        return {
            "status": "success",
            "blueprint": {
                "blueprintArn": "arn:aws:bedrock:us-west-2:123456789012:blueprint/w4-12345678",
                "blueprintName": "W-4-12345678",
                "blueprintStage": "LIVE",
                "blueprintVersion": "1",
            },
        }

    @pytest.fixture
    def service(self):
        """Fixture providing a BdaBlueprintService instance with mocked dependencies."""
        with (
            patch("boto3.resource") as mock_dynamodb,
            patch("boto3.client") as mock_boto_client,
            patch(
                "idp_common.bda.bda_blueprint_service.ConfigurationManager"
            ) as mock_config_manager,
            patch.dict("os.environ", {"CONFIGURATION_TABLE_NAME": "test-config-table"}),
        ):
            # Mock DynamoDB table
            mock_table = MagicMock()
            mock_dynamodb.return_value.Table.return_value = mock_table

            # Mock boto3 client for BDABlueprintCreator
            mock_bedrock_client = MagicMock()
            mock_boto_client.return_value = mock_bedrock_client

            # Mock configuration manager
            mock_manager_instance = mock_config_manager.return_value
            mock_manager_instance.get_configuration.return_value = None
            mock_manager_instance.handle_update_custom_configuration.return_value = True

            service = BdaBlueprintService(
                dataAutomationProjectArn="arn:aws:bedrock:us-west-2:123456789012:project/test-project"
            )

            # Store mocks for access in tests
            # Note: Using setattr to avoid type checker issues with dynamic attributes
            setattr(service, "_mock_table", mock_table)
            service.config_manager = mock_manager_instance

            # Replace the blueprint_creator with a mock
            mock_blueprint_creator = MagicMock()
            service.blueprint_creator = mock_blueprint_creator
            setattr(service, "_mock_blueprint_creator", mock_blueprint_creator)

            return service

    def test_init(self):
        """Test initialization of BdaBlueprintService."""
        with (
            patch("boto3.resource") as mock_dynamodb,
            patch("boto3.client") as mock_boto_client,
            patch.dict(
                "os.environ",
                {
                    "CONFIGURATION_TABLE_NAME": "test-config-table",
                    "AWS_REGION": "us-east-1",
                },
            ),
        ):
            service = BdaBlueprintService(
                dataAutomationProjectArn="arn:aws:bedrock:us-west-2:123456789012:project/test-project"
            )

            assert (
                service.dataAutomationProjectArn
                == "arn:aws:bedrock:us-west-2:123456789012:project/test-project"
            )

            # Verify boto3 client was called for BDABlueprintCreator
            mock_boto_client.assert_called_with(service_name="bedrock-data-automation")

            # Verify DynamoDB table was set up
            mock_dynamodb.assert_called_once_with("dynamodb")

    def test_create_blueprints_from_custom_configuration_no_config(self, service):
        """Test handling when no custom configuration exists."""
        # Mock empty configuration retrieval
        service.config_manager.get_configuration.return_value = {
            "Configuration": "Custom",
            "classes": [],
        }

        # This should not raise an exception but should handle empty classes gracefully
        # Note: The current implementation has a bug with len(classess) < 0 which is never true
        # We'll test the actual behavior
        result = service.create_blueprints_from_custom_configuration()

        # Should complete without processing any classes
        assert result["status"] == "success"
        assert "No classes to process" in result["message"]
        service.blueprint_creator.create_blueprint.assert_not_called()
        service.blueprint_creator.update_blueprint.assert_not_called()

    def test_create_blueprints_from_custom_configuration_no_classes_key(self, service):
        """Test handling when configuration has no 'classes' key."""
        # Mock configuration without classes key
        service.config_manager.get_configuration.return_value = {
            "Configuration": "Custom"
        }

        # Should handle missing classes key gracefully
        result = service.create_blueprints_from_custom_configuration()

        assert result["status"] == "success"
        service.blueprint_creator.create_blueprint.assert_not_called()

    def test_create_blueprints_from_custom_configuration_dynamodb_error(self, service):
        """Test handling of DynamoDB error during configuration retrieval."""
        # Mock DynamoDB error
        error_response = {
            "Error": {"Code": "ResourceNotFoundException", "Message": "Table not found"}
        }
        service.config_manager.get_configuration.side_effect = ClientError(
            error_response, "GetItem"
        )

        # Should raise exception on DynamoDB error
        with pytest.raises(Exception, match="Failed to process blueprint creation"):
            service.create_blueprints_from_custom_configuration()

    def test_create_blueprints_from_custom_configuration_partial_failure(
        self, service, mock_custom_configuration
    ):
        """Test handling when one blueprint succeeds and another fails."""
        # Mock configuration retrieval - wrap dict in object with classes attribute
        config_obj = MagicMock()
        config_obj.classes = mock_custom_configuration["classes"]
        service.config_manager.get_configuration.return_value = config_obj

        # Mock first blueprint creation success, second failure
        success_response = {
            "status": "success",
            "blueprint": {
                "blueprintArn": "arn:aws:bedrock:us-west-2:123456789012:blueprint/w4-12345678",
                "blueprintName": "W-4-12345678",
            },
        }

        service.blueprint_creator.create_blueprint.return_value = success_response
        service.blueprint_creator.update_blueprint.side_effect = Exception(
            "Update failed"
        )
        service.blueprint_creator.create_blueprint_version.return_value = (
            success_response
        )

        # Should continue processing despite individual failures
        # The method should complete and update configuration with successful blueprints
        service.create_blueprints_from_custom_configuration()

        # Should still update configuration despite partial failure
        service.config_manager.handle_update_custom_configuration.assert_called_once()

    def test_check_for_updates_no_changes(self, service):
        """Test _check_for_updates when no changes are detected."""
        properties = {
            "personalInformation": {
                "type": "object",
                "description": "Personal info",
                "properties": {
                    "firstName": {
                        "type": "string",
                        "description": "First Name of Employee",
                    },
                    "lastName": {
                        "type": "string",
                        "description": "Last Name of Employee",
                    },
                },
            }
        }
        custom_class = build_json_schema(properties=properties)
        blueprint_schema = service._transform_json_schema_to_bedrock_blueprint(
            custom_class
        )
        existing_blueprint = {"schema": json.dumps(blueprint_schema)}

        assert service._check_for_updates(custom_class, existing_blueprint) is False

    def test_check_for_updates_class_id_changed(self, service):
        """Test _check_for_updates when the document class identifier changes."""
        base_schema = build_json_schema()
        blueprint_schema = service._transform_json_schema_to_bedrock_blueprint(
            base_schema
        )
        existing_blueprint = {"schema": json.dumps(blueprint_schema)}

        updated_schema = deepcopy(base_schema)
        updated_schema["$id"] = "W-4-Updated"
        updated_schema["x-aws-idp-document-type"] = "W-4-Updated"

        assert service._check_for_updates(updated_schema, existing_blueprint) is True

    def test_check_for_updates_description_changed(self, service):
        """Test _check_for_updates when the schema description change is detected."""
        base_schema = build_json_schema()
        blueprint_schema = service._transform_json_schema_to_bedrock_blueprint(
            base_schema
        )
        existing_blueprint = {"schema": json.dumps(blueprint_schema)}

        updated_schema = deepcopy(base_schema)
        updated_schema["description"] = (
            "Updated Employee's Withholding Certificate form"
        )

        assert service._check_for_updates(updated_schema, existing_blueprint) is True

    def test_check_for_updates_new_property_added(self, service):
        """Test _check_for_updates when a new top-level property is added."""
        base_schema = build_json_schema(properties={"foo": {"type": "string"}})
        blueprint_schema = service._transform_json_schema_to_bedrock_blueprint(
            base_schema
        )
        existing_blueprint = {"schema": json.dumps(blueprint_schema)}

        updated_schema = deepcopy(base_schema)
        # Type annotation to help type checker understand this is a dict
        updated_schema_dict = updated_schema  # type: dict
        updated_schema_dict["properties"]["bar"] = {
            "type": "string",
            "description": "New field",
        }

        assert (
            service._check_for_updates(updated_schema_dict, existing_blueprint) is True
        )

    def test_check_for_updates_nested_description_changed(self, service):
        """Test _check_for_updates when a nested description changes."""
        base_schema = build_json_schema(
            properties={
                "personalInformation": {
                    "type": "object",
                    "description": "Personal info",
                    "properties": {
                        "firstName": {
                            "type": "string",
                            "description": "First Name of Employee",
                        }
                    },
                }
            }
        )
        blueprint_schema = service._transform_json_schema_to_bedrock_blueprint(
            base_schema
        )
        existing_blueprint = {"schema": json.dumps(blueprint_schema)}

        updated_schema = deepcopy(base_schema)
        # Type annotation to help type checker understand this is a dict
        updated_schema_dict = updated_schema  # type: dict
        updated_schema_dict["properties"]["personalInformation"]["properties"][
            "firstName"
        ]["description"] = "Updated first name description"

        assert (
            service._check_for_updates(updated_schema_dict, existing_blueprint) is True
        )

    def test_check_for_updates_nested_property_added(self, service):
        """Test _check_for_updates when a nested property is added."""
        base_schema = build_json_schema(
            properties={
                "personalInformation": {
                    "type": "object",
                    "description": "Personal info",
                    "properties": {
                        "firstName": {
                            "type": "string",
                            "description": "First Name of Employee",
                        }
                    },
                }
            }
        )
        blueprint_schema = service._transform_json_schema_to_bedrock_blueprint(
            base_schema
        )
        existing_blueprint = {"schema": json.dumps(blueprint_schema)}

        updated_schema = deepcopy(base_schema)
        # Type annotation to help type checker understand this is a dict
        updated_schema_dict = updated_schema  # type: dict
        updated_schema_dict["properties"]["personalInformation"]["properties"][
            "middleName"
        ] = {
            "type": "string",
            "description": "Middle Name of Employee",
        }

        assert (
            service._check_for_updates(updated_schema_dict, existing_blueprint) is True
        )

    def test_check_for_updates_blueprint_retrieval_error(self, service):
        """Test _check_for_updates when blueprint has invalid schema."""
        custom_class = build_json_schema()

        # Invalid blueprint with malformed schema
        invalid_blueprint = {"schema": "invalid json"}

        # Should raise the exception
        with pytest.raises(json.JSONDecodeError):
            service._check_for_updates(custom_class, invalid_blueprint)

    def test_check_for_updates_empty_properties(self, service):
        """Test _check_for_updates with empty properties."""
        custom_class = build_json_schema(
            properties={}, description="Employee's Withholding Certificate form"
        )
        blueprint_schema = service._transform_json_schema_to_bedrock_blueprint(
            custom_class
        )
        existing_blueprint = {"schema": json.dumps(blueprint_schema)}

        assert service._check_for_updates(custom_class, existing_blueprint) is False

    def test_check_for_updates_without_properties_key(self, service):
        """Test _check_for_updates when properties key is absent."""
        custom_class = build_json_schema()
        custom_class.pop("properties", None)
        blueprint_schema = service._transform_json_schema_to_bedrock_blueprint(
            build_json_schema()
        )
        existing_blueprint = {"schema": json.dumps(blueprint_schema)}

        assert service._check_for_updates(custom_class, existing_blueprint) is False

    def test_transform_does_not_mutate_input_schema(self, service):
        """_transform_json_schema_to_bedrock_blueprint should not mutate the original schema."""
        schema = build_json_schema(
            doc_id="Invoice",
            description="Invoice schema",
            properties={
                "invoiceNumber": {
                    "type": "string",
                    "description": "Unique invoice identifier",
                }
            },
        )

        original = deepcopy(schema)

        blueprint = service._transform_json_schema_to_bedrock_blueprint(schema)

        # Original schema should remain untouched
        assert schema == original
        # Blueprint should contain Bedrock fields
        assert (
            blueprint["properties"]["invoiceNumber"]["instruction"]
            == "Unique invoice identifier"
        )
        assert blueprint["properties"]["invoiceNumber"]["inferenceType"] == "explicit"

    def test_transform_converts_defs_to_definitions(self, service):
        """Ensure that $defs is converted to definitions for BDA draft-07 compatibility.

        BDA uses JSON Schema draft-07 which uses "definitions", not "$defs".
        References should be preserved but updated to #/definitions/ path.
        """
        schema = build_json_schema(
            doc_id="Document",
            description="Document schema",
            properties={
                "address": {
                    "$ref": "#/$defs/Address",
                }
            },
            defs={
                "Address": {
                    "type": "object",
                    "description": "Address information",
                    "properties": {
                        "street": {
                            "type": "string",
                            "description": "Street line",
                        },
                        "city": {
                            "type": "string",
                            "description": "City name",
                        },
                    },
                }
            },
        )

        blueprint = service._transform_json_schema_to_bedrock_blueprint(schema)

        # Verify $defs was converted to definitions
        assert "definitions" in blueprint
        assert "$defs" not in blueprint
        assert "Address" in blueprint["definitions"]

        # Verify $ref path was updated
        address_prop = blueprint["properties"]["address"]
        assert address_prop["$ref"] == "#/definitions/Address"
        assert (
            address_prop["instruction"] == "-"
        )  # $ref properties should have instruction: "-"

        # Verify definition has proper structure (object should NOT have inferenceType/instruction)
        address_def = blueprint["definitions"]["Address"]
        assert address_def["type"] == "object"
        assert "inferenceType" not in address_def  # Objects should not have this
        assert "instruction" not in address_def  # Objects should not have this
        assert "properties" in address_def

        # Verify leaf properties DO have BDA fields
        street_prop = address_def["properties"]["street"]
        assert street_prop["type"] == "string"
        assert "inferenceType" in street_prop
        assert "instruction" in street_prop
        assert street_prop["instruction"] == "Street line"

        city_prop = address_def["properties"]["city"]
        assert city_prop["type"] == "string"
        assert "inferenceType" in city_prop
        assert "instruction" in city_prop

    def test_create_blueprints_creates_idp_classes_from_orphaned_bda_blueprints(
        self, service
    ):
        """Test that IDP classes are created for BDA blueprints without corresponding IDP classes.

        This test covers the scenario where:
        1. BDA blueprints exist in the project
        2. Some blueprints don't have corresponding IDP document classes
        3. The method should create IDP class schemas from those orphaned blueprints
        4. The new IDP classes should be added to the configuration
        """
        # Mock existing configuration with only one IDP class
        existing_idp_classes = [
            build_json_schema(
                doc_id="W-4",
                description="Employee's Withholding Certificate form",
                properties={
                    "personalInformation": {
                        "type": "object",
                        "description": "Personal information of employee",
                        "properties": {
                            "firstName": {
                                "type": "string",
                                "description": "First Name of Employee",
                            },
                            "lastName": {
                                "type": "string",
                                "description": "Last Name of Employee",
                            },
                        },
                    }
                },
            )
        ]

        # Mock configuration manager to return existing classes
        config_obj = MagicMock()
        config_obj.classes = existing_idp_classes
        service.config_manager.get_configuration.return_value = config_obj

        # Mock existing BDA blueprints - some have corresponding IDP classes, some don't
        existing_bda_blueprints = [
            # This blueprint has a corresponding IDP class (W-4)
            {
                "blueprintArn": "arn:aws:bedrock:us-west-2:123456789012:blueprint/test-stack-W-4-12345678",
                "blueprintName": "test-stack-W-4-12345678",
                "blueprintVersion": "1",
                "schema": json.dumps(
                    {
                        "$schema": "http://json-schema.org/draft-07/schema#",
                        "class": "W-4",
                        "description": "Employee's Withholding Certificate form",
                        "type": "object",
                        "definitions": {
                            "PersonalInformation": {
                                "type": "object",
                                "properties": {
                                    "firstName": {
                                        "type": "string",
                                        "inferenceType": "explicit",
                                        "instruction": "First Name of Employee",
                                    },
                                    "lastName": {
                                        "type": "string",
                                        "inferenceType": "explicit",
                                        "instruction": "Last Name of Employee",
                                    },
                                },
                            }
                        },
                        "properties": {
                            "personalInformation": {
                                "$ref": "#/definitions/PersonalInformation"
                            }
                        },
                    }
                ),
            },
            # This blueprint does NOT have a corresponding IDP class (I-9)
            {
                "blueprintArn": "arn:aws:bedrock:us-west-2:123456789012:blueprint/test-stack-I-9-87654321",
                "blueprintName": "test-stack-I-9-87654321",
                "blueprintVersion": "1",
                "schema": json.dumps(
                    {
                        "$schema": "http://json-schema.org/draft-07/schema#",
                        "class": "I-9",
                        "description": "Employment Eligibility Verification",
                        "type": "object",
                        "definitions": {
                            "EmployeeInfo": {
                                "type": "object",
                                "properties": {
                                    "fullName": {
                                        "type": "string",
                                        "inferenceType": "explicit",
                                        "instruction": "Employee full name",
                                    },
                                    "dateOfBirth": {
                                        "type": "string",
                                        "inferenceType": "explicit",
                                        "instruction": "Employee date of birth",
                                    },
                                },
                            }
                        },
                        "properties": {
                            "employeeInfo": {"$ref": "#/definitions/EmployeeInfo"}
                        },
                    }
                ),
            },
            # This blueprint also does NOT have a corresponding IDP class (1099)
            {
                "blueprintArn": "arn:aws:bedrock:us-west-2:123456789012:blueprint/test-stack-1099-11111111",
                "blueprintName": "test-stack-1099-11111111",
                "blueprintVersion": "1",
                "schema": json.dumps(
                    {
                        "$schema": "http://json-schema.org/draft-07/schema#",
                        "class": "1099",
                        "description": "Miscellaneous Income Tax Form",
                        "type": "object",
                        "properties": {
                            "payerInfo": {
                                "type": "string",
                                "inferenceType": "explicit",
                                "instruction": "Payer information",
                            },
                            "recipientInfo": {
                                "type": "string",
                                "inferenceType": "explicit",
                                "instruction": "Recipient information",
                            },
                        },
                    }
                ),
            },
        ]

        # Mock the _retrieve_all_blueprints method
        service._retrieve_all_blueprints = MagicMock(
            return_value=existing_bda_blueprints
        )

        # Mock blueprint operations for the existing W-4 class
        service.blueprint_creator.create_blueprint.return_value = {
            "status": "success",
            "blueprint": {
                "blueprintArn": "arn:aws:bedrock:us-west-2:123456789012:blueprint/test-stack-W-4-12345678",
                "blueprintName": "test-stack-W-4-12345678",
            },
        }
        service.blueprint_creator.create_blueprint_version.return_value = {
            "status": "success"
        }
        service.blueprint_creator.update_blueprint.return_value = {"status": "success"}

        # Mock the _check_for_updates to return False (no updates needed)
        service._check_for_updates = MagicMock(return_value=False)

        # Mock the _blueprint_lookup method
        def mock_blueprint_lookup(existing_blueprints, doc_class):
            for blueprint in existing_blueprints:
                blueprint_name = blueprint.get("blueprintName", "")
                if doc_class in blueprint_name:
                    return blueprint
            return None

        service._blueprint_lookup = MagicMock(side_effect=mock_blueprint_lookup)

        # Execute the method
        result = service.create_blueprints_from_custom_configuration()

        # Verify the result
        assert isinstance(result, list)
        assert (
            len(result) == 3
        )  # All classes processed: 1 existing (W-4) + 2 orphaned (I-9, 1099)

        # Verify that handle_update_custom_configuration was called with new classes
        service.config_manager.handle_update_custom_configuration.assert_called_once()

        # Get the call arguments to verify the new classes were added
        call_args = service.config_manager.handle_update_custom_configuration.call_args[
            0
        ][0]
        updated_classes = call_args["classes"]

        # Should have 3 classes total: 1 original + 2 new from orphaned blueprints
        assert len(updated_classes) == 3

        # Verify the original W-4 class is still there
        w4_class = next(
            (cls for cls in updated_classes if cls.get("$id") == "W-4"), None
        )
        assert w4_class is not None
        assert w4_class["description"] == "Employee's Withholding Certificate form"

        # Verify the new I-9 class was created from the BDA blueprint
        i9_class = next(
            (cls for cls in updated_classes if cls.get("$id") == "I-9"), None
        )
        assert i9_class is not None
        assert i9_class["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert i9_class["x-aws-idp-document-type"] == "I-9"
        assert i9_class["description"] == "Employment Eligibility Verification"
        assert i9_class["type"] == "object"

        # Verify I-9 has proper $defs (converted from definitions)
        assert "$defs" in i9_class
        assert "EmployeeInfo" in i9_class["$defs"]

        # Verify I-9 properties have proper $ref paths (converted from #/definitions/ to #/$defs/)
        assert i9_class["properties"]["employeeInfo"]["$ref"] == "#/$defs/EmployeeInfo"

        # Verify I-9 definition properties have descriptions (converted from instruction)
        employee_info_def = i9_class["$defs"]["EmployeeInfo"]
        assert (
            employee_info_def["properties"]["fullName"]["description"]
            == "Employee full name"
        )
        assert (
            employee_info_def["properties"]["dateOfBirth"]["description"]
            == "Employee date of birth"
        )

        # Verify BDA-specific fields were removed
        assert "inferenceType" not in employee_info_def["properties"]["fullName"]
        assert "instruction" not in employee_info_def["properties"]["fullName"]

        # Verify the new 1099 class was created from the BDA blueprint
        form1099_class = next(
            (cls for cls in updated_classes if cls.get("$id") == "1099"), None
        )
        assert form1099_class is not None
        assert (
            form1099_class["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        )
        assert form1099_class["x-aws-idp-document-type"] == "1099"
        assert form1099_class["description"] == "Miscellaneous Income Tax Form"

        # Verify 1099 properties (flat structure, no definitions)
        assert "payerInfo" in form1099_class["properties"]
        assert "recipientInfo" in form1099_class["properties"]
        assert (
            form1099_class["properties"]["payerInfo"]["description"]
            == "Payer information"
        )
        assert (
            form1099_class["properties"]["recipientInfo"]["description"]
            == "Recipient information"
        )

        # Verify BDA-specific fields were removed from 1099 properties
        assert "inferenceType" not in form1099_class["properties"]["payerInfo"]
        assert "instruction" not in form1099_class["properties"]["payerInfo"]

    def test_create_blueprints_no_orphaned_blueprints(self, service):
        """Test that no IDP classes are created when all BDA blueprints have corresponding IDP classes."""
        # Mock existing configuration with IDP classes that match all blueprints
        existing_idp_classes = [
            build_json_schema(doc_id="W-4", description="W-4 form"),
            build_json_schema(doc_id="I-9", description="I-9 form"),
        ]

        config_obj = MagicMock()
        config_obj.classes = existing_idp_classes
        service.config_manager.get_configuration.return_value = config_obj

        # Mock existing BDA blueprints that all have corresponding IDP classes
        existing_bda_blueprints = [
            {
                "blueprintArn": "arn:aws:bedrock:us-west-2:123456789012:blueprint/test-stack-W-4-12345678",
                "blueprintName": "test-stack-W-4-12345678",
                "blueprintVersion": "1",
                "schema": json.dumps({"class": "W-4", "type": "object"}),
            },
            {
                "blueprintArn": "arn:aws:bedrock:us-west-2:123456789012:blueprint/test-stack-I-9-87654321",
                "blueprintName": "test-stack-I-9-87654321",
                "blueprintVersion": "1",
                "schema": json.dumps({"class": "I-9", "type": "object"}),
            },
        ]

        service._retrieve_all_blueprints = MagicMock(
            return_value=existing_bda_blueprints
        )
        service._check_for_updates = MagicMock(return_value=False)

        def mock_blueprint_lookup(existing_blueprints, doc_class):
            for blueprint in existing_blueprints:
                blueprint_name = blueprint.get("blueprintName", "")
                if doc_class in blueprint_name:
                    return blueprint
            return None

        service._blueprint_lookup = MagicMock(side_effect=mock_blueprint_lookup)

        # Execute the method
        service.create_blueprints_from_custom_configuration()

        # Verify that handle_update_custom_configuration was called
        service.config_manager.handle_update_custom_configuration.assert_called_once()

        # Get the call arguments to verify no new classes were added
        call_args = service.config_manager.handle_update_custom_configuration.call_args[
            0
        ][0]
        updated_classes = call_args["classes"]

        # Should still have only the original 2 classes (no new ones added)
        assert len(updated_classes) == 2
        assert any(cls.get("$id") == "W-4" for cls in updated_classes)
        assert any(cls.get("$id") == "I-9" for cls in updated_classes)

    def test_create_blueprints_empty_existing_blueprints(self, service):
        """Test behavior when no BDA blueprints exist in the project."""
        # Mock existing configuration with IDP classes
        existing_idp_classes = [
            build_json_schema(doc_id="W-4", description="W-4 form"),
        ]

        config_obj = MagicMock()
        config_obj.classes = existing_idp_classes
        service.config_manager.get_configuration.return_value = config_obj

        # Mock empty blueprints list
        service._retrieve_all_blueprints = MagicMock(return_value=[])

        # Mock blueprint operations
        service.blueprint_creator.create_blueprint.return_value = {
            "status": "success",
            "blueprint": {
                "blueprintArn": "arn:aws:bedrock:us-west-2:123456789012:blueprint/new-w4",
                "blueprintName": "new-w4",
            },
        }
        service.blueprint_creator.create_blueprint_version.return_value = {
            "status": "success"
        }

        # Execute the method
        service.create_blueprints_from_custom_configuration()

        # Verify that handle_update_custom_configuration was called
        service.config_manager.handle_update_custom_configuration.assert_called_once()

        # Get the call arguments to verify no new classes were added (since no orphaned blueprints)
        call_args = service.config_manager.handle_update_custom_configuration.call_args[
            0
        ][0]
        updated_classes = call_args["classes"]

        # Should still have only the original 1 class (no new ones added from blueprints)
        assert len(updated_classes) == 1
        assert updated_classes[0].get("$id") == "W-4"
