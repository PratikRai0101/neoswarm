#!/usr/bin/env bash
# Start the backend and web frontend for local development.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$PROJECT_ROOT/backend/.venv/bin/python"
PORT="${NEOSWARM_PORT:-8324}"
FRONTEND_PORT=3000
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

port_listener_pid() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1
  elif command -v ss >/dev/null 2>&1; then
    ss -ltnp "sport = :$port" 2>/dev/null \
      | awk -F'pid=' 'NR > 1 && NF > 1 { split($2, p, ","); print p[1]; exit }'
  fi
}

listener_description() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null | sed 's/^[[:space:]]*//' || echo "unknown process"
}

backend_healthy() {
  local response
  response="$(curl --fail --silent --max-time 2 "http://127.0.0.1:$PORT/api/health/check" 2>/dev/null)" || return 1
  [[ "$response" == *'"status":"ok"'* ]]
}

frontend_healthy() {
  local response
  response="$(curl --fail --silent --max-time 2 "http://127.0.0.1:$FRONTEND_PORT/" 2>/dev/null)" || return 1
  [[ "$response" == *'<title>NeoSwarm</title>'* && "$response" == *'bundle.js'* ]]
}

if [[ -n "${NEOSWARM_PYTHON:-}" ]]; then
  PYTHON="$NEOSWARM_PYTHON"
elif [[ -x "$VENV_PYTHON" ]]; then
  PYTHON="$VENV_PYTHON"
else
  echo "Error: backend/.venv is missing. Create it with:"
  echo "  python3.11 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt"
  exit 1
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
  echo "Error: NeoSwarm requires Python 3.11+ (found: $PYTHON)." >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "Error: Node.js is required." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "Error: curl is required." >&2
  exit 1
fi

if [[ ! -d "$PROJECT_ROOT/frontend/node_modules" ]]; then
  echo "Error: frontend dependencies are missing. Run: (cd frontend && npm install)" >&2
  exit 1
fi

export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "🐝 Starting NeoSwarm..."

if backend_healthy; then
  echo "Backend already running on :$PORT; reusing it."
else
  existing_backend_pid="$(port_listener_pid "$PORT" || true)"
  if [[ -n "$existing_backend_pid" ]]; then
    echo "Error: port $PORT is occupied by PID $existing_backend_pid:" >&2
    echo "  $(listener_description "$existing_backend_pid")" >&2
    echo "Stop that process or set NEOSWARM_PORT to another port." >&2
    exit 1
  fi

  echo "Starting FastAPI backend on :$PORT..."
  "$PYTHON" -m uvicorn backend.main:app --host 127.0.0.1 --port "$PORT" &
  BACKEND_PID=$!

  echo "Waiting for backend..."
  backend_ready=0
  for _ in $(seq 1 30); do
    if backend_healthy; then
      backend_ready=1
      break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      echo "Error: backend exited before becoming ready." >&2
      exit 1
    fi
    sleep 1
  done

  if [[ "$backend_ready" != 1 ]]; then
    echo "Error: backend did not become ready within 30 seconds." >&2
    exit 1
  fi
fi

if frontend_healthy; then
  echo "Frontend already running on :$FRONTEND_PORT; reusing it."
else
  existing_frontend_pid="$(port_listener_pid "$FRONTEND_PORT" || true)"
  if [[ -n "$existing_frontend_pid" ]]; then
    echo "Error: port $FRONTEND_PORT is occupied by PID $existing_frontend_pid:" >&2
    echo "  $(listener_description "$existing_frontend_pid")" >&2
    echo "Stop that process before starting the NeoSwarm frontend." >&2
    exit 1
  fi

  echo "Starting React frontend on :$FRONTEND_PORT..."
  (
    cd "$PROJECT_ROOT/frontend"
    exec npm run dev
  ) &
  FRONTEND_PID=$!

  frontend_ready=0
  for _ in $(seq 1 30); do
    if frontend_healthy; then
      frontend_ready=1
      break
    fi
    if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
      echo "Error: frontend exited before becoming ready." >&2
      exit 1
    fi
    sleep 1
  done

  if [[ "$frontend_ready" != 1 ]]; then
    echo "Error: frontend did not become ready within 30 seconds." >&2
    exit 1
  fi
fi

echo ""
echo "🐝 NeoSwarm running!"
echo "   Frontend: http://localhost:$FRONTEND_PORT"
echo "   Backend:  http://localhost:$PORT"
echo ""
echo "Press Ctrl+C to stop"

pids=()
[[ -n "$BACKEND_PID" ]] && pids+=("$BACKEND_PID")
[[ -n "$FRONTEND_PID" ]] && pids+=("$FRONTEND_PID")
if [[ ${#pids[@]} -gt 0 ]]; then
  wait "${pids[@]}"
else
  echo "Both services were already running; leaving them under their existing supervisor."
fi
