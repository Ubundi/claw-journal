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
  echo "❌ Could not find openclaw.json in expected locations:"
  for candidate in "${CONFIG_CANDIDATES[@]}"; do
    echo "   - $candidate"
  done
  exit 1
fi

echo "== OpenClaw Config =="
echo "Config file: $CONFIG_PATH"

echo
python3 - <<'PY' "$CONFIG_PATH"
from __future__ import annotations

import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
payload = json.loads(config_path.read_text(encoding="utf-8"))

workspace = payload.get("workspace")
context_pruning = payload.get("contextPruning") if isinstance(payload.get("contextPruning"), dict) else {}
compaction = payload.get("compaction") if isinstance(payload.get("compaction"), dict) else {}
memory_flush = compaction.get("memoryFlush") if isinstance(compaction.get("memoryFlush"), dict) else {}
logging_cfg = payload.get("logging") if isinstance(payload.get("logging"), dict) else {}

print("workspace:", workspace)
print("contextPruning.mode:", context_pruning.get("mode"))
print("compaction.mode:", compaction.get("mode"))
print("compaction.memoryFlush.enabled:", memory_flush.get("enabled"))
print("logging.level:", logging_cfg.get("level"))
print("logging.redactSensitive:", logging_cfg.get("redactSensitive"))
PY

echo
echo "== Session Transcript Candidates =="

WORKSPACE_PATH=$(python3 - <<'PY' "$CONFIG_PATH"
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
payload = json.loads(config_path.read_text(encoding="utf-8"))
workspace = payload.get("workspace")
if isinstance(workspace, str) and workspace.strip():
    print(os.path.expanduser(workspace.strip()))
else:
    print("")
PY
)

if [[ -n "$WORKSPACE_PATH" ]]; then
  echo "Workspace from config: $WORKSPACE_PATH"
fi

mapfile -t SESSION_GLOBS < <(printf '%s\n' \
  "$HOME/.openclaw/agents/*/sessions/*.jsonl" \
  "$HOME/.openclaw/workspace/agents/*/sessions/*.jsonl" \
  "$WORKSPACE_PATH/agents/*/sessions/*.jsonl")

for pattern in "${SESSION_GLOBS[@]}"; do
  [[ -z "$pattern" ]] && continue
  count=$(ls -1 $pattern 2>/dev/null | wc -l | tr -d ' ' || true)
  echo "- $pattern"
  echo "  files: $count"
  if [[ "$count" != "0" ]]; then
    ls -1t $pattern 2>/dev/null | head -n 3 | sed 's/^/  sample: /'
  fi
done

echo
echo "== OpenClaw Log Candidates =="
mapfile -t LOG_GLOBS < <(printf '%s\n' \
  "/tmp/openclaw/openclaw-*.log" \
  "$HOME/.openclaw/logs/*.log" \
  "$HOME/Library/Logs/openclaw/*.log" \
  "$WORKSPACE_PATH/logs/*.log")

for pattern in "${LOG_GLOBS[@]}"; do
  [[ -z "$pattern" ]] && continue
  count=$(ls -1 $pattern 2>/dev/null | wc -l | tr -d ' ' || true)
  echo "- $pattern"
  echo "  files: $count"
  if [[ "$count" != "0" ]]; then
    ls -1t $pattern 2>/dev/null | head -n 3 | sed 's/^/  sample: /'
  fi
done

echo
echo "== Notes =="
echo "- If logs are only under /tmp/openclaw, history may be lost on reboot/cleanup."
echo "- Persist logs to a durable folder and set CJ_OPENCLAW_LOG_GLOB to that path on Claw Journal."
echo "- Keep transcript JSONL files for full Sessions/Tools backfill on new machines."
