#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

WINDOW_S="${WINDOW_S:-10}"
SITE_LIST="${SITE_LIST:-pryorfarm,santateresa}"
OUT_ROOT_PRYOR="${OUT_ROOT_PRYOR:-/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm_5actsplit}"
OUT_ROOT_SANTATERESA="${OUT_ROOT_SANTATERESA:-/mnt/d/datasets/svwatergo/derived_wyze_santateresa_5actsplit}"
SPLIT_SEED="${SPLIT_SEED:-1337}"
TRAIN_RATIO="${TRAIN_RATIO:-0.70}"
TEST_RATIO="${TEST_RATIO:-0.15}"
VAL_RATIO="${VAL_RATIO:-0.15}"
SPLIT_ACTUATORS="${SPLIT_ACTUATORS:-ropumprun,wellpumprun,feedpumprun,deliveryrun,flushrun}"
SPLIT_MIN_POSITIVE_COUNT="${SPLIT_MIN_POSITIVE_COUNT:-3}"
COPY_ARTIFACTS="${COPY_ARTIFACTS:-yes}"

resolve_roots() {
  local site="$1"
  case "$site" in
    pryorfarm)
      DATASET_ROOT="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm/dataset=audio_actuation_dataset/site=pryorfarm/window_s=${WINDOW_S}"
      OUT_DATASET_ROOT="${OUT_ROOT_PRYOR}/dataset=audio_actuation_dataset/site=pryorfarm/window_s=${WINDOW_S}"
      ;;
    santateresa)
      DATASET_ROOT="/mnt/d/datasets/svwatergo/derived_wyze_santateresa/dataset=audio_actuation_dataset/site=santateresa/window_s=${WINDOW_S}"
      OUT_DATASET_ROOT="${OUT_ROOT_SANTATERESA}/dataset=audio_actuation_dataset/site=santateresa/window_s=${WINDOW_S}"
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
  resolve_roots "$SITE"
  echo "[RUN] resplit site=$SITE"
  echo "      dataset_root=$DATASET_ROOT"
  echo "      out_dataset_root=$OUT_DATASET_ROOT"
  DATASET_ROOT="$DATASET_ROOT" \
  OUT_DATASET_ROOT="$OUT_DATASET_ROOT" \
  SPLIT_SEED="$SPLIT_SEED" \
  TRAIN_RATIO="$TRAIN_RATIO" \
  TEST_RATIO="$TEST_RATIO" \
  VAL_RATIO="$VAL_RATIO" \
  SPLIT_ACTUATORS="$SPLIT_ACTUATORS" \
  SPLIT_MIN_POSITIVE_COUNT="$SPLIT_MIN_POSITIVE_COUNT" \
  COPY_ARTIFACTS="$COPY_ARTIFACTS" \
  PYTHON="$PYTHON" \
  bash "$SCRIPT_DIR/resplit_actuation_dataset.sh"
done
