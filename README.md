# Claw Journal 🦞

**Claw Journal** is an advanced observability and analytics skill for OpenClaw. It provides a dedicated web dashboard to track, visualize, and audit your OpenClaw usage, giving you deep insights into token consumption, costs, and agent behaviors.

> ⚠️ **Note:** Standard OpenClaw tools often hide cost metrics when using OAuth. Claw Journal aims to bridge this gap by providing local, detailed tracking for power users.

## ⚡ Recommended Startup (.env + one command)

Use `.env` + one script instead of manually juggling 4 terminals.

### 1) Create `.env` from template
```bash
cp .env.example .env
```

### 2) Set profile values in `.env`

**Local OpenClaw profile (same machine):**

Required:
- `CJ_REMOTE_ENABLED=false`
- `CJ_OPENCLAW_LOG_GLOB=/tmp/openclaw/openclaw-*.log`

Recommended:
- `CJ_PORT=3000`
- `CJ_FRONTEND_PORT=5173`

Not needed for local profile:
- `CJ_REMOTE_SSH_HOST`
- `CJ_REMOTE_GATEWAY_URL`
- `CJ_REMOTE_GATEWAY_TOKEN`
- `CJ_REMOTE_GATEWAY_AGENT_ID`

**Remote OpenClaw profile (SSH):**

Required:
- `CJ_REMOTE_ENABLED=true`
- `CJ_REMOTE_SSH_HOST=user@your-host`

Recommended:
- `CJ_PORT=3000`
- `CJ_FRONTEND_PORT=5173`
- `CJ_REMOTE_INGEST_MODE=file`

Not needed for remote `file` ingest profile:
- `CJ_REMOTE_GATEWAY_URL`
- `CJ_REMOTE_GATEWAY_TOKEN`
- `CJ_REMOTE_GATEWAY_AGENT_ID`

Only needed when using `CJ_REMOTE_INGEST_MODE=rpc` or `hybrid`:
- `CJ_REMOTE_GATEWAY_URL`
- `CJ_REMOTE_GATEWAY_TOKEN`
- `CJ_REMOTE_GATEWAY_AGENT_ID`

### 3) Run one command
```bash
chmod +x scripts/start-dashboard.sh
chmod +x scripts/stop-dashboard.sh
./scripts/start-dashboard.sh
```

Stop services:

```bash
./scripts/stop-dashboard.sh
```

