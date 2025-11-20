#!/bin/bash

# Get AgentCore Gateway Configuration Info

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "$SCRIPT_DIR/get_gateway_info.py" "$@"
