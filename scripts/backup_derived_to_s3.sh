#!/usr/bin/env bash
set -euo pipefail

# Backup derived artifacts to S3.
#
# Modes:
# - DATASET_ONLY=yes  -> only dataset=audio_event_dataset
# - DATASET_ONLY=no   -> dataset + intermediate + checkpoints + plots
#
# Example:
#   bash scripts/backup_derived_to_s3.sh
#   DATASET_ONLY=no AWS_PROFILE=prod bash scripts/backup_derived_to_s3.sh

LOCAL_DERIVED="${LOCAL_DERIVED:-/mnt/d/datasets/svwatergo/derived}"
S3_BUCKET="${S3_BUCKET:-svwn-audio-files}"
S3_PREFIX="${S3_PREFIX:-derived}"
AWS_PROFILE="${AWS_PROFILE:-}"
DATASET_ONLY="${DATASET_ONLY:-yes}"
DELETE_MISSING="${DELETE_MISSING:-no}"

run_sync() {
  local src="$1"
  local dst="$2"
  local -a cmd=(s3 sync "$src" "$dst" --exclude "*.tmp" --exclude "*.lock")
  if [[ "$DELETE_MISSING" == "yes" ]]; then
    cmd+=(--delete)
  fi
  echo "[run] aws ${cmd[*]}"
  if [[ -n "$AWS_PROFILE" ]]; then
    AWS_PROFILE="$AWS_PROFILE" aws "${cmd[@]}"
  else
    aws "${cmd[@]}"
  fi
}

if [[ ! -d "$LOCAL_DERIVED" ]]; then
  echo "[fatal] local derived dir not found: $LOCAL_DERIVED"
  exit 1
fi

run_sync \
  "$LOCAL_DERIVED/dataset=audio_event_dataset" \
  "s3://$S3_BUCKET/$S3_PREFIX/dataset=audio_event_dataset"

if [[ "$DATASET_ONLY" != "yes" ]]; then
  run_sync \
    "$LOCAL_DERIVED/intermediate" \
    "s3://$S3_BUCKET/$S3_PREFIX/intermediate"
  run_sync \
    "$LOCAL_DERIVED/checkpoints" \
    "s3://$S3_BUCKET/$S3_PREFIX/checkpoints"
  run_sync \
    "$LOCAL_DERIVED/plots" \
    "s3://$S3_BUCKET/$S3_PREFIX/plots"
fi

echo "[ok] backup complete"
