# Installation & Configuration

## 1. Installation

### Prerequisites
- [OpenClaw](https://github.com/openclaw/openclaw) installed and configured.
- Python 3.9+
- [uv](https://docs.astral.sh/uv/) installed (recommended) or pip.
- Node.js 18+

### Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/Ubundi/claw-journal.git
   cd claw-journal
   ```

2. **Install Backend Dependencies**
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -r requirements.txt
   ```

3. **Install Frontend Dependencies**
   ```bash
   cd frontend
   npm install
   cd ..
   ```

## 2. Configuration (`.env`)

Claw Journal uses a `.env` file for configuration.

1. **Create from template:**
   ```bash
   cp .env.example .env
   ```

2. **Common Profiles:**

   **Local OpenClaw (default):**
   ```bash
   CJ_REMOTE_ENABLED=false
   CJ_OPENCLAW_LOG_GLOB=/tmp/openclaw/openclaw-*.log
   CJ_PORT=3000
   CJ_FRONTEND_PORT=5173
   ```

   **Host deployment for remote viewing (recommended):**
   Run Claw Journal on the same machine as OpenClaw, then access UI/API from your laptop via SSH tunnel.
   ```bash
   ssh -L 5173:127.0.0.1:5173 -L 3000:127.0.0.1:3000 user@your-host
   ```

   **Separate Claw Journal machine (advanced SSH ingest):**
   ```bash
   CJ_REMOTE_ENABLED=true
   CJ_REMOTE_SSH_HOST=user@your-host
   CJ_REMOTE_INGEST_MODE=file
   CJ_OPENCLAW_LOG_GLOB=~/.openclaw/logs/history/openclaw-*.log
   CJ_PORT=3000
   CJ_FRONTEND_PORT=5173
   ```

### Reference: All Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `CJ_OPENCLAW_LOG_GLOB` | `/tmp/openclaw/openclaw-*.log` | Path to OpenClaw logs. |
| `CJ_DB_PATH` | `./data/claw_journal.db` | SQLite database path. |
| `CJ_REMOTE_ENABLED` | `false` | Enable remote-mode config validation. |
| `CJ_REMOTE_SSH_HOST` | - | SSH target (e.g., `user@host`) for remote sync. |
| `CJ_REMOTE_INGEST_MODE` | `file` | `file` (SSH cat), `rpc`, or `hybrid`. |
| `CJ_ENSURE_DURABLE_LOGS` | `false` | Fail startup when remote log glob points to non-durable paths like `/tmp`. |
| `CJ_SESSION_SYNC_ENABLED` | `true` | Enable read-only remote session sync. |
| `CJ_TRANSCRIPT_SYNC_ENABLED` | `true` | Enable transcript ingestion. |
| `CJ_COST_ESTIMATION_ENABLED` | `true` | Estimate cost when logs lack cost data. |
| `CJ_PRICING_FILE` | `./pricing.json` | Path to pricing table. |
| `CJ_AUTH_MODE` | `auto` | `auto`, `oauth`, or `api_key`. |
| `CJ_PORT` | `3000` | Preferred API port. |
| `CJ_FRONTEND_PORT` | `5173` | Vite dev server port. |

*(See `.env.example` for the full list)*

## 3. Running

Use the helper script to verify the environment and start both services:

```bash
./scripts/start-dashboard.sh
```

Or run manually:

**Backend:**
```bash
uv run python main.py
```

**Frontend:**
```bash
cd frontend
npm run dev
```

## Pricing Configuration

`pricing.json` allows custom cost estimation for models that don't report costs (common with OAuth).

Format (USD per 1M tokens):
```json
{
   "anthropic/claude-opus-4-5": {
      "input_per_million": 15.0,
      "output_per_million": 75.0
   }
}
```
