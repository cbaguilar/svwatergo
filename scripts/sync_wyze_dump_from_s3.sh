#!/usr/bin/env bash
set -euo pipefail

# Sync Wyze raw clips from S3 to local raw root.
#
# Example:
#   bash scripts/sync_wyze_dump_from_s3.sh
#   AWS_PROFILE=prod bash scripts/sync_wyze_dump_from_s3.sh

S3_URI="${S3_URI:-s3://svwn-audio-files/wyze_dump}"
LOCAL_DIR="${LOCAL_DIR:-/mnt/d/datasets/svwatergo/raw/wyze_dump}"
EXACT_TIMESTAMPS="${EXACT_TIMESTAMPS:-no}"
DELETE_MISSING="${DELETE_MISSING:-no}"
AWS_PROFILE="${AWS_PROFILE:-}"

mkdir -p "$LOCAL_DIR"

args=(
  s3
  sync
  "$S3_URI"
  "$LOCAL_DIR"
)

if [[ "$EXACT_TIMESTAMPS" == "yes" ]]; then
  args+=(--exact-timestamps)
fi
if [[ "$DELETE_MISSING" == "yes" ]]; then
  args+=(--delete)
fi

echo "[run] aws ${args[*]}"
if [[ -n "$AWS_PROFILE" ]]; then
  AWS_PROFILE="$AWS_PROFILE" aws "${args[@]}"
else
  aws "${args[@]}"
fi

echo "[ok] synced wyze dump"
