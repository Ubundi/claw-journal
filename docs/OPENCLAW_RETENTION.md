# OpenClaw Historical Retention Runbook

Use this runbook on the OpenClaw host to verify where transcripts/logs are stored and to enable safer history retention settings.

## 1) Audit Current Storage and Config

Run:

./scripts/openclaw-history-audit.sh

This reports:
- active `openclaw.json` path
- `workspace`, `contextPruning`, `compaction`, and logging settings
- transcript JSONL candidates
- log file candidates

## 2) Enable Retention-Focused Settings

Run:

./scripts/openclaw-enable-history-retention.sh

This script:
- creates a timestamped backup of `openclaw.json`
- sets `contextPruning.mode = none`
- sets `compaction.memoryFlush.enabled = false`

## 3) Keep Logs in Durable Storage

If logs are only under `/tmp/openclaw`, move/stream them to a persistent directory and point Claw Journal at that directory with `CJ_OPENCLAW_LOG_GLOB`.

Suggested durable paths:
- `~/.openclaw/logs/`
- `/var/log/openclaw/` (if permissions and ops policy allow)

## 4) Validate from Claw Journal

After restarting OpenClaw and Claw Journal in remote mode, verify these endpoints populate historical data:
- `/api/sessions/transcripts`
- `/api/tools/summary`
- `/api/usage/sessions`
- `/api/system/logs-explorer`
