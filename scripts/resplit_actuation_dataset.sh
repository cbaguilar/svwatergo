#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

DATASET_ROOT="${DATASET_ROOT:-}"
OUT_DATASET_ROOT="${OUT_DATASET_ROOT:-}"
SAMPLES_PARQUET="${SAMPLES_PARQUET:-}"
SPLIT_SEED="${SPLIT_SEED:-1337}"
TRAIN_RATIO="${TRAIN_RATIO:-0.70}"
TEST_RATIO="${TEST_RATIO:-0.15}"
VAL_RATIO="${VAL_RATIO:-0.15}"
SPLIT_ACTUATORS="${SPLIT_ACTUATORS:-ropumprun,wellpumprun,feedpumprun,deliveryrun,flushrun}"
SPLIT_MIN_POSITIVE_COUNT="${SPLIT_MIN_POSITIVE_COUNT:-3}"
COPY_ARTIFACTS="${COPY_ARTIFACTS:-yes}"

if [[ -z "$DATASET_ROOT" ]]; then
  echo "DATASET_ROOT is required" >&2
  exit 2
fi

cd "$REPO"

args=(
  python/analytics/resplit_actuation_dataset.py
  --dataset-root "$DATASET_ROOT"
  --split-seed "$SPLIT_SEED"
  --train-ratio "$TRAIN_RATIO"
  --test-ratio "$TEST_RATIO"
  --val-ratio "$VAL_RATIO"
  --split-actuators "$SPLIT_ACTUATORS"
  --split-min-positive-count "$SPLIT_MIN_POSITIVE_COUNT"
  --copy-artifacts "$COPY_ARTIFACTS"
)

if [[ -n "$OUT_DATASET_ROOT" ]]; then
  args+=(--out-dataset-root "$OUT_DATASET_ROOT")
fi
if [[ -n "$SAMPLES_PARQUET" ]]; then
  args+=(--samples-parquet "$SAMPLES_PARQUET")
fi

"$PYTHON" "${args[@]}"
