#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

env_value() {
  local key="$1"
  local fallback="$2"
  local env_file="$ROOT_DIR/.env"

  if [[ -f "$env_file" ]]; then
    local value
    value="$(awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$env_file")"
    if [[ -n "$value" ]]; then
      printf '%s\n' "$value"
      return
    fi
  fi

  printf '%s\n' "$fallback"
}

HOST="${HOST:-$(env_value APP_HOST 127.0.0.1)}"
PORT="${PORT:-$(env_value APP_PORT 18765)}"
RUN_DIR="$ROOT_DIR/.run"
PID_FILE="$RUN_DIR/api-spend-dashboard.pid"
APP_TARGET="api_spend_dashboard.main:create_app"

mkdir -p "$RUN_DIR"

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  echo "Missing .venv/bin/python. Run: python3 -m venv .venv && .venv/bin/python -m pip install -e \".[dev]\"" >&2
  exit 1
fi

stop_pid() {
  local pid="$1"
  if [[ -z "$pid" ]]; then
    return
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    return
  fi

  echo "Stopping existing server process $pid"
  kill "$pid" 2>/dev/null || true

  for _ in {1..20}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      return
    fi
    sleep 0.2
  done

  echo "Process $pid did not exit after SIGTERM; sending SIGKILL"
  kill -9 "$pid" 2>/dev/null || true
}

if [[ -f "$PID_FILE" ]]; then
  stop_pid "$(cat "$PID_FILE")"
  rm -f "$PID_FILE"
fi

while IFS= read -r pid; do
  stop_pid "$pid"
done < <(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)

echo "Starting API Spend Dashboard on http://$HOST:$PORT"
echo "Press Ctrl+C to stop the server."
echo "$$" > "$PID_FILE"

exec "$ROOT_DIR/.venv/bin/python" -m uvicorn "$APP_TARGET" \
  --factory \
  --host "$HOST" \
  --port "$PORT"
