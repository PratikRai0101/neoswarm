#!/usr/bin/env bash
# Start the backend and web frontend for local development.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$PROJECT_ROOT/backend/.venv/bin/python"
PORT="${NEOSWARM_PORT:-8324}"
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

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

if [[ ! -d "$PROJECT_ROOT/frontend/node_modules" ]]; then
  echo "Error: frontend dependencies are missing. Run: (cd frontend && npm install)" >&2
  exit 1
fi

export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "🐝 Starting NeoSwarm..."
echo "Starting FastAPI backend on :$PORT..."
"$PYTHON" -m uvicorn backend.main:app --host 127.0.0.1 --port "$PORT" &
BACKEND_PID=$!

echo "Waiting for backend..."
for _ in $(seq 1 30); do
  if curl --fail --silent "http://127.0.0.1:$PORT/api/health/check" >/dev/null; then
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Error: backend exited before becoming ready." >&2
    exit 1
  fi
  sleep 1
done

if ! curl --fail --silent "http://127.0.0.1:$PORT/api/health/check" >/dev/null; then
  echo "Error: backend did not become ready within 30 seconds." >&2
  exit 1
fi

echo "Starting React frontend on :3000..."
(
  cd "$PROJECT_ROOT/frontend"
  npm run dev
) &
FRONTEND_PID=$!

echo ""
echo "🐝 NeoSwarm running!"
echo "   Frontend: http://localhost:3000"
echo "   Backend:  http://localhost:$PORT"
echo ""
echo "Press Ctrl+C to stop"

wait "$BACKEND_PID" "$FRONTEND_PID"
