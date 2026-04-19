#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_PORT_FILE="$RUN_DIR/backend.port"
FRONTEND_PORT_FILE="$RUN_DIR/frontend.port"

is_running() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

kill_process_tree() {
  local pid="$1"
  local child

  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_process_tree "$child"
  done

  if is_running "$pid"; then
    kill "$pid" >/dev/null 2>&1 || true
  fi
}

kill_if_running() {
  local name="$1"
  local pid_file="$2"

  if [[ ! -f "$pid_file" ]]; then
    echo "$name PID file not found, skipping."
    return
  fi

  local pid
  pid="$(cat "$pid_file")"

  if is_running "$pid"; then
    echo "Stopping $name (PID: $pid) ..."
    kill_process_tree "$pid"

    # Wait briefly, then force kill if needed.
    sleep 1
    if is_running "$pid"; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    echo "$name stopped."
  else
    echo "$name PID $pid was not running."
  fi

  rm -f "$pid_file"
}

kill_if_running "Backend" "$BACKEND_PID_FILE"
kill_if_running "Frontend" "$FRONTEND_PID_FILE"

rm -f "$BACKEND_PORT_FILE" "$FRONTEND_PORT_FILE"

echo "Done."