Open:
- Claw Journal: `http://127.0.0.1:${CJ_FRONTEND_PORT:-5173}`
- Chat History: `http://127.0.0.1:${CJ_FRONTEND_PORT:-5173}/chat`
- Memory Explorer: `http://127.0.0.1:${CJ_FRONTEND_PORT:-5173}/memory`

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
- [uv](https://docs.astral.sh/uv/) installed
- Node.js 18+

### 1. Clone the repository
```bash
git clone https://github.com/Ubundi/claw-journal.git
cd claw-journal
```

### 2. Install Dependencies
```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

cd frontend
npm install
cd ..
```

### 3. Configure
Use `.env` as the default startup contract (recommended):

```bash
cp .env.example .env
```

Minimal local `.env`:
```bash
CJ_REMOTE_ENABLED=false
CJ_PORT=3000
CJ_FRONTEND_PORT=5173
```

Minimal remote `.env` (file ingest over SSH):
```bash
CJ_REMOTE_ENABLED=true
CJ_REMOTE_SSH_HOST=user@your-host
CJ_PORT=3000
CJ_FRONTEND_PORT=5173
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
- `CJ_TRANSCRIPT_SYNC_ENABLED`: Enable transcript ingestion for full chat history (default: `true`).
- `CJ_TRANSCRIPT_SYNC_SECONDS`: Transcript sync interval in seconds (default: `45`).
- `CJ_TRANSCRIPT_GLOB`: Local transcript glob (default: `~/.openclaw/agents/*/sessions/*.jsonl`).
- `CJ_REMOTE_TRANSCRIPT_GLOB`: Remote transcript glob used over SSH (default: `~/.openclaw/agents/*/sessions/*.jsonl`).
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
- `CJ_FRONTEND_PORT`: Vite dev server port used by `scripts/start-dashboard.sh` (default: `5173`).
- `CJ_STARTUP_HEALTHCHECK_ENABLED`: Run an automatic self-check at startup for `/health` + `/api/system/connection` (default: `true`).
- `CJ_STARTUP_HEALTHCHECK_TIMEOUT_SECONDS`: Max wait for startup self-check before failing fast (default: `20`).

## 🖥️ Running (API + Graph Dashboard)

Use the script-based flow:

```bash
./scripts/start-dashboard.sh
```

This launches backend + frontend together, loads `.env`, auto-picks a free API port if `CJ_PORT` is busy, and points Vite proxy at the selected API target.

### How ports work

- **Claw Journal API port (`CJ_PORT`)**: FastAPI backend port (default `3000`).
- **Claw Journal frontend port (`CJ_FRONTEND_PORT`)**: Vite UI port (default `5173`).
- **Vite API proxy**: frontend `/api/*` requests are proxied to `CJ_API_TARGET` (set by script).
- **OpenClaw Control UI port**: typically `18790` on OpenClaw side.
- **SSH tunnel local port**: your local mapping for remote Control UI (for example `18791:localhost:18790`).

### Multi-remote and conflict behavior

- **Remote OpenClaw ports are not bound locally**: Claw Journal reads remote logs/sessions over SSH, so it does not reserve remote API ports on your local machine.
- **Each local device uses its own local ports**: every laptop/workstation running Claw Journal binds its own local `CJ_PORT` and `CJ_FRONTEND_PORT` only.
- **Multiple remote instances are isolated by `.env`**: point each run to a specific `CJ_REMOTE_SSH_HOST` (and optional remote ingest settings) to track different remote OpenClaw instances.
- **No local conflict on same machine**: if `CJ_PORT` is busy, `start-dashboard.sh` auto-selects the next free API port and updates frontend proxy target automatically.
- **Control UI tunnel conflicts**: if `18790`/`18791` is busy locally, pick another local tunnel port while keeping remote side on `18790`.

Example for two remote instances from the same local machine:

```bash
# remote A profile
cp .env .env.remote-a

# remote B profile
cp .env .env.remote-b

# run A
cp .env.remote-a .env
./scripts/start-dashboard.sh

# run B in another clone/worktree with different local ports
# (for example CJ_PORT=3010, CJ_FRONTEND_PORT=5180)
```

### Quick health checks

After startup, verify both backend and proxy paths:

```bash
curl -sS http://127.0.0.1:3000/health
curl -sS http://127.0.0.1:5173/api/dashboard-data | head -c 200
```

If script selected a non-3000 API port, use the printed backend URL from script output.

### Manual port troubleshooting

Find an open port in a range:

```bash
for p in $(seq 3000 3050); do
   lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null || { echo "open port: $p"; break; }
done
```

Inspect what process is using a port:

```bash
lsof -nP -iTCP:3000 -sTCP:LISTEN
```

Stop process hogging a port (manual):

```bash
# graceful stop first
lsof -ti tcp:3000 | xargs kill

# force kill only if still stuck
lsof -ti tcp:3000 | xargs kill -9
```

Expected backend health response:

```json
{"status":"ok"}
```

> Use the React UI in `frontend` as the dashboard.

Open chat history at `http://localhost:5173/chat`.

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
- `GET /api/chat/sessions?limit=100&offset=0` (historical chat session list from transcripts)
- `GET /api/chat/session/{session_id}?limit=300&before_id=<id>` (full conversation messages with pagination)
- `GET /api/pricing` and `POST /api/pricing/upsert` (auto-loaded pricing plus manual override)
- `GET /api/usage/plan-cost` (Claude Max plan summary when enabled)

## 🚀 Quick Start: Connect to Remote OpenClaw

If you have OpenClaw running on a remote server and want to view the journal locally:

### 1. Prerequisite: SSH Access
Ensure you can SSH into your remote host directly (without relying on SSH config aliases):
```bash
REMOTE_SSH_HOST="user@your-host"
ssh -o BatchMode=yes "$REMOTE_SSH_HOST" 'hostname'
# Should print the hostname without asking for a password
```

### 2. Run Claw Journal API (Remote Mode)
Set `.env` for remote mode and run the script.

```bash
cat > .env <<'EOF'
CJ_REMOTE_ENABLED=true
CJ_REMOTE_SSH_HOST=user@your-host
CJ_REMOTE_INGEST_MODE=file
CJ_PORT=3000
CJ_FRONTEND_PORT=5173
EOF

./scripts/start-dashboard.sh
```

*Optional: To see full conversation logs (thinking steps), copy logs from remote:*
```bash
ssh user@your-host 'cat /tmp/openclaw/openclaw-*.log' > /tmp/openclaw-remote.log
CJ_OPENCLAW_LOG_GLOB=/tmp/openclaw-remote.log uv run python main.py
```

### 3. View Dashboard
Open `http://127.0.0.1:5173` in your local browser.

For full conversation transcripts, open `http://127.0.0.1:5173/chat`.

> **Note:** This mode syncs session history from the remote `openclaw` instance every 30 seconds and streams logs as they are written. It does NOT modify your remote instance.

## 👥 Setup Instructions (Detailed)

### Option A: Local OpenClaw (Same Machine)

If OpenClaw is running on the same computer:

1. **Install dependencies:**
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -r requirements.txt

   cd frontend
   npm install
   cd ..
   ```
2. **Review configuration (optional):**
   - The default `.env` assumes logs are at `/tmp/openclaw/openclaw-*.log`.
3. **Run API (Terminal 1):**
   ```bash
   uv run python main.py
   ```
4. **Run dashboard (Terminal 2):**
   ```bash
   cd frontend
   npm run dev
   ```
5. **Open:**
   - Open `http://localhost:5173`

### Option B: Remote OpenClaw via SSH (Advanced)

If you need more control than the Quick Start provides, you can configure `.env` persistently:

1. **Create `.env`:**
   ```bash
   touch .env
   ```
2. **Edit `.env`:**
   ```bash
   # Use explicit user@host, not an SSH alias
   CJ_REMOTE_ENABLED=true
   CJ_REMOTE_SSH_HOST=user@your-host
   CJ_SESSION_SYNC_ENABLED=true
   # Optional: Path to OpenClaw binary on remote
   CJ_REMOTE_OPENCLAW_BIN=/opt/homebrew/bin/openclaw
   ```
3. **Run API (Terminal 1):**
   ```bash
   uv run python main.py
   ```
4. **Run dashboard (Terminal 2):**
   ```bash
   cd frontend
   npm run dev
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
- [x] Add migration/versioning for SQLite schema changes.


### Later

- [ ] Expand dashboard chart/search views.
- [ ] Forecasting and benchmark views.
- [ ] Budget alerting integrations.

## 🧩 Usage with OpenClaw

Claw Journal continuously monitors your OpenClaw log files (default: `/tmp/openclaw/openclaw-YYYY-MM-DD.log`). As new entries are written, the API data updates in real-time.

1. Start your OpenClaw session (terminal or TUI).
2. Use commands like `/status` or `/usage` in OpenClaw to verify internal tracking.
3. Query `http://localhost:<active-port>/api/usage/daily` (or other endpoints) to inspect parsed analytics, including:
   - **Session Costs:** Calculated from token usage even for OAuth providers where API cost data is hidden.
   - **Thinking Logs:** Expanded views of internal chain-of-thought not fully visible in the main chat.

## 🔑 OpenClaw Control UI Access (Token + Port + SSH Tunnel)

Use this flow when you need local access to a remote OpenClaw Control endpoint.

> ⚠️ **Security warning:** treat gateway tokens like passwords. Do not paste token values into shared terminals, ticket comments, chat logs, screenshots, or recordings.

1. **Read your OpenClaw token securely (local or remote host where OpenClaw runs):**
   ```bash
   read -r -s -p "OpenClaw gateway token: " OPENCLAW_GATEWAY_TOKEN && echo
   ```

2. **Set a unique local gateway port (example uses `18791`):**
   ```bash
   PORT=18791
   sed -i '' "s/\"port\": 18789/\"port\": $PORT/" ~/.openclaw/openclaw.json
   ```

3. **Point CLI/TUI to the selected gateway port:**
   ```bash
   export OPENCLAW_GATEWAY_URL="ws://127.0.0.1:<my_port>"
   openclaw tui --token "$OPENCLAW_GATEWAY_TOKEN"
   unset OPENCLAW_GATEWAY_TOKEN
   ```

4. **Create SSH tunnel for remote control port (explicit `user@host`, no SSH config needed):**
   ```bash
   ssh -L 18790:localhost:18790 user@your-host
   ```

5. **If tunneling fails with `Address already in use`, that local port is already taken (possibly by another user/process). Use a different local port:**
   ```bash
   lsof -nP -iTCP:18790 -sTCP:LISTEN
   # keep remote side at 18790, but choose a new local port (e.g. 18791):
   LOCAL_TUNNEL_PORT=18791
   ssh -L ${LOCAL_TUNNEL_PORT}:localhost:18790 user@your-host
   ```

6. **Open in browser:**
   - OpenClaw Control UI: `http://localhost:18790` (or `http://localhost:${LOCAL_TUNNEL_PORT}` if remapped)
   - Claw Journal dashboard: `http://localhost:5173`

## 🛟 Troubleshooting Blank Claw Journal UI

If `http://localhost:5173` opens but appears stuck with no console errors, check this sequence:

```bash
# 1) Ensure only one backend and one frontend process are listening
lsof -nP -iTCP:3000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN

# 2) Verify backend responds quickly
curl -sS -m 5 http://127.0.0.1:3000/health

# 3) Verify frontend proxy reaches backend
curl -sS -m 8 http://127.0.0.1:5173/api/dashboard-data | head -c 200
```

If needed, reset both ports and restart cleanly:

```bash
lsof -ti tcp:3000 | xargs kill -9
lsof -ti tcp:5173 | xargs kill -9
```

The startup health check now fails fast if the API never becomes responsive during startup.

## 📌 Current Status

- ✅ Analytics backend MVP scaffolded (ingest, normalize, persist, query API)
- ✅ React graph dashboard available in `frontend/`
- ✅ Remote OpenClaw config contract added for hybrid integration
- ⏳ Alerts and forecasting are planned next phases

---
*Created for the OpenClaw community.*
