#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

SITE_LIST="${SITE_LIST:-bluerock,pryorfarm,santateresa}"
WINDOW_S="${WINDOW_S:-10}"
PLC_PCA_COMPONENTS="${PLC_PCA_COMPONENTS:-8}"
PLC_PCA_FILL_VALUE="${PLC_PCA_FILL_VALUE:-0.0}"
PLC_PCA_CLIP_ABS="${PLC_PCA_CLIP_ABS:-}"
PLC_PCA_CONTROLS_WEIGHT="${PLC_PCA_CONTROLS_WEIGHT:-1.0}"
PLC_PCA_FIT_SPLIT="${PLC_PCA_FIT_SPLIT:-train}"
PLC_PCA_COLS="${PLC_PCA_COLS:-}"
PLC_PCA_INCLUDE_REGEX_LIST="${PLC_PCA_INCLUDE_REGEX_LIST:-}"
PLC_PCA_EXCLUDE_REGEX_LIST="${PLC_PCA_EXCLUDE_REGEX_LIST:-}"

resolve_dataset_root() {
  local site="$1"
  case "$site" in
    bluerock)
      DATASET_ROOT="/mnt/d/datasets/svwatergo/derived/dataset=audio_actuation_dataset/site=bluerock/window_s=${WINDOW_S}"
      ;;
    pryorfarm)
      DATASET_ROOT="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm/dataset=audio_actuation_dataset/site=pryorfarm/window_s=${WINDOW_S}"
      ;;
    santateresa)
      DATASET_ROOT="/mnt/d/datasets/svwatergo/derived_wyze_santateresa/dataset=audio_actuation_dataset/site=santateresa/window_s=${WINDOW_S}"
      ;;
    *)
      echo "unknown site: $site" >&2
      exit 2
      ;;
  esac
}

cd "$REPO"

IFS=',' read -r -a SITES <<< "$SITE_LIST"
for SITE in "${SITES[@]}"; do
  SITE="$(echo "$SITE" | xargs)"
  [[ -n "$SITE" ]] || continue
  resolve_dataset_root "$SITE"
  echo "[RUN] backfill PLC PCA site=$SITE"
  echo "      dataset_root=$DATASET_ROOT"
  DATASET_ROOT="$DATASET_ROOT" \
  PLC_PCA_COMPONENTS="$PLC_PCA_COMPONENTS" \
  PLC_PCA_FILL_VALUE="$PLC_PCA_FILL_VALUE" \
  PLC_PCA_CLIP_ABS="$PLC_PCA_CLIP_ABS" \
  PLC_PCA_CONTROLS_WEIGHT="$PLC_PCA_CONTROLS_WEIGHT" \
  PLC_PCA_FIT_SPLIT="$PLC_PCA_FIT_SPLIT" \
  PLC_PCA_COLS="$PLC_PCA_COLS" \
  PLC_PCA_INCLUDE_REGEX_LIST="$PLC_PCA_INCLUDE_REGEX_LIST" \
  PLC_PCA_EXCLUDE_REGEX_LIST="$PLC_PCA_EXCLUDE_REGEX_LIST" \
  PYTHON="$PYTHON" \
  bash "$SCRIPT_DIR/backfill_actuation_plc_pca.sh"
done
