#!/bin/bash
set -euo pipefail

export HOME=/Users/rune
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=/usr/bin/false

LOCKDIR=/tmp/claw-journal-sync.lock
REPO=/Users/rune/Documents/GitHub/claw-journal
SYNC_LOG=/Users/rune/claw-journal-sync.log
START_LOG=/tmp/claw-journal-start.log

log() {
  echo "$(date +"%Y-%m-%d %H:%M:%S") $*" >> "$SYNC_LOG"
}

if ! mkdir "$LOCKDIR" 2>/dev/null; then
  log "sync skipped: previous run still active"
  exit 0
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT

if [ ! -d "$REPO/.git" ]; then
  log "repo missing: $REPO"
  exit 1
fi

ensure_venv_pip() {
  cd "$REPO"
  if [ ! -x .venv/bin/python ]; then
    /opt/homebrew/bin/python3 -m venv .venv || {
      log "failed to create venv"
      return 1
    }
  fi
  . .venv/bin/activate
  python -m ensurepip --upgrade >/tmp/claw-journal-ensurepip.log 2>&1 || true
  python -m pip --version >/dev/null 2>&1 || {
    log "pip unavailable in venv"
    return 1
  }
  python -m pip install --upgrade pip >/tmp/claw-journal-pip-upgrade.log 2>&1 || true
}

restart_stack() {
  cd "$REPO"
  ./scripts/stop-dashboard.sh >/dev/null 2>&1 || true
  lsof -ti tcp:3000 | xargs kill -9 >/dev/null 2>&1 || true
  lsof -ti tcp:5173 | xargs kill -9 >/dev/null 2>&1 || true
  nohup bash -lc 'ulimit -n 4096; export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; ./scripts/start-dashboard.sh' > "$START_LOG" 2>&1 < /dev/null &
  sleep 4
}

ensure_healthy() {
  curl -fsS http://127.0.0.1:3000/health >/dev/null 2>&1 && curl -fsS http://127.0.0.1:5173/api/system/connection >/dev/null 2>&1
}

cd "$REPO"
if ! git fetch --quiet origin main; then
  log "fetch failed"
  restart_stack
  if ensure_healthy; then
    log "recover restart ok after fetch failure"
  else
    log "recover restart failed after fetch failure"
  fi
  exit 0
fi

local_sha=$(git rev-parse HEAD)
remote_sha=$(git rev-parse origin/main)

if [ "$local_sha" != "$remote_sha" ]; then
  log "main update detected: deploying"
  git checkout -q main
  git reset --hard origin/main >/dev/null

  if ensure_venv_pip; then
    python -m pip install -r requirements.txt >/tmp/claw-journal-pip-install.log 2>&1 || log "pip install failed (continuing)"
  else
    log "venv/pip setup failed; skipping pip install"
  fi

  npm --prefix frontend install --no-audit --no-fund >/tmp/claw-journal-npm-install.log 2>&1 || log "npm install failed (continuing)"

  restart_stack
  if ensure_healthy; then
    log "deploy complete: healthy on 3000/5173"
  else
    log "deploy complete but health check failed"
  fi
  exit 0
fi

if ensure_healthy; then
  log "no update: healthy"
else
  log "no update but unhealthy: restarting"
  restart_stack
  if ensure_healthy; then
    log "self-heal restart successful"
  else
    log "self-heal restart failed"
  fi
fi
