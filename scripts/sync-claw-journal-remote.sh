#!/bin/bash
set -euo pipefail

export HOME=/Users/rune
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=/usr/bin/false

LOCKDIR=/tmp/claw-journal-sync.lock
LOCK_PID_FILE="$LOCKDIR/pid"
LOCK_MAX_AGE_SECONDS="${CJ_SYNC_LOCK_MAX_AGE_SECONDS:-300}"
FETCH_TIMEOUT_SECONDS="${CJ_SYNC_FETCH_TIMEOUT_SECONDS:-240}"
PIP_CHECK_TIMEOUT_SECONDS="${CJ_SYNC_PIP_CHECK_TIMEOUT_SECONDS:-30}"
REPO=/Users/rune/Documents/GitHub/claw-journal
SYNC_LOG=/Users/rune/claw-journal-sync.log
PERSIST_LOG_DIR="$REPO/data/logs"
START_LOG="$PERSIST_LOG_DIR/claw-journal-start.log"
ENSUREPIP_LOG="$PERSIST_LOG_DIR/claw-journal-ensurepip.log"
PIP_UPGRADE_LOG="$PERSIST_LOG_DIR/claw-journal-pip-upgrade.log"
PIP_INSTALL_LOG="$PERSIST_LOG_DIR/claw-journal-pip-install.log"
NPM_INSTALL_LOG="$PERSIST_LOG_DIR/claw-journal-npm-install.log"

mkdir -p "$PERSIST_LOG_DIR"
chmod 700 "$PERSIST_LOG_DIR" >/dev/null 2>&1 || true
umask 077

log() {
  echo "$(date +"%Y-%m-%d %H:%M:%S") $*" >> "$SYNC_LOG"
}

run_with_timeout() {
  local timeout_seconds="$1"
  shift

  "$@" &
  local cmd_pid=$!

  (
    sleep "$timeout_seconds"
    if kill -0 "$cmd_pid" >/dev/null 2>&1; then
      kill "$cmd_pid" >/dev/null 2>&1 || true
      sleep 1
      if kill -0 "$cmd_pid" >/dev/null 2>&1; then
        kill -9 "$cmd_pid" >/dev/null 2>&1 || true
      fi
    fi
  ) &
  local watchdog_pid=$!

  wait "$cmd_pid"
  local cmd_status=$?
  kill "$watchdog_pid" >/dev/null 2>&1 || true
  wait "$watchdog_pid" >/dev/null 2>&1 || true

  return "$cmd_status"
}

if ! [[ "$LOCK_MAX_AGE_SECONDS" =~ ^[0-9]+$ ]] || [[ "$LOCK_MAX_AGE_SECONDS" -le 0 ]]; then
  LOCK_MAX_AGE_SECONDS=300
fi

acquire_lock() {
  if mkdir "$LOCKDIR" 2>/dev/null; then
    echo "$$" > "$LOCK_PID_FILE"
    return 0
  fi

  local lock_mtime
  lock_mtime="$(stat -f %m "$LOCKDIR" 2>/dev/null || echo 0)"
  local now
  now="$(date +%s)"
  local age=$((now - lock_mtime))

  local lock_pid=""
  if [[ -f "$LOCK_PID_FILE" ]]; then
    lock_pid="$(cat "$LOCK_PID_FILE" 2>/dev/null || true)"
  fi

  if [[ -n "$lock_pid" ]] && kill -0 "$lock_pid" >/dev/null 2>&1; then
    if [[ "$age" -ge "$LOCK_MAX_AGE_SECONDS" ]]; then
      log "active lock exceeded max age (${age}s, pid=${lock_pid}); terminating and continuing"
      kill "$lock_pid" >/dev/null 2>&1 || true
      sleep 1
      if kill -0 "$lock_pid" >/dev/null 2>&1; then
        kill -9 "$lock_pid" >/dev/null 2>&1 || true
      fi
      rm -rf "$LOCKDIR" >/dev/null 2>&1 || true
      if mkdir "$LOCKDIR" 2>/dev/null; then
        echo "$$" > "$LOCK_PID_FILE"
        return 0
      fi
    fi
    log "sync skipped: previous run still active (pid=$lock_pid)"
    return 1
  fi

  if [[ "$age" -ge "$LOCK_MAX_AGE_SECONDS" ]]; then
    rm -rf "$LOCKDIR" >/dev/null 2>&1 || true
    if mkdir "$LOCKDIR" 2>/dev/null; then
      echo "$$" > "$LOCK_PID_FILE"
      log "cleared stale lock (age=${age}s) and continued"
      return 0
    fi
  fi

  log "sync skipped: lock present (age=${age}s)"
  return 1
}

cleanup_lock() {
  if [[ -f "$LOCK_PID_FILE" ]] && [[ "$(cat "$LOCK_PID_FILE" 2>/dev/null || true)" == "$$" ]]; then
    rm -rf "$LOCKDIR" >/dev/null 2>&1 || true
  fi
}

if ! acquire_lock; then
  exit 0
fi
trap cleanup_lock EXIT

if [ ! -d "$REPO/.git" ]; then
  log "repo missing: $REPO"
  exit 1
fi

ensure_venv_pip() {
  cd "$REPO"
  local venv_python=".venv/bin/python"
  if [ ! -x .venv/bin/python ]; then
    /opt/homebrew/bin/python3 -m venv .venv || {
      log "failed to create venv"
      return 1
    }
  fi
  "$venv_python" -m ensurepip --upgrade >"$ENSUREPIP_LOG" 2>&1 || true
  run_with_timeout "$PIP_CHECK_TIMEOUT_SECONDS" "$venv_python" -m pip --version >/dev/null 2>&1 || {
    log "pip unavailable in venv"
    return 1
  }
  "$venv_python" -m pip install --upgrade pip >"$PIP_UPGRADE_LOG" 2>&1 || true
}

restart_stack() {
  cd "$REPO"
  local start_log_target="$START_LOG"
  mkdir -p "$(dirname "$START_LOG")" >/dev/null 2>&1 || true
  touch "$START_LOG" >/dev/null 2>&1 || start_log_target="/tmp/claw-journal-start.log"
  ./scripts/stop-dashboard.sh >/dev/null 2>&1 || true
  lsof -ti tcp:3000 | xargs kill -9 >/dev/null 2>&1 || true
  lsof -ti tcp:5173 | xargs kill -9 >/dev/null 2>&1 || true
  nohup bash -lc 'ulimit -n 4096; export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; ./scripts/start-dashboard.sh' > "$start_log_target" 2>&1 < /dev/null &
  sleep 4
}

ensure_healthy() {
  curl -fsS http://127.0.0.1:3000/health >/dev/null 2>&1 && curl -fsS http://127.0.0.1:5173/api/system/connection >/dev/null 2>&1
}

cd "$REPO"
if ! run_with_timeout "$FETCH_TIMEOUT_SECONDS" git fetch --quiet origin main; then
  log "fetch failed"
  if ensure_healthy; then
    log "fetch failed but services are healthy; skipped restart"
  else
    restart_stack
    if ensure_healthy; then
      log "recover restart ok after fetch failure"
    else
      log "recover restart failed after fetch failure"
    fi
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
    .venv/bin/python -m pip install -r requirements.txt >"$PIP_INSTALL_LOG" 2>&1 || log "pip install failed (continuing)"
  else
    log "venv/pip setup failed; skipping pip install"
  fi

  npm --prefix frontend install --no-audit --no-fund >"$NPM_INSTALL_LOG" 2>&1 || log "npm install failed (continuing)"

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
