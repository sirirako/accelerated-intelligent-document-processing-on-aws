#!/usr/bin/env python3
"""
Debug script to show the exact schema being generated for BDA.
"""

import json
import sys
from pathlib import Path

# Add idp_common to path
lib_dir = Path(__file__).parent.parent.parent / "lib" / "idp_common_pkg"
sys.path.insert(0, str(lib_dir))

# Set real environment variables
import os
os.environ.setdefault("BDA_PROJECT_ARN", "arn:aws:bedrock:us-west-2:912625584728:data-automation-project/af1ddcfacc2d")
os.environ.setdefault("CONFIGURATION_TABLE_NAME", "IDP-BDA-3-ConfigurationTable-1XUJJGXYBUWCE")
os.environ.setdefault("DISCOVERY_TRACKING_TABLE", "IDP-BDA-3-DiscoveryTrackingTable-MRFIS9DV02N3")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("METRIC_NAMESPACE", "IDP-BDA-3")
os.environ.setdefault("STACK_NAME", "IDP-BDA-3")
os.environ.setdefault("AWS_REGION", "us-west-2")

from idp_common.bda.bda_blueprint_service import BdaBlueprintService


def main():
    """Generate and display the BDA blueprint schema."""
    
    # Sample JSON Schema from logs (the IRS-Form-W-2 that's failing)
    json_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": {
            "REISSUED-STATEMENT": {
                "type": "object",
                "description": "Details of the reissued statement.",
                "properties": {
                    "a-Employees-social-security-number": {
                        "type": "string",
                        "description": "Employee's social security number."
                    },
                    "b-Employer-identification-number": {
                        "type": "string",
                        "description": "Employer identification number."
                    }
                }
            }
        },
        "description": "New W-2 form for wage and tax statement.",
        "type": "object",
        "x-aws-idp-document-type": "IRS-Form-W-2",
        "properties": {
            "Retirement-plan": {
                "type": "string",
                "description": "Retirement plan indicator."
            },
            "REISSUED-STATEMENT": {
                "description": "Details of the reissued statement.",
                "$ref": "#/$defs/REISSUED-STATEMENT"
            },
            "Wages-tips-other-compensation": {
                "type": "string",
                "description": "Wages, tips, other compensation."
            }
        },
        "$id": "IRS-Form-W-2"
    }
    
    # Working schema from logs (for comparison)
    working_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "description": "The W-2 form...",
        "class": "W-2",
        "type": "object",
        "definitions": {
            "Employee-information": {
                "type": "object",
                "properties": {
                    "employeessn": {
                        "type": "string",
                        "inferenceType": "explicit",
                        "instruction": "Employee's social security number (Box a)"
                    }
                }
            }
        },
        "properties": {
            "Employee-information": {
                "$ref": "#/definitions/Employee-information"
            }
        }
    }
    
    # Initialize service
    service = BdaBlueprintService()
    
    # Transform the schema
    print("="* 80)
    print("INPUT JSON SCHEMA (draft 2020-12):")
    print("=" * 80)
    print(json.dumps(json_schema, indent=2))
    
    print("\n" + "=" * 80)
    print("GENERATED BDA BLUEPRINT SCHEMA:")
    print("=" * 80)
    blueprint = service._transform_json_schema_to_bedrock_blueprint(json_schema)
    print(json.dumps(blueprint, indent=2))
    
    print("\n" + "=" * 80)
    print("WORKING REFERENCE SCHEMA (for comparison):")
    print("=" * 80)
    print(json.dumps(working_schema, indent=2))
    
    print("\n" + "=" * 80)
    print("KEY DIFFERENCES TO CHECK:")
    print("=" * 80)
    print(f"1. Schema version: {blueprint.get('$schema')}")
    print(f"2. Has 'definitions': {'definitions' in blueprint}")
    print(f"3. Has '$defs': {'$defs' in blueprint}")
    print(f"4. Has 'class' field: {'class' in blueprint}")
    print(f"5. Has 'type' field: {'type' in blueprint}")
    
    if "definitions" in blueprint:
        print(f"\n6. Definitions:")
        for def_name, def_val in blueprint["definitions"].items():
            has_inference = "inferenceType" in def_val
            has_instruction = "instruction" in def_val
            print(f"   - {def_name}: type={def_val.get('type')}, has inferenceType={has_inference}, has instruction={has_instruction}")
            if "properties" in def_val:
                for prop_name, prop_val in def_val["properties"].items():
                    has_inf = "inferenceType" in prop_val
                    has_inst = "instruction" in prop_val
                    print(f"     * {prop_name}: type={prop_val.get('type')}, inferenceType={has_inf}, instruction={has_inst}")
    
    print(f"\n7. Top-level properties:")
    for prop_name, prop_val in blueprint.get("properties", {}).items():
        if "$ref" in prop_val:
            print(f"   - {prop_name}: $ref={prop_val['$ref']}")
        else:
            has_inf = "inferenceType" in prop_val
            has_inst = "instruction" in prop_val
            print(f"   - {prop_name}: type={prop_val.get('type')}, inferenceType={has_inf}, instruction={has_inst}")


if __name__ == "__main__":
    main()
