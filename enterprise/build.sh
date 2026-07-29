#!/bin/bash
# Build enterprise layers (install dependencies into the layer directories).
# Run this before `sam build` / `idp-cli publish` so the layers are ready to package.
#
# Usage:
#   cd <project-root>
#   ./enterprise/build.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Determine target platform from LAMBDA_ARCHITECTURE env var (set by pipeline config)
ARCH="${LAMBDA_ARCHITECTURE:-arm64}"
if [ "$ARCH" = "x86_64" ]; then
  PIP_PLATFORM="manylinux2014_x86_64"
else
  PIP_PLATFORM="manylinux2014_aarch64"
fi

echo "Building enterprise layers (platform: $PIP_PLATFORM)..."

# --- Ping verifier layer (PyJWT) ---
PING_LAYER_DIR="$SCRIPT_DIR/layers/ping_verifier"
echo "  Installing PyJWT into ping_verifier layer..."
pip install -q -r "$PING_LAYER_DIR/requirements.txt" \
    -t "$PING_LAYER_DIR/python/" \
    --upgrade --only-binary=:all: --platform "$PIP_PLATFORM" \
    --python-version 3.12 --implementation cp
echo "  ✓ ping_verifier layer ready"

# --- STOMP layer (ActiveMQ client) ---
STOMP_LAYER_DIR="$SCRIPT_DIR/layers/pika"
mkdir -p "$STOMP_LAYER_DIR/python"
echo "  Installing stomp.py into STOMP layer..."
pip install -q -r "$STOMP_LAYER_DIR/requirements.txt" \
    -t "$STOMP_LAYER_DIR/python/" \
    --upgrade
echo "  ✓ STOMP layer ready"

echo ""
echo "Done. Layers are ready for sam build / idp-cli publish."
