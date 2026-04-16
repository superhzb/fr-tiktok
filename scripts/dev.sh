#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_PORT="${WEB_PORT:-8001}"
REFRESH_MODE="${REFRESH_MODE:-on}"

case "${1:-}" in
  --refresh)
    REFRESH_MODE="on"
    ;;
  --no-refresh)
    REFRESH_MODE="off"
    ;;
  "")
    ;;
  *)
    echo "Usage: $0 [--refresh|--no-refresh]" >&2
    exit 1
    ;;
esac

if [[ "$REFRESH_MODE" == "on" ]]; then
  ORCH_REFRESH_FLAG="--refresh"
elif [[ "$REFRESH_MODE" == "off" ]]; then
  ORCH_REFRESH_FLAG="--no-refresh"
else
  echo "REFRESH_MODE must be 'on' or 'off'" >&2
  exit 1
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
  npm run dev -- --host "$WEB_HOST" --port "$WEB_PORT" --strictPort
) &
WEB_PID=$!

echo "Backend:  http://$API_HOST:$API_PORT"
echo "Frontend: http://$WEB_HOST:$WEB_PORT"
echo "Refresh:  $REFRESH_MODE"
echo "LAN/Tailscale: use this machine's LAN IP or Tailscale IP on port $WEB_PORT"
echo "If using a Tailscale hostname, set VITE_ALLOWED_HOSTS before starting."

wait "$API_PID" "$WEB_PID"
