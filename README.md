# Claw Journal 🦞

**Claw Journal** is an advanced observability and analytics skill for OpenClaw. It provides a dedicated web dashboard to track, visualize, and audit your OpenClaw usage, giving you deep insights into token consumption, costs, and agent behaviors.

> ⚠️ **Note:** Standard OpenClaw tools often hide cost metrics when using OAuth. Claw Journal aims to bridge this gap by providing local, detailed tracking for power users.

## 🚀 Features

Claw Journal runs as a local service alongside your OpenClaw instance to capture and display:

### 📊 Comprehensive Usage Analytics
- **Token Tracking:** Real-time breakdown of input/output tokens parsed directly from OpenClaw session logs.
- **Cost Observability:** Accurate cost estimation by applying model-specific pricing tables to token counts, bypassing the lack of provider billing data for OAuth users.
- **Visual Graphs:** Interactive charts showing usage trends over time (daily, weekly, monthly).
- **Forecasting:** Compare actual usage against predicted costs for different models.

### 🧠 Agent Logic & Reasoning
- **Conversation Logs:** Searchable archive of your interactions, reconstructed from session log events.
- **Thinking Process Annotation:** Visualize "Wait... thinking" blocks and internal reasoning steps often hidden in chat UIs.
- **Sub-Agent Tracking:** See exactly when and why specific sub-agents or tools (e.g., file search, terminal) were invoked.

### 🔔 Alerts & Benchmarks
- **Budget Alerts:** Receive real-time WhatsApp notifications when your daily API spend hits a defined threshold.
- **Model Benchmarking:** Track latency (TTFT) and error rates to compare performance across different LLM backends.

## 🛠️ Installation

