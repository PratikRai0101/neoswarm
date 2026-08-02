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
SECOND_APP_PID=""
BACKEND_PID=""

terminate_pid() {
  local pid="$1"
  [[ "$pid" == "$$" ]] && return
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 10); do
    kill -0 "$pid" 2>/dev/null || return
    sleep 0.1
  done
  kill -9 "$pid" 2>/dev/null || true
}

find_backend_pid() {
  ps -axo pid=,ppid=,command= | awk -v parent="$APP_PID" -v binary="$BACKEND_BINARY" \
    '$2 == parent && index($0, binary) > 0 { print $1; exit }'
}

cleanup() {
  set +e
  if [[ -n "$SECOND_APP_PID" ]] && kill -0 "$SECOND_APP_PID" 2>/dev/null; then
    terminate_pid "$SECOND_APP_PID"
    wait "$SECOND_APP_PID" 2>/dev/null || true
  fi
  if [[ -n "$APP_PID" ]] && kill -0 "$APP_PID" 2>/dev/null; then
    terminate_pid "$APP_PID"
    wait "$APP_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]]; then
    terminate_pid "$BACKEND_PID"
  fi
  # If the app was force-terminated, its sidecar can be re-parented before
  # Tauri emits RunEvent::Exit. Remove only this smoke test's exact binary.
  for pid in $(ps -axo pid=,command= | awk -v binary="$BACKEND_BINARY" \
    'index($0, binary) > 0 { print $1 }'); do
    terminate_pid "$pid"
  done
  hdiutil detach -force "$MOUNT_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [[ ! -x "$APP_BINARY" || ! -x "$BACKEND_BINARY" ]]; then
  echo "The DMG is missing the application or bundled backend executable" >&2
  exit 1
fi

(cd "${RUNNER_TEMP:-/tmp}" && exec "$APP_BINARY" >"$LOG_PATH" 2>&1) &
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
BACKEND_PID="$(find_backend_pid || true)"

cat "$LOG_PATH"
if [[ "$healthy" != 1 ]]; then
  echo "Packaged macOS app backend did not become healthy" >&2
  exit 1
fi
if ! grep -q 'Starting bundled backend executable' "$LOG_PATH"; then
  echo "Packaged app did not use its bundled backend executable" >&2
  exit 1
fi

# A second launch must hand off to the existing process and exit immediately.
SECOND_LOG_PATH="${RUNNER_TEMP:-/tmp}/neoswarm-macos-second-instance.log"
(cd "${RUNNER_TEMP:-/tmp}" && exec "$APP_BINARY" >"$SECOND_LOG_PATH" 2>&1) &
SECOND_APP_PID=$!
sleep 2
if kill -0 "$SECOND_APP_PID" 2>/dev/null; then
  echo "A second NeoSwarm instance stayed alive" >&2
  cat "$SECOND_LOG_PATH" >&2 || true
  exit 1
fi
wait "$SECOND_APP_PID" 2>/dev/null || true

# Verify that the optional computer-control dependency survived PyInstaller.
python3 - <<'PY' | "$BACKEND_BINARY" --internal python-exec | grep -q '"module": "pyautogui"'
import json
print(json.dumps({
    "code": "import pyautogui\nresult={'module': pyautogui.__name__}",
    "input_data": {},
}))
PY

echo "macOS packaged-app smoke test: ok"
