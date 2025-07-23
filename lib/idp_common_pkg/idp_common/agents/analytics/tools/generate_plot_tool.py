# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Python Plot Generation Tool for creating visualizations and tables using Strands framework.
"""

import json  # noqa
import logging
import sys
from io import StringIO
from typing import Any, Dict

from strands import tool

# Import commonly used libraries for analytics
try:
    import pandas as pd  # noqa
except ImportError:
    pd = None


import random  # noqa

logger = logging.getLogger(__name__)


@tool
def generate_plot(code: str) -> Dict[str, Any]:
    """
    Executes Python code to create plots or tables for analytics visualization.

    This function executes the given code with access to specific predefined functions
    while capturing both standard output and standard error streams.

    Args:
        code (str): The Python code to generate a plot or table to be executed as a string.

    Returns:
        dict: A dictionary containing:
            - 'stdout' (str): The captured standard output from the code execution
            - 'stderr' (str): The captured standard error output from the code execution
            - 'success' (bool): Whether the execution was successful

    Note:
        - The code is executed in a restricted environment with only specific functions available
        - All stdout is captured and returned rather than being printed directly
        - Available libraries: json, pandas (if installed), random
    """
    logger.info(f"Executing Python code:\n{code}")

    stdout_buffer = StringIO()
    stderr_buffer = StringIO()

    # Save the originals
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    try:
        # Redirect stdout to our buffer
        sys.stdout = stdout_buffer
        sys.stderr = stderr_buffer

        # Create a restricted execution environment
        exec_globals = {
            "__builtins__": __builtins__,
            "json": json,
            "random": random,
        }

        # Add pandas if available
        if pd is not None:
            exec_globals["pd"] = pd
            exec_globals["pandas"] = pd

        # Execute the code snippet
        exec(code, exec_globals)

        # Get the captured output
        output = stdout_buffer.getvalue()
        err = stderr_buffer.getvalue()

        if output:
            logger.info(
                f"Python code execution succeeded with output length: {len(output)}"
            )
        else:
            logger.warning("Python code execution produced no output")

        if err:
            logger.error(f"Python code execution produced errors:\n{err}")

        return {"stdout": output, "stderr": err, "success": not bool(err)}

    except Exception as e:
        logger.exception(f"Error executing Python code: {str(e)}")
        return {"stdout": "", "stderr": str(e), "success": False}

    finally:
        # Restore the original stdout and stderr
        sys.stdout = original_stdout
        sys.stderr = original_stderr
