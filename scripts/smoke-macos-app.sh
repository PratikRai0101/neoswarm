#!/usr/bin/env bash
# Smoke-test a built macOS DMG without relying on the repository source tree.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DMG_PATH="$(find "$PROJECT_ROOT/src-tauri/target/debug/bundle/dmg" -maxdepth 1 -type f -name 'NeoSwarm_*.dmg' -print -quit)"
MOUNT_DIR="${RUNNER_TEMP:-/tmp}/neoswarm-dmg-mount"
LOG_PATH="${RUNNER_TEMP:-/tmp}/neoswarm-macos-app.log"

if [[ -z "$DMG_PATH" ]]; then
  echo "No debug macOS DMG was found under src-tauri/target/debug/bundle/dmg" >&2
  exit 1
fi
if lsof -nP -iTCP:8324 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port 8324 is already in use; refusing to run the packaged-app smoke test" >&2
  lsof -nP -iTCP:8324 -sTCP:LISTEN >&2 || true
  exit 1
fi

rm -rf "$MOUNT_DIR"
mkdir -p "$MOUNT_DIR"
hdiutil attach -readonly -nobrowse -mountpoint "$MOUNT_DIR" "$DMG_PATH" >/dev/null

APP_PATH="$MOUNT_DIR/NeoSwarm.app"
APP_BINARY="$APP_PATH/Contents/MacOS/neoswarm"
BACKEND_BINARY="$APP_PATH/Contents/Resources/backend-dist/neoswarm-backend"
APP_PID=""

cleanup() {
  set +e
  if [[ -n "$APP_PID" ]] && kill -0 "$APP_PID" 2>/dev/null; then
    kill "$APP_PID" 2>/dev/null || true
    wait "$APP_PID" 2>/dev/null || true
  fi
  sleep 1
  pkill -f "$BACKEND_BINARY --host 127.0.0.1 --port 8324" 2>/dev/null || true
  hdiutil detach -force "$MOUNT_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [[ ! -x "$APP_BINARY" || ! -x "$BACKEND_BINARY" ]]; then
  echo "The DMG is missing the application or bundled backend executable" >&2
  exit 1
fi

(cd "${RUNNER_TEMP:-/tmp}" && "$APP_BINARY" >"$LOG_PATH" 2>&1) &
APP_PID=$!

healthy=0
for _ in $(seq 1 45); do
  if curl --fail --silent http://127.0.0.1:8324/api/health/check | grep -q '"status":"ok"'; then
    healthy=1
    break
  fi
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    break
  fi
  sleep 1
done

cat "$LOG_PATH"
if [[ "$healthy" != 1 ]]; then
  echo "Packaged macOS app backend did not become healthy" >&2
  exit 1
fi
if ! grep -q 'Starting bundled backend executable' "$LOG_PATH"; then
  echo "Packaged app did not use its bundled backend executable" >&2
  exit 1
fi

# Verify that the optional computer-control dependency survived PyInstaller.
python3 - <<'PY' | "$BACKEND_BINARY" --internal python-exec | grep -q '"module": "pyautogui"'
import json
print(json.dumps({
    "code": "import pyautogui\nresult={'module': pyautogui.__name__}",
    "input_data": {},
}))
PY

echo "macOS packaged-app smoke test: ok"
