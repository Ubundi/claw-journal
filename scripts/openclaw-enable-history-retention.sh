#!/usr/bin/env bash
set -euo pipefail

CONFIG_CANDIDATES=(
  "$HOME/.openclaw/openclaw.json"
  "$HOME/.config/openclaw/openclaw.json"
)

CONFIG_PATH=""
for candidate in "${CONFIG_CANDIDATES[@]}"; do
  if [[ -f "$candidate" ]]; then
    CONFIG_PATH="$candidate"
    break
  fi
done

if [[ -z "$CONFIG_PATH" ]]; then
  echo "❌ Could not find openclaw.json in expected locations."
  exit 1
fi

BACKUP_PATH="${CONFIG_PATH}.bak.$(date +%Y%m%d-%H%M%S)"
cp "$CONFIG_PATH" "$BACKUP_PATH"
echo "Backup created: $BACKUP_PATH"

python3 - <<'PY' "$CONFIG_PATH"
from __future__ import annotations

import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
payload = json.loads(config_path.read_text(encoding="utf-8"))

context_pruning = payload.get("contextPruning")
if not isinstance(context_pruning, dict):
    context_pruning = {}
    payload["contextPruning"] = context_pruning
context_pruning["mode"] = "none"

compaction = payload.get("compaction")
if not isinstance(compaction, dict):
    compaction = {}
    payload["compaction"] = compaction
memory_flush = compaction.get("memoryFlush")
if not isinstance(memory_flush, dict):
    memory_flush = {}
    compaction["memoryFlush"] = memory_flush
memory_flush["enabled"] = False

config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

print("Applied settings:")
print("- contextPruning.mode = none")
print("- compaction.memoryFlush.enabled = false")
print("- compaction.mode =", compaction.get("mode"))
PY

echo "✅ Retention-focused config update complete."
echo "   Review and restart OpenClaw for changes to take effect."
