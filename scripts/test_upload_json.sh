#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-http://localhost:8080}"

payload='[
  {
    "location": "bluerock",
    "plctime": "PLC#2026-02-03T12:00:00Z",
    "permeateflow": "1.25",
    "feedflow": "2.50",
    "deliveryflow": "5.00",
    "alarm": "0"
  }
]'

echo "POST ${HOST}/uploadDataNew (JSON)"

curl -sS -X POST "${HOST}/uploadDataNew" \
  -H "Content-Type: application/json" \
  -d "${payload}"
