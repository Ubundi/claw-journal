# OpenClaw Historical Retention Runbook

Use this runbook on the OpenClaw host to verify where transcripts/logs are stored and to enable safer history retention settings.

## Goal: Single Source of Truth on the OpenClaw Host

For remote usage, treat the OpenClaw host as the canonical history source.

- **Source of truth**: OpenClaw transcript files + durable OpenClaw logs on the host.
- **Local Claw Journal DB**: cache/derived index only (`claw_journal.db` can be recreated).
- **Expected outcome**: deleting/recloning Claw Journal on any remote client still backfills full history from the host.

Claw Journal now supports enforcing this on remote runs:

- `CJ_ENSURE_DURABLE_LOGS=true` (enabled by default by `scripts/start-dashboard.sh` when `CJ_REMOTE_ENABLED=true`)
- startup fails fast if `CJ_OPENCLAW_LOG_GLOB` points at temporary paths like `/tmp/...`

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
- sets `compaction.memoryFlush.enabled = false`

> Note: newer OpenClaw schemas store compaction settings under `agents.defaults.*`; the script auto-detects schema.
> `contextPruning` options are schema/version-specific and are intentionally left unchanged by default.

## 3) Keep Logs in Durable Storage

If logs are only under `/tmp/openclaw`, move/stream them to a persistent directory and point Claw Journal at that directory with `CJ_OPENCLAW_LOG_GLOB`.

Suggested durable paths:
- `~/.openclaw/logs/`
- `/var/log/openclaw/` (if permissions and ops policy allow)

### Optional automation (recommended on macOS host)

Install periodic `/tmp/openclaw` -> persistent sync with launchd:

```bash
./scripts/install-openclaw-log-sync-launchd.sh
```

This installs:
- sync worker: `scripts/openclaw-sync-tmp-logs.sh`
- launchd agent: `~/Library/LaunchAgents/io.ubundi.openclaw-log-sync.plist`
- destination: `~/.openclaw/logs/history/openclaw-*.log`

Set optional sync cadence before install (seconds):

```bash
export CJ_LOG_SYNC_INTERVAL=120
```

Set Claw Journal to use durable logs:

```bash
CJ_OPENCLAW_LOG_GLOB=/Users/<user>/.openclaw/logs/history/openclaw-*.log
```

And enforce durable path checks for remote mode:

```bash
CJ_ENSURE_DURABLE_LOGS=true
```

## 4) Clean Remote Setup Flow (Repeatable)

Use this when onboarding a new machine or after deleting/recloning Claw Journal:

1. On OpenClaw host, run audit:
	- `./scripts/openclaw-history-audit.sh`
2. Apply retention-focused compaction settings:
	- `./scripts/openclaw-enable-history-retention.sh`
3. Install durable log sync automation:
	- `./scripts/install-openclaw-log-sync-launchd.sh`
4. Ensure Claw Journal `.env` for remote mode includes:
	- `CJ_REMOTE_ENABLED=true`
	- `CJ_REMOTE_SSH_HOST=<host>`
	- `CJ_OPENCLAW_LOG_GLOB=/Users/<user>/.openclaw/logs/history/openclaw-*.log`
	- `CJ_ENSURE_DURABLE_LOGS=true`
5. Start Claw Journal and allow initial backfill.

## 5) Validate from Claw Journal

After restarting OpenClaw and Claw Journal in remote mode, verify these endpoints populate historical data:
- `/api/sessions/transcripts`
- `/api/tools/summary`
- `/api/usage/sessions`
- `/api/system/logs-explorer`
