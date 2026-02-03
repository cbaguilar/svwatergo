#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-http://localhost:8080}"
TMPDIR="$(mktemp -d)"
ZIPFILE="${TMPDIR}/payload.zip"

cat > "${TMPDIR}/temp.txt" <<'JSON'
[
  {
    "location": "bluerock",
    "plctime": "PLC#2026-02-03T12:05:00Z",
    "permeateflow": "1.30",
    "feedflow": "2.60",
    "deliveryflow": "5.10",
    "alarm": "0"
  }
]
JSON

python3 - <<PY
import zipfile
zf = zipfile.ZipFile("${ZIPFILE}", "w", zipfile.ZIP_DEFLATED)
zf.write("${TMPDIR}/temp.txt", arcname="temp.txt")
zf.close()
PY

echo "POST ${HOST}/uploadDataNew (ZIP)"

curl -sS -X POST "${HOST}/uploadDataNew" \
  -H "Content-Type: application/zip" \
  --data-binary "@${ZIPFILE}"

rm -rf "${TMPDIR}"
