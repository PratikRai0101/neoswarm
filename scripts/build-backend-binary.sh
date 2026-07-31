#!/usr/bin/env bash
# Build the self-contained backend executable bundled by Tauri releases.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/backend/.venv/bin/python"
PYTHON="${NEOSWARM_PYTHON:-$VENV_PYTHON}"
DIST_DIR="$PROJECT_ROOT/backend-dist"
WORK_DIR="$PROJECT_ROOT/.build/pyinstaller"
SPEC_DIR="$PROJECT_ROOT/.build"

if [[ ! -x "$PYTHON" ]]; then
  echo "Error: backend Python was not found at $PYTHON" >&2
  echo "Create backend/.venv before building the desktop release." >&2
  exit 1
fi
if ! "$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
  echo "Error: the bundled backend requires Python 3.11+." >&2
  exit 1
fi
"$PYTHON" -m pip install --disable-pip-version-check -r \
  "$PROJECT_ROOT/backend/requirements-build.txt"

mkdir -p "$DIST_DIR" "$WORK_DIR" "$SPEC_DIR"
find "$DIST_DIR" -mindepth 1 ! -name .gitkeep -delete

"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name neoswarm-backend \
  --paths "$PROJECT_ROOT" \
  --collect-submodules backend.apps \
  --hidden-import backports \
  --hidden-import backports.tarfile \
  --add-data "$PROJECT_ROOT/backend/apps/outputs/view_builder_skill.md:backend/apps/outputs" \
  --add-data "$PROJECT_ROOT/backend/mcp-bundles:backend/mcp-bundles" \
  --add-data "$PROJECT_ROOT/backend/npm-servers:backend/npm-servers" \
  --distpath "$DIST_DIR" \
  --workpath "$WORK_DIR" \
  --specpath "$SPEC_DIR" \
  "$PROJECT_ROOT/backend/standalone.py"

chmod +x "$DIST_DIR/neoswarm-backend"
echo "Backend executable ready: $DIST_DIR/neoswarm-backend"
