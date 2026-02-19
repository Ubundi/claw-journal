# Claw Journal 🦞

> Local observability dashboard for OpenClaw — track tokens, costs, and agent reasoning without cloud dependencies.

![GitHub stars](https://img.shields.io/github/stars/Ubundi/claw-journal?style=social)
![GitHub license](https://img.shields.io/github/license/Ubundi/claw-journal)
![GitHub issues](https://img.shields.io/github/issues/Ubundi/claw-journal)
![GitHub last commit](https://img.shields.io/github/last-commit/Ubundi/claw-journal)

![Claw Journal Demo](./docs/demo.gif)

**Claw Journal** is an advanced observability and analytics skill for OpenClaw. It provides a dedicated web dashboard to track, visualize, and audit your OpenClaw usage with local-first data collection.

> ⚠️ **Note:** Standard OpenClaw tools often hide cost metrics when using OAuth. Claw Journal aims to bridge this gap by providing local, detailed tracking for power users.

## Why Claw Journal?

- **See actual spend:** Token and cost tracking even when provider billing data is hidden.
- **Audit agent behavior:** Session-level reasoning and tool invocation visibility.
- **Stay local-first:** Data collection and storage run on your own machine.

## ⚡ Quick Start

### Option A: Local (Same Machine)

If OpenClaw runs on this computer:

1. **Configure:** Copy and check defaults.
   ```bash
   cp .env.example .env
   # Default assumes logs at /tmp/openclaw/openclaw-*.log
   ```
2. **Run:** Start the dashboard.
   ```bash
   ./scripts/start-dashboard.sh
   ```

### Option B: Remote (Over SSH)

If OpenClaw runs on a server/VM and you want the dashboard locally:

1. **Check SSH:** Ensure you can connect without a password prompt.
   ```bash
   ssh user@your-host "echo connected"
   ```

2. **Configure:** Create `.env` pointing to the remote host.
   ```bash
   # Create .env with remote settings
   cat > .env <<EOF
   CJ_REMOTE_ENABLED=true
   CJ_REMOTE_SSH_HOST=user@your-host
   CJ_REMOTE_INGEST_MODE=file
   CJ_PORT=3000
   CJ_FRONTEND_PORT=5173
   EOF
   ```

3. **Run:**
   ```bash
   ./scripts/start-dashboard.sh
   ```

- **Dashboard:** `http://localhost:5173`
- **Chat History:** `http://localhost:5173/chat`

---

## 🚀 Features

Claw Journal runs as a local service alongside your OpenClaw instance to capture and display:

### 📊 Comprehensive Usage Analytics
- **Token Tracking:** Real-time breakdown of input/output tokens parsed directly from OpenClaw session logs.
- **Cost Observability:** Accurate cost estimation even for OAuth providers where API cost data is hidden.
- **Visual Graphs:** Interactive charts showing usage trends over time.

### 🧠 Agent Logic & Reasoning
- **Conversation Logs:** Searchable archive of your interactions.
- **Thinking Process Annotation:** Visualize "Wait... thinking" blocks and internal reasoning steps.
- **Sub-Agent Tracking:** See when specific sub-agents or tools were invoked.

---

## 📚 Documentation

<details>
<summary><strong>Installing & Configuring</strong></summary>

Full setup instructions, including manual installation steps and detailed `.env` reference.

[View Installation Guide](./docs/INSTALLATION.md)
</details>

<details>
<summary><strong>Remote Access (SSH)</strong></summary>

How to connect to a remote OpenClaw instance or tunnel the Control UI.

[View Remote Access Guide](./docs/REMOTE_ACCESS.md)
</details>

<details>
<summary><strong>Troubleshooting</strong></summary>

Common issues with ports, blank dashboards, and connectivity.

[View Remote Access & Troubleshooting](./docs/REMOTE_ACCESS.md#troubleshooting)
</details>

---

## 📌 Current Status

- ✅ Analytics backend MVP scaffolded (ingest, normalize, persist, query API)
- ✅ React graph dashboard available in `frontend/`
- ✅ Remote OpenClaw config contract added for hybrid integration
- ⏳ Alerts and forecasting are planned next phases

## 🗺️ Roadmap

- Track progress and upcoming milestones in GitHub Projects:
   - https://github.com/orgs/Ubundi/projects/1/views/1

## 🤝 Contributing

Contributions are welcome.

- Open an issue with a clear bug report or enhancement proposal.
- For first contributions, look for the `good first issue` label.
- Keep PRs focused and include setup/verification notes.

Planned repository docs:
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`

## 🌍 Community

- Discussions and support: open a GitHub Discussion or issue.
- Community chat link can be added here once a Discord/Slack channel is created.

## 📄 License

This project is open source under the repository license.

## ✅ Maintainer Actions Needed

These items require human action to fully complete the OSS/public repo refactor:

1. Add a real demo asset at `docs/demo.gif` (or change the image path to your final screenshot/GIF).
2. Create `CONTRIBUTING.md` with PR workflow, development setup, and coding standards.
3. Add `CODE_OF_CONDUCT.md` (GitHub Community Standards template is fine).
4. Add `SECURITY.md` with private vulnerability disclosure instructions.
5. Add your community URL (Discord/Slack) into the Community section.

---
*Created for the OpenClaw community.*
