#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

DATASET_ROOT="${DATASET_ROOT:-}"
SAMPLES_PARQUET="${SAMPLES_PARQUET:-}"
PLC_PCA_COMPONENTS="${PLC_PCA_COMPONENTS:-8}"
PLC_PCA_FILL_VALUE="${PLC_PCA_FILL_VALUE:-0.0}"
PLC_PCA_CLIP_ABS="${PLC_PCA_CLIP_ABS:-}"
PLC_PCA_CONTROLS_WEIGHT="${PLC_PCA_CONTROLS_WEIGHT:-1.0}"
PLC_PCA_FIT_SPLIT="${PLC_PCA_FIT_SPLIT:-train}"
PLC_PCA_COLS="${PLC_PCA_COLS:-}"
PLC_PCA_INCLUDE_REGEX_LIST="${PLC_PCA_INCLUDE_REGEX_LIST:-}"
PLC_PCA_EXCLUDE_REGEX_LIST="${PLC_PCA_EXCLUDE_REGEX_LIST:-}"

if [[ -z "$DATASET_ROOT" ]]; then
  echo "DATASET_ROOT is required" >&2
  exit 2
fi

cd "$REPO"

args=(
  python/analytics/backfill_actuation_plc_pca.py
  --dataset-root "$DATASET_ROOT"
  --plc-pca-components "$PLC_PCA_COMPONENTS"
  --plc-pca-fill-value "$PLC_PCA_FILL_VALUE"
  --plc-pca-controls-weight "$PLC_PCA_CONTROLS_WEIGHT"
  --plc-pca-fit-split "$PLC_PCA_FIT_SPLIT"
)

if [[ -n "$SAMPLES_PARQUET" ]]; then
  args+=(--samples-parquet "$SAMPLES_PARQUET")
fi
if [[ -n "$PLC_PCA_CLIP_ABS" ]]; then
  args+=(--plc-pca-clip-abs "$PLC_PCA_CLIP_ABS")
fi
if [[ -n "$PLC_PCA_COLS" ]]; then
  args+=(--plc-pca-cols "$PLC_PCA_COLS")
fi
if [[ -n "$PLC_PCA_INCLUDE_REGEX_LIST" ]]; then
  IFS=',' read -r -a _inc <<< "$PLC_PCA_INCLUDE_REGEX_LIST"
  for p in "${_inc[@]}"; do
    p="$(echo "$p" | xargs)"
    [[ -n "$p" ]] && args+=(--plc-pca-include-regex "$p")
  done
fi
if [[ -n "$PLC_PCA_EXCLUDE_REGEX_LIST" ]]; then
  IFS=',' read -r -a _exc <<< "$PLC_PCA_EXCLUDE_REGEX_LIST"
  for p in "${_exc[@]}"; do
    p="$(echo "$p" | xargs)"
    [[ -n "$p" ]] && args+=(--plc-pca-exclude-regex "$p")
  done
fi

"$PYTHON" "${args[@]}"
