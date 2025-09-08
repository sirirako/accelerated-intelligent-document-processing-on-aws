# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import json
import logging
import os
import uuid
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from idp_common.bda.bda_blueprint_creator import BDABlueprintCreator
from idp_common.bda.schema_converter import SchemaConverter

logger = logging.getLogger(__name__)


class BdaBlueprintService:
    def __init__(
        self,
        dataAutomationProjectArn: Optional[str] = None,
        region: Optional[str] = "us-west-2",
    ):
        self.dataAutomationProjectArn = dataAutomationProjectArn
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.blueprint_creator = BDABlueprintCreator(region_name=self.region)
        self.configuration_table_name = os.environ.get("CONFIGURATION_TABLE_NAME", "")
        dynamodb = boto3.resource("dynamodb")
        self.configuration_table = dynamodb.Table(self.configuration_table_name)

        return

    """
    Recursively convert all values to strings
    """

    def _stringify_values(self, obj):
        if isinstance(obj, dict):
            return {k: self._stringify_values(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._stringify_values(item) for item in obj]
        else:
            # Convert everything to string, except None values
            return str(obj) if obj is not None else None

    def _get_configuration_item(self, config_type):
        """
        Retrieve a configuration item from DynamoDB
        """
        try:
            response = self.configuration_table.get_item(
                Key={"Configuration": config_type}
            )
            return response.get("Item")
        except ClientError as e:
            logger.error(f"Error retrieving {config_type} configuration: {str(e)}")
            raise Exception(f"Failed to retrieve {config_type} configuration")

    def _handle_update_configuration(self, custom_config):
        """
        Handle the updateConfiguration GraphQL mutation
        Updates the Custom or Default configuration item in DynamoDB
        """
        try:
            # Handle empty configuration case
            stringified_config = self._stringify_values(custom_config)

            self.configuration_table.put_item(
                Item={"Configuration": "Custom", "classes": stringified_config}
            )

            logger.info("Updated Custom configuration")

            return True

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in customConfig: {str(e)}")
            raise Exception(f"Invalid configuration format: {str(e)}")
        except Exception as e:
            logger.error(f"Error in updateConfiguration: {str(e)}")
            raise e

    def _format_section_name(self, section_name: str) -> str:
        """Format section name to PascalCase for definitions."""
        words = section_name.replace(" ", "-").split()
        return "".join(word.capitalize() for word in words)

    def _format_field_name(self, field_name: str) -> str:
        """Format field name to snake_case for properties."""
        # Remove any non-alphanumeric characters except spaces
        field_name = "".join(
            c if c.isalnum() or c.isspace() else " " for c in field_name
        )
        # Convert to snake_case
        field_name = "".join(field_name.lower().split())
        return field_name.replace("_", "-")

    def _check_for_updates(self, custom_class: dict, blueprint_arn: str):
        blueprint = self.blueprint_creator.get_blueprint(blueprint_arn, stage="LIVE")
        # print(f"blueprint retrieved {blueprint}")
        # get the schema
        schema = blueprint["blueprint"]["schema"]
        schema = json.loads(schema)
        # get the document class
        definitions = schema["definitions"]
        groups = custom_class.get("attributes", None)
        # traverse thru definitions fist
        if groups is None:
            groups = []
        logger.info(f"number of groups {len(groups)}")
        _updatesFound = False
        if (
            custom_class["name"] != schema["class"]
            or custom_class["description"] != schema["description"]
        ):
            _updatesFound = True
            return _updatesFound
        for group in groups:
            groupName = group.get("name")
            formattedGroupName = self._format_section_name(groupName)
            definition = definitions.get(formattedGroupName, None)
            if not definition:
                logger.info(f"change found group {groupName} : {formattedGroupName}")
                return True

            if definition:
                for field in group["groupAttributes"]:
                    field_name = field.get("name")
                    formatted_field_name = self._format_field_name(
                        field_name=field_name
                    )
                    blueprint_field = definition["properties"].get(
                        formatted_field_name, None
                    )
                    if not blueprint_field or blueprint_field[
                        "instruction"
                    ] != field.get("description", None):
                        _updatesFound = True
                        logger.info(
                            f"change found for field {groupName} : {formattedGroupName} {blueprint_field} {field}"
                        )
                        return _updatesFound

        return _updatesFound

    def create_blueprints_from_custom_configuration(self):
        """
        Create blueprint from custom configurations.
        Raises:
            Exception: If blueprint creation fails
        """
        logger.info("Creating blueprint for document ")

        try:
            config_item = self._get_configuration_item("Custom")

            if not config_item or "classes" not in config_item:
                logger.info("No Custom configuration to process")
                return {"status": "success", "message": "No classes to process"}

            classess = config_item["classes"]

            if not classess or len(classess) == 0:
                logger.info("No Custom configuration to process")
                return {"status": "success", "message": "No classes to process"}

            classess_status = []

            for custom_class in classess:
                try:
                    blueprint_arn = custom_class.get("blueprint_arn", None)
                    blueprint_name = custom_class.get("blueprint_name", None)
                    docu_class = custom_class["name"]
                    docu_desc = custom_class["description"]
                    converter = SchemaConverter(
                        document_class=docu_class, description=docu_desc
                    )
                    blueprint_schema = converter.convert(custom_class)
                    logger.info(
                        f"Blueprint schema generate:: for {json.dumps(custom_class, indent=2)}"
                    )
                    logger.info(json.dumps(blueprint_schema, indent=2))
                    logger.info("Blueprint schema generate:: END")

                    if blueprint_arn is None:
                        # create blueprint
                        # Call the create_blueprint method
                        blueprint_name = f"{docu_class}-{uuid.uuid4().hex[:8]}"

                        result = self.blueprint_creator.create_blueprint(
                            document_type="DOCUMENT",
                            blueprint_name=blueprint_name,
                            schema=json.dumps(blueprint_schema),
                        )
                        status = result["status"]
                        print(f"blueprint created status {status}")
                        if status != "success":
                            raise Exception(f"Failed to create blueprint: {result}")

                        blueprint_arn = result["blueprint"]["blueprintArn"]
                        blueprint_name = result["blueprint"]["blueprintName"]
                        custom_class["blueprint_arn"] = blueprint_arn
                        # update the project or create new project
                        # update the project with version
                        result = self.blueprint_creator.create_blueprint_version(
                            blueprint_arn=blueprint_arn,
                            project_arn=self.dataAutomationProjectArn,
                        )
                    else:
                        # check for Updates
                        if self._check_for_updates(
                            custom_class=custom_class, blueprint_arn=blueprint_arn
                        ):
                            result = self.blueprint_creator.update_blueprint(
                                blueprint_arn=blueprint_arn,
                                stage="LIVE",
                                schema=json.dumps(blueprint_schema),
                            )
                            result = self.blueprint_creator.create_blueprint_version(
                                blueprint_arn=blueprint_arn,
                                project_arn=self.dataAutomationProjectArn,
                            )
                        else:
                            logger.info(
                                f"No updates found for custom class {custom_class['name']}, skipping blueprint update"
                            )

                    classess_status.append(
                        {
                            "class": custom_class["name"],
                            "blueprint_arn": blueprint_arn,
                            "status": "success",
                        }
                    )

                except Exception as e:
                    logger.error(f"Error processing blueprint creation/update {e}")
                    classess_status.append(
                        {
                            "class": "unknown",
                            "status": "failed",
                            "error_message": f"Exception - {str(e)}",
                        }
                    )

            self._handle_update_configuration(classess)
            return classess_status

        except Exception as e:
            logger.error(f"Error processing blueprint creation: {e}", exc_info=True)
            # Re-raise the exception to be handled by the caller
            raise Exception(f"Failed to process blueprint creation: {str(e)}")
