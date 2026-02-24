#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"

RUN_STATE_FILE="${ROOT_DIR}/.claw-journal-run.env"
LOG_DIR="${CJ_LOG_DIR:-${ROOT_DIR}/data/logs}"
BACKEND_LOG_FILE="${CJ_BACKEND_LOG_FILE:-${LOG_DIR}/claw-journal-backend.log}"
FRONTEND_LOG_FILE="${CJ_FRONTEND_LOG_FILE:-${LOG_DIR}/claw-journal-frontend.log}"

umask 077
mkdir -p "$LOG_DIR"
chmod 700 "$LOG_DIR" >/dev/null 2>&1 || true

if [[ ! -d ".venv" ]]; then
  echo "Missing .venv. Run: uv venv && source .venv/bin/activate && uv pip install -r requirements.txt"
  exit 1
fi

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ "${CJ_REMOTE_ENABLED:-false}" == "true" && -z "${CJ_ENSURE_DURABLE_LOGS+x}" ]]; then
  export CJ_ENSURE_DURABLE_LOGS=true
fi

fd_target="${CJ_OPEN_FILES_LIMIT:-8192}"
current_fd="$(ulimit -n 2>/dev/null || echo '')"
if [[ "$fd_target" =~ ^[0-9]+$ ]] && [[ "$current_fd" =~ ^[0-9]+$ ]] && (( current_fd < fd_target )); then
  if ulimit -n "$fd_target" 2>/dev/null; then
    echo "Raised open-file soft limit: ${current_fd} -> ${fd_target}"
  else
    hard_fd="$(ulimit -Hn 2>/dev/null || echo '')"
    if [[ "$hard_fd" =~ ^[0-9]+$ ]] && (( current_fd < hard_fd )); then
      desired_fd="$fd_target"
      if (( desired_fd > hard_fd )); then
        desired_fd="$hard_fd"
      fi
      if ulimit -n "$desired_fd" 2>/dev/null; then
        echo "Raised open-file soft limit: ${current_fd} -> ${desired_fd}"
      else
        echo "Warning: could not raise open-file soft limit (current ${current_fd})."
      fi
    else
      echo "Warning: open-file soft limit is ${current_fd}; consider increasing it if startup hits 'Too many open files'."
    fi
  fi
fi

backend_port="${CJ_PORT:-3000}"
frontend_port="${CJ_FRONTEND_PORT:-5173}"
port_search_limit="${CJ_PORT_SEARCH_LIMIT:-50}"

is_port_busy() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

find_next_open_port() {
  local start_port="$1"
  local max_tries="$2"
  local port
  for ((i=0; i<=max_tries; i++)); do
    port=$((start_port + i))
    if ! is_port_busy "$port"; then
      echo "$port"
      return 0
    fi
  done
  return 1
}

if is_port_busy "$backend_port"; then
  next_port="$(find_next_open_port "$backend_port" "$port_search_limit" || true)"
  if [[ -z "$next_port" ]]; then
    echo "No open backend port found in range ${backend_port}-$((backend_port + port_search_limit))."
    echo "Free a port first, then rerun."
    exit 1
  fi
  echo "CJ_PORT ${backend_port} is busy, using ${next_port} instead."
  backend_port="$next_port"
fi

export CJ_AUTO_PORT=false
export CJ_PORT="$backend_port"
export CJ_API_TARGET="http://127.0.0.1:${backend_port}"

source .venv/bin/activate

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found in PATH. Install Node.js/npm, or run with PATH set (example: PATH=/opt/homebrew/bin:/usr/local/bin:\$PATH ./scripts/start-dashboard.sh)."
  exit 1
fi

nohup python main.py >"$BACKEND_LOG_FILE" 2>&1 < /dev/null &
backend_pid=$!

cat > "$RUN_STATE_FILE" <<EOF
CJ_EFFECTIVE_BACKEND_PORT=${backend_port}
CJ_EFFECTIVE_FRONTEND_PORT=${frontend_port}
CJ_EFFECTIVE_BACKEND_PID=${backend_pid}
EOF

cleanup() {
  if kill -0 "$backend_pid" >/dev/null 2>&1; then
    kill "$backend_pid" >/dev/null 2>&1 || true
  fi
  rm -f "$RUN_STATE_FILE"
}
trap cleanup EXIT INT TERM

for _ in {1..40}; do
  if curl -sS "http://127.0.0.1:${backend_port}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

if ! curl -sS "http://127.0.0.1:${backend_port}/health" >/dev/null 2>&1; then
  echo "Backend failed to start. See ${BACKEND_LOG_FILE}"
  exit 1
fi

echo "Backend:  http://127.0.0.1:${backend_port}"
echo "Frontend: http://127.0.0.1:${frontend_port}"
echo "(Vite proxy -> ${CJ_API_TARGET})"
echo "Stop:     ./scripts/stop-dashboard.sh"

cd frontend

if [[ "${CJ_DETACH:-false}" == "true" ]]; then
  nohup npm run dev -- --host 127.0.0.1 --port "$frontend_port" >"$FRONTEND_LOG_FILE" 2>&1 < /dev/null &
  frontend_pid=$!
  echo "CJ_EFFECTIVE_FRONTEND_PID=${frontend_pid}" >> "$RUN_STATE_FILE"
  disown || true
  trap - EXIT INT TERM
  echo "Detached mode enabled."
  echo "Backend log:  ${BACKEND_LOG_FILE}"
  echo "Frontend log: ${FRONTEND_LOG_FILE}"
  exit 0
fi

npm run dev -- --host 127.0.0.1 --port "$frontend_port"
