#!/bin/bash
# warm-node.sh — Warm JFrog npm remote cache by downloading all Node packages.
#
# This triggers JFrog to fetch packages from upstream npmjs.org and cache them
# locally, making them available for air-gapped builds.
#
# Prerequisites:
#   - .npmrc configured pointing at JFrog remote/virtual npm repo
#   - Can run on any OS (Node packages are platform-agnostic)
#
# Usage:
#   ./warm-node.sh node-packages.txt

set -euo pipefail

MANIFEST="${1:-node-packages.txt}"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: Manifest not found: $MANIFEST"
    echo "Generate it with: make dep-manifest"
    exit 1
fi

TEMP_DIR=$(mktemp -d /tmp/warm-node-XXXX)
trap "rm -rf $TEMP_DIR" EXIT

TOTAL=$(grep -c '\S' "$MANIFEST" || echo 0)
SUCCESS=0
FAILED=0
FAIL_FILE="node-warm-failures.txt"
> "$FAIL_FILE"

echo "=== Warming $TOTAL Node packages ==="
echo "Temp dir: $TEMP_DIR"
echo ""

cd "$TEMP_DIR"
i=0
while IFS= read -r pkg; do
    [[ -z "$pkg" || "$pkg" == \#* ]] && continue
    i=$((i + 1))
    pct=$((i * 100 / TOTAL))
    printf "[%3d%%] (%d/%d) %-50s " "$pct" "$i" "$TOTAL" "$pkg"

    if npm pack "$pkg" >/dev/null 2>&1; then
        echo "OK"
        SUCCESS=$((SUCCESS + 1))
    else
        echo "FAILED"
        FAILED=$((FAILED + 1))
        echo "$pkg" >> "$OLDPWD/$FAIL_FILE"
    fi
done < "$OLDPWD/$MANIFEST"
cd "$OLDPWD"

echo ""
echo "=== Summary ==="
echo "Total:   $TOTAL"
echo "Success: $SUCCESS"
echo "Failed:  $FAILED"
if [[ $FAILED -gt 0 ]]; then
    echo ""
    echo "Failed packages saved to: $FAIL_FILE"
    echo "Re-run this script to retry (cached packages return instantly)."
    echo ""
    echo "If failures persist, check:"
    echo "  - JFrog remote repo metadata cache (ask admin to 'Zap Caches')"
    echo "  - Package version exists on npmjs.org"
    echo "  - .npmrc auth token is valid and has read access to the remote repo"
    echo "  - For SELF_SIGNED_CERT_IN_CHAIN: set strict-ssl=false in .npmrc or"
    echo "    export NODE_EXTRA_CA_CERTS=/path/to/corporate-ca.crt"
fi
