#!/usr/bin/env bash
set -euo pipefail

# Build 10s audio_event_dataset for all major sites.
#
# Example:
#   bash scripts/build_audio_event_dataset_all_sites_10s.sh
#   SKIP_EXISTING=yes SKIP_WYZE_CONVERSION=yes \
#     bash scripts/build_audio_event_dataset_all_sites_10s.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_SCRIPT="${SCRIPT_DIR}/build_audio_event_dataset_10s.sh"

if [[ ! -f "$BASE_SCRIPT" ]]; then
  echo "[fatal] missing base script: $BASE_SCRIPT"
  exit 1
fi

PYTHON="${PYTHON:-/home/cbaguilar/miniforge3/envs/rapids-cu13/bin/python}"
RAW_ROOT="${RAW_ROOT:-/mnt/d/datasets/svwatergo/raw}"
OUT_ROOT="${OUT_ROOT:-/mnt/d/datasets/svwatergo/derived}"
INCLUDE_RPI="${INCLUDE_RPI:-yes}"
INCLUDE_WYZE="${INCLUDE_WYZE:-yes}"
SKIP_EXISTING="${SKIP_EXISTING:-yes}"
SKIP_WYZE_CONVERSION="${SKIP_WYZE_CONVERSION:-yes}"
WINDOW_SECONDS="${WINDOW_SECONDS:-10}"
STRIDE_SECONDS="${STRIDE_SECONDS:-10}"
MEL_NORMALIZATION="${MEL_NORMALIZATION:-log_db}"
SITE_LIST="${SITE_LIST:-bluerock,santateresa,pryorfarm}"

IFS=',' read -r -a SITES <<< "$SITE_LIST"
for SITE_RAW in "${SITES[@]}"; do
  SITE="$(echo "$SITE_RAW" | xargs)"
  [[ -z "$SITE" ]] && continue
  echo
  echo "============================================================"
  echo "[site] $SITE"
  echo "============================================================"
  SITE="$SITE" \
  PYTHON="$PYTHON" \
  RAW_ROOT="$RAW_ROOT" \
  OUT_ROOT="$OUT_ROOT" \
  INCLUDE_RPI="$INCLUDE_RPI" \
  INCLUDE_WYZE="$INCLUDE_WYZE" \
  SKIP_EXISTING="$SKIP_EXISTING" \
  SKIP_WYZE_CONVERSION="$SKIP_WYZE_CONVERSION" \
  WINDOW_SECONDS="$WINDOW_SECONDS" \
  STRIDE_SECONDS="$STRIDE_SECONDS" \
  MEL_NORMALIZATION="$MEL_NORMALIZATION" \
  bash "$BASE_SCRIPT"
done

echo
echo "[done] all requested sites built"
