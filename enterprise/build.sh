#!/bin/bash
# Build enterprise layers (install dependencies into the layer directories).
# Run this before `sam build` / `idp-cli publish` so the layers are ready to package.
#
# Usage:
#   cd <project-root>
#   ./enterprise/build.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Building enterprise layers..."

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
echo "Done. Layers are ready for sam build / idp-cli publish."
