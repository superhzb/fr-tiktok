#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-19099}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_PORT="${WEB_PORT:-19102}"
REFRESH_MODE="${REFRESH_MODE:-on}"

usage() {
  cat >&2 <<EOF
Usage: $0 [--refresh|--no-refresh] [--api-host HOST] [--api-port PORT] [--web-host HOST] [--web-port PORT]

Environment defaults:
  API_HOST=$API_HOST
  API_PORT=$API_PORT
  WEB_HOST=$WEB_HOST
  WEB_PORT=$WEB_PORT
  REFRESH_MODE=$REFRESH_MODE
EOF
}

require_value() {
  local flag="$1"
  local value="${2:-}"
  if [[ -z "$value" || "$value" == --* ]]; then
    echo "$flag requires a value" >&2
    usage
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --refresh)
      REFRESH_MODE="on"
      shift
      ;;
    --no-refresh)
      REFRESH_MODE="off"
      shift
      ;;
    --api-host)
      require_value "$1" "${2:-}"
      API_HOST="$2"
      shift 2
      ;;
    --api-port)
      require_value "$1" "${2:-}"
      API_PORT="$2"
      shift 2
      ;;
    --web-host)
      require_value "$1" "${2:-}"
      WEB_HOST="$2"
      shift 2
      ;;
    --web-port)
      require_value "$1" "${2:-}"
      WEB_PORT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$REFRESH_MODE" == "on" ]]; then
  ORCH_REFRESH_FLAG="--refresh"
elif [[ "$REFRESH_MODE" == "off" ]]; then
  ORCH_REFRESH_FLAG="--no-refresh"
else
  echo "REFRESH_MODE must be 'on' or 'off'" >&2
  exit 1
fi

API_PROXY_HOST="$API_HOST"
if [[ "$API_PROXY_HOST" == "0.0.0.0" || "$API_PROXY_HOST" == "::" ]]; then
  API_PROXY_HOST="127.0.0.1"
fi

cd "$ROOT_DIR"

cleanup() {
  local exit_code=$?
  if [[ -n "${API_PID:-}" ]] && kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
  fi
  if [[ -n "${WEB_PID:-}" ]] && kill -0 "$WEB_PID" 2>/dev/null; then
    kill "$WEB_PID" 2>/dev/null || true
  fi
  wait "${API_PID:-}" "${WEB_PID:-}" 2>/dev/null || true
  exit "$exit_code"
}

trap cleanup INT TERM EXIT

uv run --package tk-orchestrator tk-orch start --host "$API_HOST" --port "$API_PORT" "$ORCH_REFRESH_FLAG" &
API_PID=$!

(
  cd "$ROOT_DIR/tk-web"
  VITE_API_TARGET="http://$API_PROXY_HOST:$API_PORT" npm run dev -- --host "$WEB_HOST" --port "$WEB_PORT" --strictPort
) &
WEB_PID=$!

echo "Backend:  http://$API_HOST:$API_PORT"
echo "Frontend: http://$WEB_HOST:$WEB_PORT"
echo "Refresh:  $REFRESH_MODE"
echo "LAN/Tailscale: use this machine's LAN IP or Tailscale IP on port $WEB_PORT"
echo "If using a Tailscale hostname, set VITE_ALLOWED_HOSTS before starting."

wait "$API_PID" "$WEB_PID"
