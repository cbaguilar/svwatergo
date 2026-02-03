#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8080}"
HOST="http://localhost:${PORT}"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

mkdir -p "${ROOT_DIR}/data"

( cd "${ROOT_DIR}" && go run ./cmd/server ) &
SERVER_PID=$!

# wait for server to start
for i in {1..20}; do
  if curl -sS "${HOST}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

echo "Server running on ${HOST} (pid ${SERVER_PID})"

HOST="${HOST}" "${ROOT_DIR}/scripts/test_upload_json.sh"
HOST="${HOST}" "${ROOT_DIR}/scripts/test_upload_zip.sh"
HOST="${HOST}" "${ROOT_DIR}/scripts/test_series.sh"
