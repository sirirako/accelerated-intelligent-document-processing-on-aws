# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Pydantic model generation utilities for JSON Schema.

This module provides utilities for dynamically generating Pydantic v2 models
from JSON Schema definitions using datamodel-code-generator.
"""

import importlib.util
import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from datamodel_code_generator import DataModelType, InputFileType, generate
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PydanticModelGenerationError(Exception):
    """Exception raised when Pydantic model generation fails."""

    pass


class CircularReferenceError(PydanticModelGenerationError):
    """Exception raised when circular references are detected in schema."""

    pass


def clean_schema_for_generation(
    schema: Dict[str, Any], fields_to_remove: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Clean JSON Schema by removing custom extension fields.

    Args:
        schema: JSON Schema definition
        fields_to_remove: List of field prefixes to remove (default: ["x-aws-idp-"])

    Returns:
        Cleaned JSON Schema without custom extension fields
    """
    if fields_to_remove is None:
        fields_to_remove = ["x-aws-idp-"]

    cleaned = {}

    for key, value in schema.items():
        # Skip fields that match removal patterns
        if any(key.startswith(prefix) for prefix in fields_to_remove):
            continue

        # Recursively clean nested objects
        if isinstance(value, dict):
            cleaned[key] = clean_schema_for_generation(value, fields_to_remove)
        elif isinstance(value, list):
            cleaned[key] = [
                clean_schema_for_generation(item, fields_to_remove)
                if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            cleaned[key] = value

    return cleaned


def _normalize_class_name(name: str) -> str:
    """
    Normalize a class name to PascalCase.

    Args:
        name: Class name to normalize

    Returns:
        PascalCase version of the name
    """
    return "".join(
        word.capitalize() for word in name.replace("-", " ").replace("_", " ").split()
    )


def _find_model_in_module(
    generated_module: Any,
    schema_dict: Dict[str, Any],
    class_label: str,
) -> Tuple[Optional[Type[BaseModel]], List[Tuple[str, Type[BaseModel]]]]:
    """
    Find the appropriate Pydantic model in a generated module.

    Args:
        generated_module: The dynamically imported module
        schema_dict: The JSON Schema dictionary
        class_label: The class label for fallback matching

    Returns:
        Tuple of (selected_model, all_models_list)
    """
    # Find all BaseModel subclasses in the module
    all_models = [
        (name, obj)
        for name in dir(generated_module)
        if (obj := getattr(generated_module, name))
        and isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj != BaseModel
        and not name.startswith("_")
    ]

    if not all_models:
        return None, []

    # Get schema title/id for matching
    schema_title = schema_dict.get("title", schema_dict.get("$id", class_label))
    schema_title_pascal = _normalize_class_name(schema_title)
    class_label_pascal = _normalize_class_name(class_label)

    # Try to find the best matching model
    # Priority: exact schema title > exact class label > "Model" > first available
    matching_names = [
        schema_title_pascal,
        schema_title.replace(" ", ""),
        class_label_pascal,
        class_label.replace(" ", ""),
        "Model",
    ]

    for name, obj in all_models:
        if name in matching_names:
            return obj, all_models

    # No exact match - use first available
    return all_models[0][1], all_models


def create_pydantic_model_from_json_schema(
    schema: Dict[str, Any],
    class_label: str,
    clean_schema: bool = True,
    fields_to_remove: Optional[List[str]] = None,
) -> Type[BaseModel]:
    """
    Dynamically create a Pydantic v2 model from JSON Schema.

    This function uses datamodel-code-generator to create a Pydantic model
    from a JSON Schema definition. The model is generated in a temporary
    file and then dynamically imported.

    Args:
        schema: JSON Schema definition (dict or JSON string)
        class_label: Label/name for the class (used for module naming and fallback)
        clean_schema: Whether to clean custom fields before generation (default: True)
        fields_to_remove: List of field prefixes to remove when cleaning (default: ["x-aws-idp-"])

    Returns:
        Dynamically created Pydantic BaseModel class

    Raises:
        ValueError: If no model classes are found in generated code
        Exception: Any exception from datamodel-code-generator (e.g., invalid schema)

    Examples:
        >>> schema = {
        ...     "type": "object",
        ...     "title": "Invoice",
        ...     "properties": {
        ...         "invoice_number": {"type": "string"},
        ...         "amount": {"type": "number"}
        ...     }
        ... }
        >>> InvoiceModel = create_pydantic_model_from_json_schema(schema, "Invoice")
        >>> invoice = InvoiceModel(invoice_number="INV-001", amount=100.50)
    """
    # Clean the schema if requested
    if clean_schema:
        processed_schema = clean_schema_for_generation(schema, fields_to_remove)
    else:
        processed_schema = schema

    # Convert to JSON string if needed
    schema_str = (
        json.dumps(processed_schema)
        if isinstance(processed_schema, dict)
        else processed_schema
    )

    # Sanitize class_label for use in module name (remove special chars)
    safe_class_label = "".join(c if c.isalnum() else "_" for c in class_label)
    module_name = f"generated_model_{safe_class_label}"

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / f"model_{safe_class_label}.py"

            # Generate the Pydantic model code
            generate(
                input_=schema_str,
                input_file_type=InputFileType.JsonSchema,
                output_model_type=DataModelType.PydanticV2BaseModel,
                output=tmp_path,
                disable_timestamp=True,
                use_standard_collections=True,
                use_union_operator=True,
            )

            # Import the generated module
            spec = importlib.util.spec_from_file_location(module_name, tmp_path)
            if not spec or not spec.loader:
                raise PydanticModelGenerationError(
                    f"Failed to create module spec for '{class_label}'"
                )

            generated_module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = generated_module
            spec.loader.exec_module(generated_module)

            # Parse schema dict for model selection
            schema_dict = (
                json.loads(schema_str)
                if isinstance(schema_str, str)
                else processed_schema
            )

            # Find the appropriate model
            data_model, all_models = _find_model_in_module(
                generated_module, schema_dict, class_label
            )

            if not data_model:
                raise ValueError(
                    f"No Pydantic models found in generated code for class '{class_label}'"
                )

            # Rebuild the model to ensure proper configuration
            data_model.model_rebuild()

            logger.info(
                f"Created Pydantic model '{data_model.__name__}' from JSON Schema for class '{class_label}' "
                f"(selected from {len(all_models)} available models)"
            )

            return data_model

    finally:
        # Clean up the module from sys.modules
        if module_name in sys.modules:
            del sys.modules[module_name]
            logger.debug(f"Cleaned up module '{module_name}' from sys.modules")


def validate_json_schema_for_pydantic(schema: Dict[str, Any]) -> List[str]:
    """
    Validate that a JSON Schema is suitable for Pydantic model generation.

    Args:
        schema: JSON Schema to validate

    Returns:
        List of validation warnings (empty if schema is valid)
    """
    warnings = []

    # Check for required top-level fields
    if "type" not in schema:
        warnings.append("Schema missing 'type' field")

    # Check that type is object for Pydantic models
    if schema.get("type") != "object":
        warnings.append(
            f"Schema type is '{schema.get('type')}' but Pydantic models require type='object'"
        )

    # Check for properties
    if "properties" not in schema:
        warnings.append("Schema has no 'properties' field - model will be empty")

    # Check for potential circular references
    def check_circular(
        obj: Any, path: Optional[List[str]] = None, seen: Optional[set] = None
    ):
        if path is None:
            path = []
        if seen is None:
            seen = set()

        if isinstance(obj, dict):
            # Check for $ref that might cause circular references
            if "$ref" in obj:
                ref = obj["$ref"]
                if ref in seen:
                    warnings.append(
                        f"Potential circular reference detected at path {'.'.join(path)}: {ref}"
                    )
                else:
                    seen.add(ref)

            for key, value in obj.items():
                check_circular(value, path + [key], seen)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                check_circular(item, path + [f"[{i}]"], seen)

    check_circular(schema)

    return warnings
