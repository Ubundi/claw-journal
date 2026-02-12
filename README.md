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
- Node.js (for the frontend dashboard)

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
- `OPENCLAW_LOG_DIR`: Path to your OpenClaw logs (default: `/tmp/openclaw/`).
- `BUDGET_THRESHOLD`: Daily spend limit for alerts (e.g., `5.00`).
- `WHATSAPP_NUM`: Phone number for budget alerts.

## 🖥️ Running the Dashboard

Start the local server. This will launch the analytics dashboard on `http://localhost:3000`.

```bash
python main.py
```

## 🧩 Usage with OpenClaw

Claw Journal continuously monitors your OpenClaw log files (default: `/tmp/openclaw/openclaw-YYYY-MM-DD.log`). As new entries are written, the dashboard updates in real-time.

1. Start your OpenClaw session (terminal or TUI).
2. Use commands like `/status` or `/usage` in OpenClaw to verify internal tracking.
3. Open `http://localhost:3000` to see the parsed data, including:
   - **Session Costs:** Calculated from token usage even for OAuth providers where API cost data is hidden.
   - **Thinking Logs:** Expanded views of internal chain-of-thought not fully visible in the main chat.

---
*Created for the OpenClaw community.*
