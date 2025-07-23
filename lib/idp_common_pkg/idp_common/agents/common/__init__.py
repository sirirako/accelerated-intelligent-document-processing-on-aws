# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Common utilities for IDP agents.

This module provides shared functionality that can be used across different agent types.
"""

from .config import get_environment_config

__all__ = [
    "get_environment_config",
]
