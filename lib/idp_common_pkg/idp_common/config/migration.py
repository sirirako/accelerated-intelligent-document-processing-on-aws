from typing import Any, Dict, List, Optional, Union


def is_legacy_format(data: Union[Dict, List, Any]) -> bool:
    """
    Detect if data is in legacy format (vs JSON Schema).

    Legacy format has:
    - "attributes" key with list value
    - No "$schema", "$id", or "properties" keys

    JSON Schema format has:
    - "$schema", "$id", or "properties" keys
    - "attributes" as dict (nested schema) or absent

    Args:
        data: Configuration data (dict, list, or other)

    Returns:
        True if legacy format, False if JSON Schema or unknown
    """
    if data is None:
        return False

    # Handle list of classes
    if isinstance(data, list):
        if len(data) == 0:
            return False
        # Check first element
        return is_legacy_format(data[0])

    # Handle single class/schema dict
    if isinstance(data, dict):
        # Definitive JSON Schema markers
        if any(key in data for key in ["$schema", "$id", "properties"]):
            return False

        # Special marker for our schema format
        if "x-aws-idp-document-type" in data:
            return False

        # Legacy marker: attributes is a list
        if "attributes" in data:
            attributes = data["attributes"]
            return isinstance(attributes, list)

        # No attributes at all - assume modern format
        return False

    # Unknown type
    return False


def is_json_schema_format(data: Union[Dict, List, Any]) -> bool:
    """
    Detect if data is in JSON Schema format.

    Inverse of is_legacy_format for clarity.

    Args:
        data: Configuration data

    Returns:
        True if JSON Schema format, False if legacy or unknown
    """
    if data is None:
        return False
    return not is_legacy_format(data)


