# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import json
import logging
import os
import uuid
from copy import deepcopy
from typing import Optional

from botocore.exceptions import ClientError
from deepdiff import DeepDiff

from idp_common.bda.bda_blueprint_creator import BDABlueprintCreator
from idp_common.config.configuration_manager import ConfigurationManager
from idp_common.config.schema_constants import (
    DEFS_FIELD,
    ID_FIELD,
    REF_FIELD,
    SCHEMA_DESCRIPTION,
    SCHEMA_ITEMS,
    SCHEMA_PROPERTIES,
    SCHEMA_TYPE,
    TYPE_ARRAY,
    TYPE_OBJECT,
    X_AWS_IDP_DOCUMENT_TYPE,
)

logger = logging.getLogger(__name__)


class BdaBlueprintService:
    def __init__(self, dataAutomationProjectArn: Optional[str] = None):
        self.dataAutomationProjectArn = dataAutomationProjectArn
        self.blueprint_creator = BDABlueprintCreator()
        self.blueprint_name_prefix = os.environ.get("STACK_NAME", "")
        self.config_manager = ConfigurationManager()

        return

    def _retrieve_all_blueprints(self, project_arn: str):
        """
        Retrieve all blueprints from the Bedrock Data Automation service.
        If project_arn is provided, retrieves blueprints associated with that project.

        Args:
            project_arn (Optional[str]): ARN of the data automation project to filter blueprints

        Returns:
            list: List of blueprint names and ARNs
        """
        try:
            all_blueprints = []

            # If project ARN is provided, get blueprints from the project
            if project_arn:
                try:
                    blueprint_response = self.blueprint_creator.list_blueprints(
                        projectArn=project_arn, projectStage="LIVE"
                    )

                    blueprints = blueprint_response.get("blueprints", [])
                    for blueprint in blueprints:
                        blueprint_arn = blueprint.get("blueprintArn", None)
                        if "aws:blueprint" in blueprint_arn:
                            continue
                        response = self.blueprint_creator.get_blueprint(
                            blueprint_arn=blueprint_arn, stage="LIVE"
                        )
                        _blueprint = response.get("blueprint")
                        # Add blueprintVersion with default if missing
                        _blueprint["blueprintVersion"] = blueprint.get(
                            "blueprintVersion", "1"
                        )
                        all_blueprints.append(_blueprint)
                    logger.info(
                        f"{len(all_blueprints)} blueprints retrieved for {project_arn}"
                    )
                    logger.info(
                        f"blueprints retrieved {json.dumps(all_blueprints, default=str)}"
                    )
                    return all_blueprints

                except ClientError as e:
                    logger.warning(f"Could not retrieve project {project_arn}: {e}")
                    # Fall through to list all blueprints
                    return []

        except Exception as e:
            logger.error(f"Error retrieving blueprints: {e}")
            return []

    def _transform_json_schema_to_bedrock_blueprint(self, json_schema: dict) -> dict:
        """
        Transform JSON Schema (draft 2020-12) to BDA blueprint format (draft-07).

        Handles two input patterns:
        1. Schemas with $defs (from migration.py)
        2. Flat nested schemas (from classes_discovery.py)

        BDA requirements based on working schemas:
        - Uses "definitions" (not "$defs") - JSON Schema draft-07
        - References use "#/definitions/" (not "#/$defs/")
        - Only LEAF properties get "inferenceType" and "instruction"
        - Object/array types do NOT get these fields

        Args:
            json_schema: JSON Schema from configuration

        Returns:
            Blueprint schema in BDA-compatible draft-07 format
        """
        blueprint = self._create_base_blueprint_structure(json_schema)

        defs = json_schema.get(DEFS_FIELD, {})
        properties = json_schema.get(SCHEMA_PROPERTIES, {})

        if defs:
            blueprint.update(self._process_schema_with_defs(defs, properties))
        else:
            blueprint.update(self._process_flat_schema(properties))

        return blueprint

    def _create_base_blueprint_structure(self, json_schema: dict) -> dict:
        """Create the base blueprint structure."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "class": json_schema.get(
                ID_FIELD, json_schema.get(X_AWS_IDP_DOCUMENT_TYPE, "Document")
            ),
            "description": json_schema.get(
                SCHEMA_DESCRIPTION, "Document schema for data extraction"
            ),
            "type": TYPE_OBJECT,
        }

    def _process_schema_with_defs(self, defs: dict, properties: dict) -> dict:
        """Process schema that has $defs (Pattern 1: from migration.py)."""
        result = {"definitions": {}, "properties": {}}

        # Process definitions
        for def_name, def_value in defs.items():
            result["definitions"][def_name] = self._add_bda_fields_to_schema(def_value)

        # Process properties and update $ref paths
        for prop_name, prop_value in properties.items():
            if REF_FIELD in prop_value:
                # $ref properties should have instruction: "-" based on correct_format.json
                result["properties"][prop_name] = {
                    REF_FIELD: self._normalize_ref_path(prop_value[REF_FIELD]),
                    "instruction": "-",
                }
            else:
                result["properties"][prop_name] = self._add_bda_fields_to_schema(
                    prop_value
                )

        return result

    def _process_flat_schema(self, properties: dict) -> dict:
        """Process flat nested schema (Pattern 2: from classes_discovery.py)."""
        simple_properties, extracted_definitions = self._extract_complex_objects(
            properties
        )

        result = {"properties": {}}

        # Add definitions if any were extracted
        if extracted_definitions:
            result["definitions"] = {}
            for def_name, def_value in extracted_definitions.items():
                result["definitions"][def_name] = self._add_bda_fields_to_schema(
                    def_value
                )

        # Transform simple properties
        for prop_name, prop_value in simple_properties.items():
            if REF_FIELD in prop_value:
                # This is a $ref to an extracted definition
                result["properties"][prop_name] = {REF_FIELD: prop_value[REF_FIELD]}
            else:
                # Handle arrays and simple properties
                prop_type = prop_value.get(SCHEMA_TYPE, "string")
                if prop_type == TYPE_ARRAY and SCHEMA_ITEMS in prop_value:
                    result["properties"][prop_name] = (
                        self._process_array_property_simple(prop_value)
                    )
                else:
                    result["properties"][prop_name] = self._add_bda_fields_to_schema(
                        prop_value
                    )

        return result

    def _normalize_ref_path(self, ref_path: str) -> str:
        """Convert $defs references to definitions references."""
        return ref_path.replace("/$defs/", "/definitions/")

    def _add_bda_fields_to_leaf_property(
        self, prop_schema: dict, original_description: str = None
    ) -> dict:
        """Add BDA fields (inferenceType, instruction) to a leaf property."""
        result = {
            "type": prop_schema.get(SCHEMA_TYPE, "string"),
            "inferenceType": prop_schema.get("inferenceType", "explicit"),
        }

        if "instruction" in prop_schema:
            result["instruction"] = prop_schema["instruction"]
        elif original_description:
            result["instruction"] = original_description
        else:
            result["instruction"] = "Extract this field from the document"

        return result

    def _process_object_properties(self, properties: dict) -> dict:
        """Process object properties, adding BDA fields to leaf properties only."""
        processed_properties = {}

        for name, value in properties.items():
            # Skip $ref properties
            if REF_FIELD in value:
                continue

            # Skip nested objects - BDA doesn't support them
            if value.get(SCHEMA_TYPE) == TYPE_OBJECT:
                continue

            # Process leaf property
            processed_properties[name] = self._add_bda_fields_to_leaf_property(
                value, value.get(SCHEMA_DESCRIPTION)
            )

        return processed_properties

    def _process_array_property_simple(self, prop_value: dict) -> dict:
        """Process array properties for simple cases."""
        items = prop_value[SCHEMA_ITEMS]
        if isinstance(items, dict) and REF_FIELD in items:
            # Array with $ref items - preserve array description as instruction
            array_property = {
                SCHEMA_TYPE: TYPE_ARRAY,
                SCHEMA_ITEMS: {REF_FIELD: items[REF_FIELD]},
            }
            if SCHEMA_DESCRIPTION in prop_value:
                array_property["instruction"] = prop_value[SCHEMA_DESCRIPTION]
            return array_property
        else:
            # Array with simple items
            return self._add_bda_fields_to_schema(prop_value)

    def _process_array_property(
        self, prop_name: str, prop_value: dict, extracted_definitions: dict
    ) -> dict:
        """Process array properties, extracting complex item types to definitions."""
        items = prop_value.get(SCHEMA_ITEMS, {})

        if (
            isinstance(items, dict)
            and items.get(SCHEMA_TYPE) == TYPE_OBJECT
            and SCHEMA_PROPERTIES in items
        ):
            # Array of complex objects - extract to definition
            item_def_name = f"{prop_name}Item"

            item_definition = {
                SCHEMA_TYPE: TYPE_OBJECT,
                SCHEMA_PROPERTIES: self._process_object_properties(
                    items[SCHEMA_PROPERTIES]
                ),
            }

            if SCHEMA_DESCRIPTION in items:
                item_definition[SCHEMA_DESCRIPTION] = items[SCHEMA_DESCRIPTION]

            extracted_definitions[item_def_name] = item_definition

            # Return array with $ref to definition
            array_property = {
                SCHEMA_TYPE: TYPE_ARRAY,
                SCHEMA_ITEMS: {REF_FIELD: f"#/definitions/{item_def_name}"},
            }

            if SCHEMA_DESCRIPTION in prop_value:
                array_property["instruction"] = prop_value[SCHEMA_DESCRIPTION]

            return array_property
        else:
            # Array of simple items
            return prop_value

    def _extract_complex_objects(self, properties: dict) -> tuple[dict, dict]:
        """
        Extract complex objects from flat nested schema properties.

        Args:
            properties: Properties dict from flat nested schema

        Returns:
            tuple: (simple_properties, extracted_definitions)
                - simple_properties: Properties with complex objects replaced by $ref
                - extracted_definitions: Complex objects extracted to definitions
        """
        simple_properties = {}
        extracted_definitions = {}

        for prop_name, prop_value in properties.items():
            if not isinstance(prop_value, dict):
                simple_properties[prop_name] = prop_value
                continue

            prop_type = prop_value.get(SCHEMA_TYPE, "string")

            if prop_type == TYPE_OBJECT and SCHEMA_PROPERTIES in prop_value:
                # This is a complex object - extract to definitions
                definition_name = prop_name

                # Create the definition for this object
                object_definition = {
                    SCHEMA_TYPE: TYPE_OBJECT,
                    SCHEMA_PROPERTIES: self._process_object_properties(
                        prop_value[SCHEMA_PROPERTIES]
                    ),
                }

                # Preserve description if present
                if SCHEMA_DESCRIPTION in prop_value:
                    object_definition[SCHEMA_DESCRIPTION] = prop_value[
                        SCHEMA_DESCRIPTION
                    ]

                extracted_definitions[definition_name] = object_definition

                # Replace with $ref in simple properties
                simple_properties[prop_name] = {
                    REF_FIELD: f"#/definitions/{definition_name}"
                }

            elif prop_type == TYPE_ARRAY and SCHEMA_ITEMS in prop_value:
                # Handle arrays using the dedicated array processor
                simple_properties[prop_name] = self._process_array_property(
                    prop_name, prop_value, extracted_definitions
                )
            else:
                # Simple property - keep as is
                simple_properties[prop_name] = prop_value

        return simple_properties, extracted_definitions

    def _add_bda_fields_to_schema(self, schema: dict) -> dict:
        """
        Add BDA fields (inferenceType, instruction) ONLY to leaf properties.

        Critical BDA requirements (based on working schemas):
        - Pure $ref properties: ONLY the $ref field (when inside definitions)
        - Object/array types: ONLY type and properties (NO description, inferenceType, instruction)
        - Leaf types: type, inferenceType, instruction (NO description)

        Args:
            schema: Property or definition schema

        Returns:
            Schema with BDA fields, description removed
        """
        if not isinstance(schema, dict):
            return schema

        # Make deep copy to avoid mutation
        result = deepcopy(schema)

        # Remove description field - BDA doesn't use it (only instruction)
        original_description = result.pop(SCHEMA_DESCRIPTION, None)

        prop_type = result.get(SCHEMA_TYPE, "string")

        # Add BDA fields ONLY for leaf/primitive types
        if prop_type not in [TYPE_OBJECT, TYPE_ARRAY]:
            # This is a leaf property - use the dedicated helper
            return self._add_bda_fields_to_leaf_property(result, original_description)

        # Handle object types - process properties using helper method
        if prop_type == TYPE_OBJECT and SCHEMA_PROPERTIES in result:
            result[SCHEMA_PROPERTIES] = self._process_object_properties(
                result[SCHEMA_PROPERTIES]
            )

        # Handle array items (but don't add BDA fields to the array itself)
        if prop_type == TYPE_ARRAY and SCHEMA_ITEMS in result:
            result[SCHEMA_ITEMS] = self._add_bda_fields_to_schema(result[SCHEMA_ITEMS])

        return result

    def _check_for_updates(self, custom_class: dict, blueprint: dict):
        """
        Check if the custom_class JSON Schema differs from the existing blueprint.
        Transform both to Bedrock format and then compare.
        """
        # Parse the blueprint schema
        blueprint_schema = blueprint["schema"]
        if isinstance(blueprint_schema, str):
            blueprint_schema = json.loads(blueprint_schema)

        # Transform the custom_class to Bedrock format for comparison
        transformed_custom = self._transform_json_schema_to_bedrock_blueprint(
            custom_class
        )

        # Use DeepDiff to compare the schemas
        diff = DeepDiff(blueprint_schema, transformed_custom, ignore_order=True)

        updates_found = bool(diff)

        if updates_found:
            logger.info("Schema changes detected between custom class and blueprint")
            # Log specific differences for debugging
            logger.info(f"Differences found: {diff}")

        return updates_found

    def _blueprint_lookup(self, existing_blueprints, doc_class):
        # Create a lookup dictionary for existing blueprints by name prefix
        _blueprint_prefix = f"{self.blueprint_name_prefix}-{doc_class}"
        logger.info(f"blueprint lookup using name {_blueprint_prefix}")
        for blueprint in existing_blueprints:
            blueprint_name = blueprint.get("blueprintName", "")
            if blueprint_name.startswith(_blueprint_prefix):
                return blueprint
        return None

    def create_blueprints_from_custom_configuration(self):
        """
        Create blueprint from custom configurations.
        Raises:
            Exception: If blueprint creation fails
        """
        logger.info("Creating blueprint for document ")

        try:
            config_item = self.config_manager.get_configuration(config_type="Custom")

            # Type check: Custom configuration should return IDPConfig which has classes attribute
            if not config_item:
                logger.info("No Custom configuration to process")
                return {"status": "success", "message": "No classes to process"}

            # Use getattr to safely access classes attribute
            classes = getattr(config_item, "classes", None)
            if not classes:
                logger.info("No Custom configuration to process")
                return {"status": "success", "message": "No classes to process"}

            classess = classes

            if not classess or len(classess) == 0:
                logger.info("No Custom configuration to process")
                return {"status": "success", "message": "No classes to process"}

            classess_status = []
            # retrieve all blueprints for this project.
            existing_blueprints = self._retrieve_all_blueprints(
                self.dataAutomationProjectArn
            )

            blueprints_updated = []

            for custom_class in classess:
                try:
                    blueprint_arn = custom_class.get("blueprint_arn", None)
                    blueprint_name = custom_class.get("blueprint_name", None)
                    docu_class = custom_class.get(
                        ID_FIELD, custom_class.get(X_AWS_IDP_DOCUMENT_TYPE, "")
                    )

                    blueprint_exists = self._blueprint_lookup(
                        existing_blueprints, docu_class
                    )
                    if blueprint_exists:
                        blueprint_arn = blueprint_exists.get("blueprintArn")
                        blueprint_name = blueprint_exists.get("blueprintName")
                        logger.info(
                            f"blueprint already exists for this class {docu_class} updating blueprint {blueprint_arn}"
                        )

                    if blueprint_arn:
                        # Use existing blueprint
                        # Note: We don't modify custom_class since it's a JSON Schema
                        logger.info(
                            f"Found existing blueprint for class {docu_class}: {blueprint_name}"
                        )
                        blueprints_updated.append(blueprint_arn)

                        # Check for updates on existing blueprint
                        if self._check_for_updates(
                            custom_class=custom_class, blueprint=blueprint_exists
                        ):
                            blueprint_schema = (
                                self._transform_json_schema_to_bedrock_blueprint(
                                    custom_class
                                )
                            )
                            logger.info(
                                f"Blueprint schema generate:: for {docu_class} to update"
                            )
                            logger.info(json.dumps(blueprint_schema, indent=2))
                            logger.info("Blueprint schema generate:: END")

                            result = self.blueprint_creator.update_blueprint(
                                blueprint_arn=blueprint_arn,
                                stage="LIVE",
                                schema=json.dumps(blueprint_schema),
                            )
                            result = self.blueprint_creator.create_blueprint_version(
                                blueprint_arn=blueprint_arn,
                                project_arn=self.dataAutomationProjectArn,
                            )
                            # Note: We don't store blueprint_version in custom_class since it's a JSON Schema
                            logger.info(
                                f"Updated existing blueprint for class {docu_class}"
                            )
                        else:
                            logger.info(
                                f"No updates needed for existing blueprint {blueprint_name}"
                            )

                    else:
                        # create new blueprint
                        # Call the create_blueprint method
                        blueprint_name = f"{self.blueprint_name_prefix}-{docu_class}-{uuid.uuid4().hex[:8]}"

                        blueprint_schema = (
                            self._transform_json_schema_to_bedrock_blueprint(
                                custom_class
                            )
                        )
                        logger.info(
                            f"Blueprint schema generate:: for {docu_class} for create"
                        )
                        logger.info("Blueprint schema generate:: END")

                        result = self.blueprint_creator.create_blueprint(
                            document_type="DOCUMENT",
                            blueprint_name=blueprint_name,
                            schema=json.dumps(blueprint_schema),
                        )
                        status = result["status"]
                        logger.info(f"blueprint created status {status}")
                        if status != "success":
                            raise Exception(f"Failed to create blueprint: {result}")

                        blueprint_arn = result["blueprint"]["blueprintArn"]
                        blueprint_name = result["blueprint"]["blueprintName"]
                        # Note: We don't store blueprint metadata in custom_class since it's a JSON Schema
                        # update the project or create new project
                        # update the project with version
                        result = self.blueprint_creator.create_blueprint_version(
                            blueprint_arn=blueprint_arn,
                            project_arn=self.dataAutomationProjectArn,
                        )
                        blueprints_updated.append(blueprint_arn)
                        logger.info(
                            f"Created new blueprint for class {docu_class}: {blueprint_name}"
                        )
                    classess_status.append(
                        {
                            "class": docu_class,  # Use the docu_class we extracted earlier
                            "blueprint_arn": blueprint_arn,
                            "status": "success",
                        }
                    )

                except Exception as e:
                    class_name = (
                        custom_class.get(
                            ID_FIELD,
                            custom_class.get(X_AWS_IDP_DOCUMENT_TYPE, "unknown"),
                        )
                        if custom_class
                        else "unknown"
                    )
                    logger.error(
                        f"Error processing blueprint creation/update for class {class_name}: {e}"
                    )
                    classess_status.append(
                        {
                            "class": class_name,
                            "status": "failed",
                            "error_message": f"Exception - {str(e)}",
                        }
                    )
            self._synchronize_deletes(
                existing_blueprints=existing_blueprints,
                blueprints_updated=blueprints_updated,
            )
            self.config_manager.handle_update_custom_configuration(
                {"classes": classess}
            )

            return classess_status

        except Exception as e:
            logger.error(f"Error processing blueprint creation: {e}", exc_info=True)
            # Re-raise the exception to be handled by the caller
            raise Exception(f"Failed to process blueprint creation: {str(e)}")

    def _synchronize_deletes(self, existing_blueprints, blueprints_updated):
        # remove all blueprints which are not in custom class
        blueprints_to_delete = []
        blueprints_arn_to_delete = []
        for blueprint in existing_blueprints:
            blueprint_name = blueprint.get("blueprintName", "")
            blueprint_arn = blueprint.get("blueprintArn", "")
            blueprint_version = blueprint.get("blueprintVersion", "")
            if blueprint_arn in blueprints_updated:
                continue
            if blueprint_name.startswith(self.blueprint_name_prefix):
                # delete detected - remove the blueprint
                logger.info(f"deleting blueprint not in custom class {blueprint_name}")
                blueprints_to_delete.append(blueprint)
                blueprints_arn_to_delete.append(blueprint_arn)

        if len(blueprints_to_delete) > 0:
            # remove the blueprints marked for deletion for the project first before deleting them.
            response = self.blueprint_creator.list_blueprints(
                self.dataAutomationProjectArn, "LIVE"
            )
            custom_configurations = response.get("blueprints", [])
            new_custom_configurations = []
            for custom_blueprint in custom_configurations:
                if custom_blueprint.get("blueprintArn") not in blueprints_arn_to_delete:
                    new_custom_configurations.append(custom_blueprint)
            new_custom_configurations = {"blueprints": new_custom_configurations}
            response = self.blueprint_creator.update_project_with_custom_configurations(
                self.dataAutomationProjectArn,
                customConfiguration=new_custom_configurations,
            )

            try:
                for _blueprint_delete in blueprints_to_delete:
                    self.blueprint_creator.delete_blueprint(
                        _blueprint_delete.get("blueprintArn"),
                        _blueprint_delete.get("blueprintVersion"),
                    )
            except Exception:
                logger.error(
                    f"Error during deleting blueprint {blueprint_name} {blueprint_arn} {blueprint_version}"
                )
            try:
                for _blueprint_delete in blueprints_to_delete:
                    self.blueprint_creator.delete_blueprint(
                        _blueprint_delete.get("blueprintArn"), None
                    )
            except Exception:
                logger.error(
                    f"Error during deleting blueprint {blueprint_name} {blueprint_arn} {blueprint_version}"
                )
