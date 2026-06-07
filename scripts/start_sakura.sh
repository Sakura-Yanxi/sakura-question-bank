#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${SAKURA_APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PID_FILE="${SAKURA_PID_FILE:-$APP_DIR/server.pid}"
OUT_LOG="${SAKURA_OUT_LOG:-$APP_DIR/server.out.log}"
ERR_LOG="${SAKURA_ERR_LOG:-$APP_DIR/server.err.log}"

cd "$APP_DIR"
mkdir -p data/uploads data/pages

if [ -f "$PID_FILE" ]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${old_pid:-}" ] && kill -0 "$old_pid" 2>/dev/null; then
    echo "Sakura is already running: pid=$old_pid"
    exit 0
  fi
fi

nohup "$PYTHON_BIN" app.py > "$OUT_LOG" 2> "$ERR_LOG" < /dev/null &
pid="$!"
echo "$pid" > "$PID_FILE"
sleep 2

if ! kill -0 "$pid" 2>/dev/null; then
  echo "Sakura failed to start. Recent error log:" >&2
  tail -80 "$ERR_LOG" >&2 || true
  exit 1
fi

echo "Sakura started: pid=$pid"
tail -5 "$OUT_LOG" || true
