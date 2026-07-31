#!/usr/bin/env bash
# Start the backend from any working directory.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$PROJECT_ROOT/backend/.venv/bin/python"

if [[ -n "${NEOSWARM_PYTHON:-}" ]]; then
  PYTHON="$NEOSWARM_PYTHON"
elif [[ -x "$VENV_PYTHON" ]]; then
  PYTHON="$VENV_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "Error: Python 3.11+ is required. Set NEOSWARM_PYTHON or create backend/.venv." >&2
  exit 1
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
  echo "Error: NeoSwarm requires Python 3.11+ (found: $PYTHON)." >&2
  exit 1
fi

export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m uvicorn backend.main:app --host 127.0.0.1 --port "${NEOSWARM_PORT:-8324}" "$@"
