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
- Python 3.10+
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
- `CJ_REMOTE_ENABLED`: Enable remote-mode config validation (`true`/`false`).
- `CJ_REMOTE_GATEWAY_URL`: Remote OpenClaw gateway URL.
- `CJ_REMOTE_GATEWAY_TOKEN`: Remote OpenClaw gateway token.
- `CJ_REMOTE_GATEWAY_AGENT_ID`: Agent ID for remote attribution context.
- `CJ_REMOTE_INGEST_MODE`: `file`, `rpc`, or `hybrid` (default: `hybrid`).

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
