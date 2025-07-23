#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Wrapper script that loads .env file and runs the analytics test.
"""

import sys
from pathlib import Path

# Try to load .env file if it exists
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"Loaded environment variables from {env_file}")
    else:
        print(f"No .env file found at {env_file}")
        print("You can create one by copying .env.example to .env and updating the values")
except ImportError:
    print("python-dotenv not available, using system environment variables")

# Add the idp_common_pkg root to Python path
pkg_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(pkg_root))

# Import after path modification to avoid E402 linting error
from idp_common.agents.testing.test_analytics import main  # noqa: E402

if __name__ == "__main__":
    main()
