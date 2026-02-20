#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_STATE_FILE="${ROOT_DIR}/.claw-journal-run.env"

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

python main.py >/tmp/claw-journal-backend.log 2>&1 &
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
  echo "Backend failed to start. See /tmp/claw-journal-backend.log"
  exit 1
fi

echo "Backend:  http://127.0.0.1:${backend_port}"
echo "Frontend: http://127.0.0.1:${frontend_port}"
echo "(Vite proxy -> ${CJ_API_TARGET})"
echo "Stop:     ./scripts/stop-dashboard.sh"

cd frontend
npm run dev -- --host 127.0.0.1 --port "$frontend_port"
