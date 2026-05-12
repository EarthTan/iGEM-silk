#!/bin/bash
# =============================================================================
# Download TemStaPro classifier models (~80 MB, 30 .pt files)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODELS_DIR="$SCRIPT_DIR/models"

echo "Downloading TemStaPro classifier models …"
echo "Target: $MODELS_DIR"
echo ""

# Sparse clone of the TemStaPro repo (models/ directory only)
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

git clone --depth 1 --filter=blob:none --sparse \
    https://github.com/ievapudz/TemStaPro.git "$TMP_DIR"

cd "$TMP_DIR"
git sparse-checkout set models

# Copy .pt files
count=$(ls models/*.pt 2>/dev/null | wc -l | tr -d ' ')
cp models/*.pt "$MODELS_DIR/"

echo ""
echo "Done — $count classifier files copied to $MODELS_DIR"
echo ""
echo "Next steps:"
echo "  cd tools/TemStaPro && uv sync --all-extras"
echo "  python service.py"
