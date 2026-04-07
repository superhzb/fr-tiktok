#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_PORT="${WEB_PORT:-5173}"

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

uv run --package tk-orchestrator tk-orch start --host "$API_HOST" --port "$API_PORT" &
API_PID=$!

(
  cd "$ROOT_DIR/tk-web"
  npm run dev -- --host "$WEB_HOST" --port "$WEB_PORT" --strictPort
) &
WEB_PID=$!

echo "Backend:  http://$API_HOST:$API_PORT"
echo "Frontend: http://$WEB_HOST:$WEB_PORT"
echo "LAN/Tailscale: use this machine's LAN IP or Tailscale IP on port $WEB_PORT"
echo "If using a Tailscale hostname, set VITE_ALLOWED_HOSTS before starting."

wait "$API_PID" "$WEB_PID"
