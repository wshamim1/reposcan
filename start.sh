#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_PORT_FILE="$RUN_DIR/backend.port"
FRONTEND_PORT_FILE="$RUN_DIR/frontend.port"
BACKEND_LOG="$RUN_DIR/backend.log"
FRONTEND_LOG="$RUN_DIR/frontend.log"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"

DEFAULT_BACKEND_PORT=8000
DEFAULT_FRONTEND_PORT=5173

mkdir -p "$RUN_DIR"

is_running() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

find_listener_pid() {
  local port="$1"
  lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true
}

find_free_port() {
  local start_port="$1"
  local port="$start_port"
  while [[ "$port" -lt $((start_port + 50)) ]]; do
    if [[ -z "$(find_listener_pid "$port")" ]]; then
      echo "$port"
      return
    fi
    port=$((port + 1))
  done
  echo ""
}

start_backend() {
  local requested_port="$DEFAULT_BACKEND_PORT"
  local port

  if [[ -f "$BACKEND_PORT_FILE" ]]; then
    requested_port="$(cat "$BACKEND_PORT_FILE")"
  fi

  if [[ -f "$BACKEND_PID_FILE" ]]; then
    local existing_pid
    existing_pid="$(cat "$BACKEND_PID_FILE")"
    if is_running "$existing_pid"; then
      echo "Backend already running (PID: $existing_pid, port: $requested_port)"
      return
    fi
    rm -f "$BACKEND_PID_FILE"
  fi

  port="$(find_free_port "$requested_port")"
  if [[ -z "$port" ]]; then
    echo "Could not find a free backend port starting from $requested_port."
    return 1
  fi

  if [[ "$port" != "$requested_port" ]]; then
    echo "Port $requested_port is busy. Using backend port $port instead."
  fi

  local python_cmd="python3"
  if [[ -x "$PYTHON_BIN" ]]; then
    python_cmd="$PYTHON_BIN"
  fi

  echo "Starting backend on http://localhost:$port ..."
  (
    cd "$ROOT_DIR"
    nohup "$python_cmd" main.py serve --host 0.0.0.0 --port "$port" >"$BACKEND_LOG" 2>&1 &
    echo $! >"$BACKEND_PID_FILE"
  )
  echo "$port" >"$BACKEND_PORT_FILE"

  echo "Backend PID: $(cat "$BACKEND_PID_FILE") (port: $port)"
}

start_frontend() {
  local requested_port="$DEFAULT_FRONTEND_PORT"
  local port

  if [[ -f "$FRONTEND_PORT_FILE" ]]; then
    requested_port="$(cat "$FRONTEND_PORT_FILE")"
  fi

  if [[ -f "$FRONTEND_PID_FILE" ]]; then
    local existing_pid
    existing_pid="$(cat "$FRONTEND_PID_FILE")"
    if is_running "$existing_pid"; then
      echo "Frontend already running (PID: $existing_pid, port: $requested_port)"
      return
    fi
    rm -f "$FRONTEND_PID_FILE"
  fi

  port="$(find_free_port "$requested_port")"
  if [[ -z "$port" ]]; then
    echo "Could not find a free frontend port starting from $requested_port."
    return 1
  fi

  if [[ "$port" != "$requested_port" ]]; then
    echo "Port $requested_port is busy. Using frontend port $port instead."
  fi

  local backend_port="$DEFAULT_BACKEND_PORT"
  if [[ -f "$BACKEND_PORT_FILE" ]]; then
    backend_port="$(cat "$BACKEND_PORT_FILE")"
  fi

  echo "Starting frontend on http://localhost:$port ..."
  (
    cd "$ROOT_DIR/frontend"
    VITE_API_URL="http://localhost:$backend_port" \
      nohup npm run dev -- --host 0.0.0.0 --port "$port" >"$FRONTEND_LOG" 2>&1 &
    echo $! >"$FRONTEND_PID_FILE"
  )
  echo "$port" >"$FRONTEND_PORT_FILE"

  echo "Frontend PID: $(cat "$FRONTEND_PID_FILE") (port: $port)"
}

start_backend
start_frontend

echo
echo "Services started."
if [[ -f "$BACKEND_PORT_FILE" ]]; then
  echo "- Backend URL: http://localhost:$(cat "$BACKEND_PORT_FILE")"
fi
if [[ -f "$FRONTEND_PORT_FILE" ]]; then
  echo "- Frontend URL: http://localhost:$(cat "$FRONTEND_PORT_FILE")"
fi
echo "- Backend log:  $BACKEND_LOG"
echo "- Frontend log: $FRONTEND_LOG"
echo "Use ./stop.sh to stop both services."