Prerequisites:
- [OpenClaw](https://github.com/openclaw/openclaw) installed and configured.
- Python 3.9+
- Node.js (frontend planned; backend MVP is now implemented)

### 1. Clone the repository
```bash
git clone https://github.com/your-username/claw-journal.git
cd claw-journal
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure
Create a `.env` file from the example:
```bash
cp .env.example .env
```
Edit `.env` to configure your settings:
- `CJ_OPENCLAW_LOG_GLOB`: Glob path to OpenClaw logs (default: `/tmp/openclaw/openclaw-*.log`).
- `CJ_DB_PATH`: SQLite database path (default: `./data/claw_journal.db`).
- `CJ_REMOTE_ENABLED`: Enable remote-mode config validation (`true`/`false`, default `false`).
- `CJ_REMOTE_GATEWAY_URL`: Remote OpenClaw gateway URL.
- `CJ_REMOTE_GATEWAY_TOKEN`: Remote OpenClaw gateway token.
- `CJ_REMOTE_GATEWAY_AGENT_ID`: Agent ID for remote attribution context.
- `CJ_REMOTE_INGEST_MODE`: `file`, `rpc`, or `hybrid` (default: `file`).
- `CJ_REMOTE_SSH_HOST`: SSH target for read-only session sync (example: `user@your-host`).
- `CJ_REMOTE_OPENCLAW_BIN`: Path to OpenClaw binary on remote host (default: `/opt/homebrew/bin/openclaw`).
- `CJ_REMOTE_PATH_PREFIX`: Prefix added to remote `PATH` for Node/OpenClaw runtime (default: `/opt/homebrew/bin`).
- `CJ_SESSION_SYNC_ENABLED`: Enable read-only remote session sync (default: `true`).
- `CJ_SESSION_SYNC_SECONDS`: Session sync interval in seconds (default: `30`).

## 🖥️ Running (Backend MVP)

Start the local API service:

```bash
python main.py
```

Available endpoints:
- `GET /health`
- `GET /api/usage/daily?days=30`
- `GET /api/usage/sessions?limit=100`
- `GET /api/reasoning?limit=100`
- `GET /api/usage/reconciled?limit=100` (gateway session truth + observed log costs)

## ✅ Tested Safe Workflow (Remote Instance)

This project was tested in **read-only** mode against a live remote OpenClaw host via SSH tunnel:

- Verified Control UI availability at `http://localhost:18790/overview`
- Verified remote logs are readable from `/tmp/openclaw/openclaw-YYYY-MM-DD.log`
- Verified read-only gateway session access over SSH:
  - `ssh rune 'export PATH=/opt/homebrew/bin:$PATH && /opt/homebrew/bin/openclaw gateway call sessions.list --params "{}"'`
- Verified Claw Journal endpoint returns reconciled session rows using remote session truth:
  - `GET /api/usage/reconciled`

No write operations were performed on the OpenClaw instance.

## 👤 Setup Instructions for New Users

### Option A: Local OpenClaw on same machine

1. Install dependencies:
   - `python3 -m pip install -r requirements.txt`
2. Keep defaults in `.env` (or set):
   - `CJ_REMOTE_ENABLED=false`
   - `CJ_OPENCLAW_LOG_GLOB=/tmp/openclaw/openclaw-*.log`
3. Run:
   - `python3 main.py`
4. Open:
   - `http://127.0.0.1:3000/health`
   - `http://127.0.0.1:3000/api/usage/daily`

### Option B: Remote OpenClaw via SSH

1. Confirm SSH works non-interactively:
   - `ssh -o BatchMode=yes <host> 'hostname'`
2. Set `.env` values:
   - `CJ_REMOTE_ENABLED=true`
   - `CJ_REMOTE_INGEST_MODE=file`
   - `CJ_REMOTE_SSH_HOST=<host>`
   - `CJ_SESSION_SYNC_ENABLED=true`
   - `CJ_REMOTE_OPENCLAW_BIN=/opt/homebrew/bin/openclaw`
   - `CJ_REMOTE_PATH_PREFIX=/opt/homebrew/bin`
3. Choose log ingest source:
   - Mounted/forwarded logs path via `CJ_OPENCLAW_LOG_GLOB`, or leave default if local copy exists.
4. Run:
   - `python3 main.py`
5. Validate reconciliation:
   - `http://127.0.0.1:3000/api/usage/reconciled`

## TODOs

### High Priority

- [x] Add parser support for OpenClaw logger envelope fields (`0`,`1`,`2`,`_meta`,`time`) and nested usage payloads.
- [ ] Expand parser mappings for additional provider-specific token/cost keys observed in production logs.
- [ ] Add log-derived cost estimation using model pricing table when cost is absent (OAuth-safe fallback).
- [ ] Add dedupe keying for repeated log lines across rotations/restarts.
- [ ] Add redaction guardrails for sensitive values in stored `raw_json`.

### Medium Priority

- [ ] Add a background task for remote log pull (read-only) when logs are not locally mounted.
- [ ] Add API filter params (`provider`, `model`, `session_id`, date range).
- [ ] Add integration tests using captured fixture logs + mocked `sessions.list` payloads.
- [ ] Add migration/versioning for SQLite schema changes.

### Later

- [ ] Frontend dashboard (charts + search UI).
- [ ] Forecasting and benchmark views.
- [ ] Budget alerting integrations.

## 🧩 Usage with OpenClaw

Claw Journal continuously monitors your OpenClaw log files (default: `/tmp/openclaw/openclaw-YYYY-MM-DD.log`). As new entries are written, the API data updates in real-time.

1. Start your OpenClaw session (terminal or TUI).
2. Use commands like `/status` or `/usage` in OpenClaw to verify internal tracking.
3. Query `http://localhost:3000/api/usage/daily` (or other endpoints) to inspect parsed analytics, including:
   - **Session Costs:** Calculated from token usage even for OAuth providers where API cost data is hidden.
   - **Thinking Logs:** Expanded views of internal chain-of-thought not fully visible in the main chat.

## 📌 Current Status

- ✅ Analytics backend MVP scaffolded (ingest, normalize, persist, query API)
- ✅ Remote OpenClaw config contract added for hybrid integration
- ⏳ Frontend dashboard, alerts, and forecasting are planned next phases

---
*Created for the OpenClaw community.*
