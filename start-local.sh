#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-7070}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_DB_URL="${BACKEND_DB_URL:-sqlite:///./local-dev.db}"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
FRONTEND_API_BASE_URL="${VITE_API_BASE_URL:-${BACKEND_URL}/api/v1}"
ENABLED_SOURCES_RAW="${ENABLED_SOURCES_RAW:-amazon,flipkart,poorvika,reliance-digital,croma,moglix,robu,electronicscomp,ibo,global-electronics}"
DEGRADED_SOURCES_RAW="${DEGRADED_SOURCES_RAW:-}"
PRIMARY_SOURCES_RAW="${PRIMARY_SOURCES_RAW:-amazon,flipkart,poorvika,reliance-digital,croma,moglix,robu,electronicscomp,ibo,global-electronics}"
BACKGROUND_SOURCES_RAW="${BACKGROUND_SOURCES_RAW:-}"

backend_pid=""

require_file() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    echo "Missing required file: $path" >&2
    exit 1
  fi
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
}

port_in_use() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_backend() {
  local attempts=30
  local delay_seconds=1
  local health_url="${BACKEND_URL}/health"

  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    if curl -fsS "$health_url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay_seconds"
  done

  echo "Backend did not become healthy at ${health_url}" >&2
  return 1
}

cleanup() {
  if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" >/dev/null 2>&1; then
    kill "$backend_pid" >/dev/null 2>&1 || true
    wait "$backend_pid" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

require_file "$ROOT_DIR/.env"
require_file "$BACKEND_DIR/.venv/bin/uvicorn"
require_file "$FRONTEND_DIR/package.json"
require_command npm
require_command curl
require_command lsof

if port_in_use "$BACKEND_PORT"; then
  echo "Backend port ${BACKEND_PORT} is already in use." >&2
  exit 1
fi

if port_in_use "$FRONTEND_PORT"; then
  echo "Frontend port ${FRONTEND_PORT} is already in use." >&2
  exit 1
fi

echo "Starting backend on ${BACKEND_URL}"
(
  cd "$BACKEND_DIR"
  env \
    DATABASE_URL="$BACKEND_DB_URL" \
    AUTO_CREATE_SCHEMA=true \
    BOOTSTRAP_VENDORS_ON_STARTUP=true \
    ENVIRONMENT=development \
    ENABLED_SOURCES_RAW="$ENABLED_SOURCES_RAW" \
    DEGRADED_SOURCES_RAW="$DEGRADED_SOURCES_RAW" \
    PRIMARY_SOURCES_RAW="$PRIMARY_SOURCES_RAW" \
    BACKGROUND_SOURCES_RAW="$BACKGROUND_SOURCES_RAW" \
    CORS_ORIGINS_RAW="http://${FRONTEND_HOST}:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT}" \
    ../backend/.venv/bin/uvicorn \
      app.main:app \
      --host "$BACKEND_HOST" \
      --port "$BACKEND_PORT" \
      --env-file ../.env
) &
backend_pid="$!"

wait_for_backend

echo "Starting frontend on http://${FRONTEND_HOST}:${FRONTEND_PORT}"
cd "$FRONTEND_DIR"
env \
  VITE_API_BASE_URL="$FRONTEND_API_BASE_URL" \
  npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
