# Remote Access & Troubleshooting

## Preferred Deployment: Run on OpenClaw Host

For reliable historical backfill across multiple viewer devices, run Claw Journal on the same host where OpenClaw runs.

Why:
- One SQLite DB on host (single source of truth).
- No per-laptop cache divergence.
- New laptops can view the same history via SSH tunnel instantly.

### 1. Run Claw Journal on host

```bash
ssh user@your-host
cd ~/claw-journal
./scripts/start-dashboard.sh
```

### 2. View from your local machine via SSH tunnel

```bash
ssh -L 5173:127.0.0.1:5173 -L 3000:127.0.0.1:3000 user@your-host
```

Open:
- Claw Journal: `http://127.0.0.1:5173`
- API health: `http://127.0.0.1:3000/health`

## Alternative: Separate Claw Journal Machine (SSH ingest)

If you run OpenClaw on a remote server (e.g., a cloud VM or diverse local machine) but want to browse the journal on your laptop.

### 1. SSH Prerequisite
Ensure password-less SSH access works:
```bash
ssh -o BatchMode=yes user@your-host 'hostname'
```

### 2. Configure Local Claw Journal (advanced mode)
Set your local `.env` to pull from the remote host:

```bash
CJ_REMOTE_ENABLED=true
CJ_REMOTE_SSH_HOST=user@your-host
CJ_REMOTE_INGEST_MODE=file
```

Run start script:
```bash
./scripts/start-dashboard.sh
```

This will:
1. Connect via SSH to `user@your-host`.
2. Backfill historical logs from the remote OpenClaw instance into your local Claw Journal DB.
3. Sync transcript/session history continuously.

## Historic Data Expectations

In this advanced mode, Claw Journal stores data in a **local** SQLite file on each machine. Prefer host-run mode if you want one canonical DB.

For a brand-new machine to recover history, ensure the remote host retains:

- OpenClaw JSONL transcripts (default: `~/.openclaw/agents/*/sessions/*.jsonl`)
- OpenClaw log files (default: `/tmp/openclaw/openclaw-*.log`)

If your remote host cleans `/tmp` on reboot, move logs to a persistent directory and point `CJ_OPENCLAW_LOG_GLOB` at that path.

---

## OpenClaw Control UI Access (SSH Tunnel)

If you need to access the **OpenClaw Control UI** (usually on port 18790) from your local machine securely.

1. **Read Remote Token:**
   ```bash
   # On remote machine
   read -r -s -p "OpenClaw gateway token: " OPENCLAW_GATEWAY_TOKEN && echo
   ```

2. ** Tunnel the Port:**
   ```bash
   # On local machine
   ssh -L 18790:localhost:18790 user@your-host
   ```
   *(If 18790 is busy locally, use `ssh -L 18791:localhost:18790 ...`)*

3. **Access:**
   - OpenClaw Control: `http://localhost:18790`
   - Claw Journal: `http://localhost:5173`

---

## Troubleshooting

### Blank or Stuck Dashboard
If `http://localhost:5173` loads but shows no data:

1. **Check Ports:**
   ```bash
   lsof -nP -iTCP:3000 -sTCP:LISTEN
   lsof -nP -iTCP:5173 -sTCP:LISTEN
   ```

2. **Check Health Endpoint:**
   ```bash
   # Should return {"status":"ok"}
   curl -sS http://127.0.0.1:3000/health
   ```

3. **Check Frontend Proxy:**
   ```bash
   # Should return JSON data
   curl -sS http://127.0.0.1:5173/api/dashboard-data
   ```

4. **Reset:**
   ```bash
   ./scripts/stop-dashboard.sh
   # If processes persist:
   lsof -ti tcp:3000 | xargs kill -9
   ```

### "Address already in use"
The start script attempts to find free ports, but if you need to manually find what's running:
```bash
lsof -i :3000
```
