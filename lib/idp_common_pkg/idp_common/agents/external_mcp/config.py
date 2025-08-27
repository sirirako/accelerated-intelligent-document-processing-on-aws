# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Configuration for External MCP Agent.
"""

import os
from typing import Any, Dict


def get_external_mcp_config() -> Dict[str, Any]:
    """
    Get configuration for External MCP Agent.

    Returns:
        Configuration dictionary with secret name and region
    """
    return {
        "secret_name": os.environ.get(
            "EXTERNAL_MCP_SECRET_NAME", "idp/external-mcp-agent/credentials"
        ),
        "region": os.environ.get("AWS_REGION", "us-east-1"),
    }
