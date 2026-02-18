#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_STATE_FILE="${ROOT_DIR}/.claw-journal-run.env"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

backend_port="${CJ_PORT:-3000}"
frontend_port="${CJ_FRONTEND_PORT:-5173}"
backend_pid=""

if [[ -f "$RUN_STATE_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$RUN_STATE_FILE"
  set +a
  backend_port="${CJ_EFFECTIVE_BACKEND_PORT:-$backend_port}"
  frontend_port="${CJ_EFFECTIVE_FRONTEND_PORT:-$frontend_port}"
  backend_pid="${CJ_EFFECTIVE_BACKEND_PID:-}"
fi

kill_port_listeners() {
  local port="$1"
  local pids
  pids="$(lsof -ti tcp:"$port" || true)"
  if [[ -n "$pids" ]]; then
    echo "$pids" | xargs kill >/dev/null 2>&1 || true
    sleep 0.2
    pids="$(lsof -ti tcp:"$port" || true)"
    if [[ -n "$pids" ]]; then
      echo "$pids" | xargs kill -9 >/dev/null 2>&1 || true
    fi
  fi
}

if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" >/dev/null 2>&1; then
  kill "$backend_pid" >/dev/null 2>&1 || true
fi

kill_port_listeners "$backend_port"
kill_port_listeners "$frontend_port"

rm -f "$RUN_STATE_FILE"

echo "Stopped dashboard processes (backend port: ${backend_port}, frontend port: ${frontend_port})."
