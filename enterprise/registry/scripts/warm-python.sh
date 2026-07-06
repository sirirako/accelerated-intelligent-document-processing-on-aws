#!/bin/bash
# warm-python.sh — Warm JFrog PyPI remote cache by downloading all Python packages.
#
# This triggers JFrog to fetch packages from upstream PyPI and cache them locally,
# making them available for air-gapped builds.
#
# Prerequisites:
#   - pip configured (pip.conf or PIP_INDEX_URL env var) pointing at JFrog remote/virtual repo
#   - OR pass the index URL as the second argument
#   - Run on Linux (EC2) to download the correct platform wheels for Lambda
#
# Usage:
#   ./warm-python.sh python-packages.txt
#   ./warm-python.sh python-packages.txt "https://user:token@jfrog.company.com/artifactory/api/pypi/pypi-remote/simple"

set -euo pipefail

MANIFEST="${1:-python-packages.txt}"
INDEX_URL="${2:-}"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: Manifest not found: $MANIFEST"
    echo "Generate it with: make dep-manifest"
    exit 1
fi

TEMP_DIR=$(mktemp -d /tmp/warm-python-XXXX)
trap "rm -rf $TEMP_DIR" EXIT

INDEX_ARG=""
if [[ -n "$INDEX_URL" ]]; then
    INDEX_ARG="--index-url $INDEX_URL"
fi

TOTAL=$(grep -c '\S' "$MANIFEST" || echo 0)
SUCCESS=0
FAILED=0
SKIPPED=0
FAIL_FILE="python-warm-failures.txt"
> "$FAIL_FILE"

echo "=== Warming $TOTAL Python packages ==="
echo "Temp dir: $TEMP_DIR"
echo ""

i=0
while IFS= read -r pkg; do
    [[ -z "$pkg" || "$pkg" == \#* ]] && continue
    i=$((i + 1))
    pct=$((i * 100 / TOTAL))
    printf "[%3d%%] (%d/%d) %-50s " "$pct" "$i" "$TOTAL" "$pkg"

    if pip download --no-deps --dest "$TEMP_DIR" $INDEX_ARG "$pkg" >/dev/null 2>&1; then
        echo "OK"
        SUCCESS=$((SUCCESS + 1))
    else
        echo "FAILED"
        FAILED=$((FAILED + 1))
        echo "$pkg" >> "$FAIL_FILE"
    fi
done < "$MANIFEST"

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
    echo "  - Package version exists on pypi.org"
    echo "  - Network connectivity from JFrog to upstream pypi.org"
fi
