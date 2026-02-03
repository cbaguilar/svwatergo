#!/usr/bin/env bash
set -euo pipefail

BASE_URL=${BASE_URL:-http://localhost:8080}
SITE=${SITE:-bluerock}
AUTH_BEARER=${AUTH_BEARER:-}

AUTH_HEADER=()
if [[ -n "$AUTH_BEARER" ]]; then
  AUTH_HEADER=( -H "Authorization: Bearer ${AUTH_BEARER}" )
fi

create_payload='{
  "title": "Operator note: RO skid check",
  "body": "Observed mild vibration on P1. Will re-check after next flush.",
  "severity": "low",
  "tags": ["maintenance", "ro"]
}'

echo "Creating report..."
create_resp=$(curl -sS -X POST "${BASE_URL}/api/v1/sites/${SITE}/operator-reports" \
  -H "Content-Type: application/json" \
  "${AUTH_HEADER[@]}" \
  -d "$create_payload")

echo "$create_resp"

report_id=$(python - <<'PY'
import json, sys
try:
    data = json.loads(sys.stdin.read())
    print(data.get("id", ""))
except Exception:
    print("")
PY
)

if [[ -z "$report_id" ]]; then
  echo "Report id not found in response. Skipping update/delete."
  exit 0
fi

echo "Listing reports..."
curl -sS "${BASE_URL}/api/v1/sites/${SITE}/operator-reports?limit=5" "${AUTH_HEADER[@]}"
echo

echo "Updating report ${report_id}..."
update_payload='{
  "status": "resolved",
  "severity": "info"
}'
curl -sS -X PUT "${BASE_URL}/api/v1/sites/${SITE}/operator-reports/${report_id}" \
  -H "Content-Type: application/json" \
  "${AUTH_HEADER[@]}" \
  -d "$update_payload"
echo

echo "Deleting report ${report_id}..."
curl -sS -X DELETE "${BASE_URL}/api/v1/sites/${SITE}/operator-reports/${report_id}" \
  "${AUTH_HEADER[@]}"
echo
