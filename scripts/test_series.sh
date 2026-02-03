#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-http://localhost:8080}"
SITE="${SITE:-bluerock}"

START="${START:-2026-02-03T12:00:00Z}"
END="${END:-2026-02-03T12:10:00Z}"
FIELDS="${FIELDS:-plctime,permeateflow,feedflow,deliveryflow}"

url="${HOST}/api/v1/sites/${SITE}/series?start=${START}&end=${END}&fields=${FIELDS}&format=columns"

echo "GET ${url}"

curl -sS "${url}"