def migrate_legacy_to_schema(
    legacy_classes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Migrate legacy classes to JSON Schema format.

    Each legacy class is treated as a document type in the new format.
    Always returns an array of JSON Schema objects for consistency.

    Args:
        legacy_classes: List of legacy class configurations
        validate: Whether to validate the result against JSON Schema (default: True)

    Returns:
        List of migrated JSON Schema objects (always array, even for single schema)

    Raises:
        ValueError: If validation is enabled and result is invalid
    """
    migrated_classes = []

    for class_config in legacy_classes:
        migrated_class = {
            "name": class_config.get("name", ""),
            "description": class_config.get("description", ""),
            "x-aws-idp-document-type": True,  # Mark as document type
            "attributes": {"type": "object", "properties": {}, "required": []},
        }

        legacy_attributes = class_config.get("attributes", [])

        for attr in legacy_attributes:
            attr_name = attr.get("name", "")
            attr_type = attr.get("attributeType", "simple")

            if attr_type == "simple":
                schema_attr = _migrate_simple_attribute(attr)
            elif attr_type == "group":
                schema_attr = _migrate_group_attribute(attr)
            elif attr_type == "list":
                schema_attr = _migrate_list_attribute(attr)
            else:
                schema_attr = _migrate_simple_attribute(attr)

            migrated_class["attributes"]["properties"][attr_name] = schema_attr

        migrated_classes.append(migrated_class)

    # Convert class array to JSON Schema format
    result = _convert_classes_to_json_schema(migrated_classes)

    return result


def _validate_and_set_aws_extensions(
    schema_attr: Dict[str, Any], source_attr: Dict[str, Any]
) -> None:
    """
    Validate and set AWS IDP extension fields.

    Args:
        schema_attr: Target schema attribute to update
        source_attr: Source attribute with potential AWS extensions

    Raises:
        ValueError: If AWS extension values are invalid
    """
    VALID_EVALUATION_METHODS = frozenset(
        ["EXACT", "NUMERIC_EXACT", "FUZZY", "SEMANTIC"]
    )

    if "evaluation_method" in source_attr:
        method = source_attr["evaluation_method"]
        if method not in VALID_EVALUATION_METHODS:
            raise ValueError(
                f"Invalid evaluation_method '{method}'. Must be one of: {', '.join(VALID_EVALUATION_METHODS)}"
            )
        schema_attr["x-aws-idp-evaluation-method"] = method

    if "confidence_threshold" in source_attr:
        threshold = source_attr["confidence_threshold"]
        # Convert string to float if needed
        if isinstance(threshold, str):
            try:
                threshold = float(threshold)
            except (ValueError, TypeError):
                raise ValueError(
                    f"Invalid confidence_threshold '{threshold}'. Must be a number between 0 and 1."
                )

        # Validate range
        if not isinstance(threshold, (int, float)):
            raise ValueError(
                f"confidence_threshold must be a number, got {type(threshold).__name__}"
            )

        if not (0 <= threshold <= 1):
            raise ValueError(
                f"confidence_threshold must be between 0 and 1, got {threshold}"
            )

        schema_attr["x-aws-idp-confidence-threshold"] = float(threshold)

    if "prompt_override" in source_attr:
        prompt = source_attr["prompt_override"]
        if not isinstance(prompt, str):
            raise ValueError(
                f"prompt_override must be a string, got {type(prompt).__name__}"
            )
        if len(prompt) > 10000:
            raise ValueError("prompt_override is too long (maximum 10000 characters)")
        schema_attr["x-aws-idp-prompt-override"] = prompt


def _migrate_simple_attribute(attr: Dict[str, Any]) -> Dict[str, Any]:
    schema_attr = {
        "type": "string",
        "description": attr.get("description", ""),
        "x-aws-idp-attribute-type": "simple",
    }

    _validate_and_set_aws_extensions(schema_attr, attr)

    return schema_attr


def _migrate_group_attribute(attr: Dict[str, Any]) -> Dict[str, Any]:
    schema_attr = {
        "type": "object",
        "description": attr.get("description", ""),
        "properties": {},
        "x-aws-idp-attribute-type": "group",
    }

    group_attrs = attr.get("groupAttributes", [])
    for group_attr in group_attrs:
        attr_name = group_attr.get("name", "")
        schema_attr["properties"][attr_name] = _migrate_simple_attribute(group_attr)

    _validate_and_set_aws_extensions(schema_attr, attr)

    return schema_attr


def _migrate_list_attribute(attr: Dict[str, Any]) -> Dict[str, Any]:
    schema_attr = {
        "type": "array",
        "description": attr.get("description", ""),
        "x-aws-idp-attribute-type": "list",
    }

    list_item_template = attr.get("listItemTemplate", {})
    item_attrs = list_item_template.get("itemAttributes", [])

    if "itemDescription" in list_item_template:
        schema_attr["x-aws-idp-list-item-description"] = list_item_template[
            "itemDescription"
        ]

    if len(item_attrs) == 1:
        item_schema = _migrate_simple_attribute(item_attrs[0])
        if "name" in item_attrs[0]:
            item_schema["x-aws-idp-original-name"] = item_attrs[0]["name"]
        schema_attr["items"] = item_schema
    else:
        schema_attr["items"] = {"type": "object", "properties": {}}
        for item_attr in item_attrs:
            attr_name = item_attr.get("name", "")
            schema_attr["items"]["properties"][attr_name] = _migrate_simple_attribute(
                item_attr
            )

    if "evaluation_method" in attr:
        schema_attr["x-aws-idp-evaluation-method"] = attr["evaluation_method"]

    if "confidence_threshold" in attr:
        threshold = attr["confidence_threshold"]
        if isinstance(threshold, str):
            try:
                threshold = float(threshold)
            except (ValueError, TypeError):
                threshold = None
        if threshold is not None:
            schema_attr["x-aws-idp-confidence-threshold"] = threshold

    return schema_attr


def _add_aws_extensions(legacy_attr: Dict[str, Any], schema: Dict[str, Any]) -> None:
    if "x-aws-idp-evaluation-method" in schema:
        legacy_attr["evaluation_method"] = schema["x-aws-idp-evaluation-method"]

    if "x-aws-idp-confidence-threshold" in schema:
        threshold = schema["x-aws-idp-confidence-threshold"]
        legacy_attr["confidence_threshold"] = (
            str(threshold) if threshold is not None else None
        )

    if "x-aws-idp-prompt-override" in schema:
        legacy_attr["prompt_override"] = schema["x-aws-idp-prompt-override"]


def _sanitize_attribute_schema(attribute: Any) -> Any:
    """Remove internal fields (id, name) from attribute schema recursively."""
    if not attribute or not isinstance(attribute, dict):
        return attribute

    # Create a copy without 'id' and 'name' fields
    sanitized = {k: v for k, v in attribute.items() if k not in ("id", "name")}

    # Recursively sanitize nested structures
    if "items" in sanitized:
        sanitized["items"] = _sanitize_attribute_schema(sanitized["items"])

    if "properties" in sanitized:
        sanitized["properties"] = {
            prop_name: _sanitize_attribute_schema(prop_value)
            for prop_name, prop_value in sanitized["properties"].items()
        }

    return sanitized


def _find_referenced_classes(
    root_class: Dict[str, Any],
    all_classes: List[Dict[str, Any]],
    visited: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """Find all classes referenced by root_class (recursively)."""
    if visited is None:
        visited = set()

    referenced = []

    def process_properties(properties: Dict[str, Any]) -> None:
        for attr in properties.values():
            # Check direct $ref
            if isinstance(attr, dict) and "$ref" in attr:
                ref_name = attr["$ref"].replace("#/$defs/", "")
                if ref_name not in visited:
                    ref_class = next(
                        (c for c in all_classes if c["name"] == ref_name), None
                    )
                    if ref_class and not ref_class.get("x-aws-idp-document-type"):
                        visited.add(ref_name)
                        referenced.append(ref_class)
                        # Recursively find references in this class
                        referenced.extend(
                            _find_referenced_classes(ref_class, all_classes, visited)
                        )

            # Check array items $ref
            if (
                isinstance(attr, dict)
                and "items" in attr
                and isinstance(attr["items"], dict)
            ):
                if "$ref" in attr["items"]:
                    ref_name = attr["items"]["$ref"].replace("#/$defs/", "")
                    if ref_name not in visited:
                        ref_class = next(
                            (c for c in all_classes if c["name"] == ref_name), None
                        )
                        if ref_class and not ref_class.get("x-aws-idp-document-type"):
                            visited.add(ref_name)
                            referenced.append(ref_class)
                            referenced.extend(
                                _find_referenced_classes(
                                    ref_class, all_classes, visited
                                )
                            )

            # Check nested object properties
            if (
                isinstance(attr, dict)
                and attr.get("type") == "object"
                and "properties" in attr
            ):
                process_properties(attr["properties"])

    attributes = root_class.get("attributes", {})
    properties = attributes.get("properties", {})
    process_properties(properties)

    return referenced


def _convert_classes_to_json_schema(
    classes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert class array to JSON Schema format. Always returns array of schemas."""
    if not classes:
        return []

    # Find all document type classes
    doc_type_classes = [
        cls for cls in classes if cls.get("x-aws-idp-document-type") is True
    ]

    # If no document types, treat first class as document type (backward compatibility)
    if not doc_type_classes:
        doc_type_classes = [classes[0]]
        # Mark it as document type
        doc_type_classes[0]["x-aws-idp-document-type"] = True

    # Build schema for each document type
    schemas = []
    for doc_type_class in doc_type_classes:
        # Find classes referenced by this document type
        referenced_classes = _find_referenced_classes(doc_type_class, classes)

        # Build $defs only for referenced classes
        defs = {}
        for cls in referenced_classes:
            sanitized_props = {
                attr_name: _sanitize_attribute_schema(attr_value)
                for attr_name, attr_value in cls.get("attributes", {})
                .get("properties", {})
                .items()
            }

            defs[cls["name"]] = {
                "type": "object",
                "properties": sanitized_props,
            }
            if cls.get("description"):
                defs[cls["name"]]["description"] = cls["description"]

            required = cls.get("attributes", {}).get("required", [])
            if required:
                defs[cls["name"]]["required"] = required

        # Build main schema properties
        sanitized_props = {
            attr_name: _sanitize_attribute_schema(attr_value)
            for attr_name, attr_value in doc_type_class.get("attributes", {})
            .get("properties", {})
            .items()
        }

        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": doc_type_class["name"],
            "x-aws-idp-document-type": doc_type_class["name"],
            "type": "object",
            "properties": sanitized_props,
        }

        if doc_type_class.get("description"):
            schema["description"] = doc_type_class["description"]

        required = doc_type_class.get("attributes", {}).get("required", [])
        if required:
            schema["required"] = required

        if defs:
            schema["$defs"] = defs

        schemas.append(schema)

    # Always return array of schemas for consistency
    return schemas
