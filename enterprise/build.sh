#!/bin/bash
# OPTIONAL local-dev helper — populate the layer python/ dirs for editor/import
# resolution while working on the code locally.
#
# NOT required before publish: the layers declare `Metadata: BuildMethod: python3.12`,
# so `sam build` / `idp-cli publish` installs these dependencies from each layer's
# requirements.txt automatically (through the registry-configured pip in CodeBuild).
# The python/ dirs are git-ignored build output; this script just fills them locally.
#
# Usage:
#   cd <project-root>
#   ./enterprise/build.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Populating enterprise layer deps locally (optional; publish does this via BuildMethod)..."

# --- Ping verifier layer (PyJWT) ---
PING_LAYER_DIR="$SCRIPT_DIR/layers/ping_verifier"
echo "  Installing PyJWT into ping_verifier layer..."
pip install -q -r "$PING_LAYER_DIR/requirements.txt" \
    -t "$PING_LAYER_DIR/python/" \
    --upgrade --only-binary=:all: --platform manylinux2014_aarch64 \
    --python-version 3.12 --implementation cp
echo "  ✓ ping_verifier layer ready"

# --- Pika layer (AMQP client) ---
PIKA_LAYER_DIR="$SCRIPT_DIR/layers/pika"
mkdir -p "$PIKA_LAYER_DIR/python"
echo "  Installing pika into pika layer..."
pip install -q -r "$PIKA_LAYER_DIR/requirements.txt" \
    -t "$PIKA_LAYER_DIR/python/" \
    --upgrade --only-binary=:all: --platform manylinux2014_aarch64 \
    --python-version 3.12 --implementation cp
echo "  ✓ pika layer ready"

echo ""
echo "Done. (Local dev only — publish installs these via BuildMethod.)"
