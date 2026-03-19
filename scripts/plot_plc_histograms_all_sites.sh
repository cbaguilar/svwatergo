#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

LOCAL_ROOT="${LOCAL_ROOT:-/mnt/d/datasets/svwatergo/raw/plc}"
DATE_FROM="${DATE_FROM:-2025-12-01}"
DATE_TO="${DATE_TO:-2025-12-31}"
START_TS="${START_TS:-}"
END_TS="${END_TS:-}"
OUT_DIR="${OUT_DIR:-/mnt/d/datasets/svwatergo/derived/plots/plc_histograms}"
BINS="${BINS:-80}"
MAX_COLS="${MAX_COLS:-24}"
COLS_PER_PAGE="${COLS_PER_PAGE:-6}"
DENSITY="${DENSITY:-no}"
LOG_Y="${LOG_Y:-yes}"
SPLIT_STATE_COL="${SPLIT_STATE_COL:-ropumprun}"
SITES_CSV="${SITES_CSV:-bluerock,pryorfarm,santateresa}"

cd "$REPO"

IFS=',' read -r -a SITES <<< "$SITES_CSV"
for SITE_RAW in "${SITES[@]}"; do
  SITE="$(echo "$SITE_RAW" | xargs)"
  [[ -z "$SITE" ]] && continue

  args=(
    -m python.analytics.plc_signal_histograms
    --local-root "$LOCAL_ROOT"
    --site "$SITE"
    --date-from "$DATE_FROM"
    --date-to "$DATE_TO"
    --bins "$BINS"
    --max-cols "$MAX_COLS"
    --cols-per-page "$COLS_PER_PAGE"
    --out-dir "$OUT_DIR/$SITE"
    --out-prefix "${SITE}_${DATE_FROM}_to_${DATE_TO}"
    --verbose
  )

  if [[ -n "$START_TS" ]]; then
    args+=(--start "$START_TS")
  fi
  if [[ -n "$END_TS" ]]; then
    args+=(--end "$END_TS")
  fi
  if [[ "$DENSITY" == "yes" ]]; then
    args+=(--density)
  fi
  if [[ "$LOG_Y" == "yes" ]]; then
    args+=(--log-y)
  fi
  if [[ -n "$SPLIT_STATE_COL" ]]; then
    args+=(--split-state-col "$SPLIT_STATE_COL")
  fi

  echo "[RUN] site=$SITE date_from=$DATE_FROM date_to=$DATE_TO out_dir=$OUT_DIR/$SITE"
  "$PYTHON" "${args[@]}"
done
