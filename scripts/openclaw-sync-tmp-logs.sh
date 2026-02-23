#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="${OPENCLAW_TMP_LOG_DIR:-/tmp/openclaw}"
DEST_DIR="${OPENCLAW_PERSISTENT_LOG_DIR:-$HOME/.openclaw/logs/history}"
PATTERN="${OPENCLAW_TMP_LOG_PATTERN:-openclaw-*.log}"

mkdir -p "$DEST_DIR"

# Copy if newer while preserving metadata.
for src in "$SRC_DIR"/$PATTERN; do
  [[ -e "$src" ]] || continue
  cp -p "$src" "$DEST_DIR/"
done

# Optional lightweight index to aid diagnostics.
INDEX_PATH="$DEST_DIR/.index.txt"
{
  echo "generated_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  ls -1 "$DEST_DIR"/$PATTERN 2>/dev/null | sed 's/^/file=/' || true
} > "$INDEX_PATH"
