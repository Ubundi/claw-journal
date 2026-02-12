# Claw Journal 🦞

**Claw Journal** is an advanced observability and analytics skill for OpenClaw. It provides a dedicated web dashboard to track, visualize, and audit your OpenClaw usage, giving you deep insights into token consumption, costs, and agent behaviors.

> ⚠️ **Note:** Standard OpenClaw tools often hide cost metrics when using OAuth. Claw Journal aims to bridge this gap by providing local, detailed tracking for power users.

## 🚀 Features

Claw Journal runs as a local service alongside your OpenClaw instance to capture and display:

### 📊 Comprehensive Usage Analytics
- **Token Tracking:** Detailed breakdown of input/output tokens across sessions.
- **Cost Observability:** Real-time cost estimation for API Key users, with workarounds for OAuth limitations.
- **Visual Graphs:** Interactive charts showing usage trends over time (daily, weekly, monthly).
- **Forecasting:** Compare actual usage against predicted costs for different models.

### 🧠 Agent Logic & Reasoning
- **Conversation Logs:** Searchable archive of your interactions.
- **Thinking Process Annotation:** Visualize "Wait... thinking" blocks.
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
Edit `.env` to add your preferences, such as budget thresholds and notification numbers.

## 🖥️ Running the Dashboard

Start the local server. This will launch the analytics dashboard on `http://localhost:3000`.

```bash
python main.py
```

## 🧩 Usage with OpenClaw

Once running, Claw Journal listens for events from your OpenClaw session (via logs or a configured webhook). 

Simply use OpenClaw as normal. Visit the dashboard to see your metrics populate in real-time.

---
*Created for the OpenClaw community.*
