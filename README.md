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
- `CJ_SNAPSHOT_BACKFILL_ENABLED`: Backfill usage history from session snapshots when logs are sparse (default: `true`).
- `CJ_SNAPSHOT_BACKFILL_SECONDS`: Snapshot backfill interval in seconds (default: `10`).
- `CJ_COST_ESTIMATION_ENABLED`: Estimate cost when logs contain tokens but no cost (default: `true`).
- `CJ_PRICING_FILE`: Pricing table JSON path (default: `./pricing.json`).
- `CJ_OPENROUTER_SYNC_ENABLED`: Auto-fetch model catalog + pricing from OpenRouter on startup (default: `true`).
- `CJ_OPENROUTER_MODELS_URL`: OpenRouter models endpoint (default: `https://openrouter.ai/api/v1/models`).
- `CJ_OPENROUTER_TIMEOUT_SECONDS`: OpenRouter request timeout (default: `8`).
- `CJ_REDACTION_ENABLED`: Redact sensitive keys/tokens before storing `raw_json` (default: `true`).
- `CJ_AUTH_MODE`: `auto`, `oauth`, or `api_key` (default: `auto`).
- `CJ_BILLING_MODE`: `token` or `claude_max` (default: `token`).
- `CJ_CLAUDE_MAX_MONTHLY_USD`: Monthly Claude Max subscription amount used for dashboard context (default: `200`).
- `CJ_AUTO_PORT`: Automatically bind the first available local port starting at `CJ_PORT` (default: `true`).
- `CJ_PORT_SEARCH_LIMIT`: Number of incremental ports to try after `CJ_PORT` when occupied (default: `50`).

## 🖥️ Running (Backend MVP)

Start the local API service:

```bash
python3 main.py
```

On startup, Claw Journal logs the active dashboard URL (for example `Dashboard available at http://127.0.0.1:3002`).
With `CJ_AUTO_PORT=true`, backend + embedded frontend always stay on the same selected port.

Available endpoints:
- `GET /health`
- `GET /api/usage/daily?days=30`
- `GET /api/usage/sessions?limit=100`
- `GET /api/reasoning?limit=100`
- `GET /api/usage/reconciled?limit=100` (gateway session truth + observed log costs)
- `GET /api/usage/cost-sources` (observed vs estimated vs missing cost counts)
- `GET /api/system/profile` (auth mode, billing mode, data-source diagnostics, notes)
- `GET /api/system/models` (OpenRouter available models + models currently used by OpenClaw)
- `GET /api/system/token-accuracy` (snapshot vs backfilled token accuracy by session)
- `GET /api/usage/session/{session_id}` (click-through event detail with extracted human text + raw JSON)
- `GET /api/pricing` and `POST /api/pricing/upsert` (auto-loaded pricing plus manual override)
- `GET /api/usage/plan-cost` (Claude Max plan summary when enabled)

## 🚀 Quick Start: Connect to Remote OpenClaw

If you have OpenClaw running on a remote server (e.g., a host named `rune`) and want to view the journal locally:

### 1. Prerequisite: SSH Access
Ensure you can SSH into your remote host without a password prompt (using keys):
```bash
ssh -o BatchMode=yes rune 'hostname'
# Should print "rune" or the hostname without asking for a password
```

### 2. Run Claw Journal (Remote Mode)
Run the following command locally. This connects to `rune` to sync session totals via SSH.

```bash
# Replace 'rune' with your host alias if different
CJ_REMOTE_ENABLED=true \
CJ_REMOTE_SSH_HOST=rune \
python3 main.py
```

*Optional: To see full conversation logs (thinking steps), copy logs from remote:*
```bash
ssh user@your-host 'cat /tmp/openclaw/openclaw-*.log' > /tmp/openclaw-remote.log
CJ_OPENCLAW_LOG_GLOB=/tmp/openclaw-remote.log python3 main.py
```

### 3. View Dashboard
Open the URL printed in startup logs (`Dashboard available at ...`) in your local browser.

> **Note:** This mode syncs session history from the remote `openclaw` instance every 30 seconds and streams logs as they are written. It does NOT modify your remote instance.

## 👥 Setup Instructions (Detailed)

### Option A: Local OpenClaw (Same Machine)

If OpenClaw is running on the same computer:

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Review configuration (optional):**
   - The default `.env` assumes logs are at `/tmp/openclaw/openclaw-*.log`.
3. **Run:**
   ```bash
   python3 main.py
   ```
4. **Open:**
   - Open the `Dashboard available at ...` URL printed on startup

### Option B: Remote OpenClaw via SSH (Advanced)

If you need more control than the Quick Start provides, you can configure `.env` persistently:

1. **Copy example config:**
   ```bash
   cp .env.example .env
   ```
2. **Edit `.env`:**
   ```bash
   CJ_REMOTE_ENABLED=true
   CJ_REMOTE_SSH_HOST=rune  # Replace with your host
   CJ_SESSION_SYNC_ENABLED=true
   # Optional: Path to OpenClaw binary on remote
   CJ_REMOTE_OPENCLAW_BIN=/opt/homebrew/bin/openclaw
   ```
3. **Run:**
   ```bash
   python3 main.py
   ```

### Pricing file format

`pricing.json` uses provider/model keys with USD-per-1M-token rates:

```json
{
   "anthropic/claude-opus-4-5": {
      "input_per_million": 15.0,
      "output_per_million": 75.0
   }
}
```

## TODOs

### High Priority

- [x] Add parser support for OpenClaw logger envelope fields (`0`,`1`,`2`,`_meta`,`time`) and nested usage payloads.
- [ ] Expand parser mappings for additional provider-specific token/cost keys observed in production logs.
- [x] Add log-derived cost estimation using model pricing table when cost is absent (OAuth-safe fallback).
- [x] Add dedupe keying for repeated log lines across rotations/restarts.
- [x] Add redaction guardrails for sensitive values in stored `raw_json`.

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
3. Query `http://localhost:<active-port>/api/usage/daily` (or other endpoints) to inspect parsed analytics, including:
   - **Session Costs:** Calculated from token usage even for OAuth providers where API cost data is hidden.
   - **Thinking Logs:** Expanded views of internal chain-of-thought not fully visible in the main chat.

## 📌 Current Status

- ✅ Analytics backend MVP scaffolded (ingest, normalize, persist, query API)
- ✅ Remote OpenClaw config contract added for hybrid integration
- ⏳ Frontend dashboard, alerts, and forecasting are planned next phases

---
*Created for the OpenClaw community.*
