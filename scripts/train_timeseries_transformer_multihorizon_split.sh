#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
DATASETS="${DATASETS:-}"
DATASET_ROOT="${DATASET_ROOT:-}"
DATASET_FILENAME="${DATASET_FILENAME:-data.parquet}"
DATE_FROM="${DATE_FROM:-}"
DATE_TO="${DATE_TO:-}"
TIMESTAMP_COL="${TIMESTAMP_COL:-timestamp}"
GROUP_COL="${GROUP_COL:-}"
FEATURE_COLS="${FEATURE_COLS:-}"
FEATURE_PRESET="${FEATURE_PRESET:-auto}"
SITE="${SITE:-}"
OUT_ROOT="${OUT_ROOT:-data/checkpoints/timeseries_transformer_multihorizon_split}"

SHORT_HORIZONS="${SHORT_HORIZONS:-1m,1h}"
SHORT_HORIZON_WEIGHTS="${SHORT_HORIZON_WEIGHTS:-1.0,1.0}"
SHORT_LOOKBACK="${SHORT_LOOKBACK:-512}"
SHORT_STRIDE="${SHORT_STRIDE:-10}"
SHORT_TARGET_MODE="${SHORT_TARGET_MODE:-last}"

LONG_HORIZONS="${LONG_HORIZONS:-6h,24h}"
LONG_HORIZON_WEIGHTS="${LONG_HORIZON_WEIGHTS:-1.0,2.0}"
LONG_LOOKBACK="${LONG_LOOKBACK:-512}"
LONG_STRIDE="${LONG_STRIDE:-10}"
LONG_TARGET_MODE="${LONG_TARGET_MODE:-mean}"

EPOCHS="${EPOCHS:-10}"
BATCH_SIZE="${BATCH_SIZE:-128}"
LEARNING_RATE="${LEARNING_RATE:-0.001}"
WEIGHT_DECAY="${WEIGHT_DECAY:-0.0001}"
D_MODEL="${D_MODEL:-128}"
NHEAD="${NHEAD:-4}"
NUM_LAYERS="${NUM_LAYERS:-2}"
FF_DIM="${FF_DIM:-256}"
DROPOUT="${DROPOUT:-0.1}"
DEVICE="${DEVICE:-auto}"
DATALOADER_NUM_WORKERS="${DATALOADER_NUM_WORKERS:-8}"
REGRESSION_TASK_WEIGHT="${REGRESSION_TASK_WEIGHT:-1.0}"
BINARY_TASK_WEIGHT="${BINARY_TASK_WEIGHT:-1.0}"
STATE_TASK_WEIGHT="${STATE_TASK_WEIGHT:-1.0}"

if [[ -z "$DATASETS" && -z "$DATASET_ROOT" ]]; then
  echo "Set DATASETS and/or DATASET_ROOT"
  exit 1
fi

COMMON_ARGS=(
  --timestamp-col "$TIMESTAMP_COL"
  --epochs "$EPOCHS"
  --batch-size "$BATCH_SIZE"
  --learning-rate "$LEARNING_RATE"
  --weight-decay "$WEIGHT_DECAY"
  --d-model "$D_MODEL"
  --nhead "$NHEAD"
  --num-layers "$NUM_LAYERS"
  --ff-dim "$FF_DIM"
  --dropout "$DROPOUT"
  --device "$DEVICE"
  --dataloader-num-workers "$DATALOADER_NUM_WORKERS"
  --feature-preset "$FEATURE_PRESET"
  --regression-task-weight "$REGRESSION_TASK_WEIGHT"
  --binary-task-weight "$BINARY_TASK_WEIGHT"
  --state-task-weight "$STATE_TASK_WEIGHT"
)

if [[ -n "$DATASETS" ]]; then
  # shellcheck disable=SC2206
  DATASET_ARR=($DATASETS)
  COMMON_ARGS+=(--dataset "${DATASET_ARR[@]}")
fi
if [[ -n "$DATASET_ROOT" ]]; then
  COMMON_ARGS+=(--dataset-root "$DATASET_ROOT" --dataset-filename "$DATASET_FILENAME")
  if [[ -n "$DATE_FROM" ]]; then
    COMMON_ARGS+=(--date-from "$DATE_FROM")
  fi
  if [[ -n "$DATE_TO" ]]; then
    COMMON_ARGS+=(--date-to "$DATE_TO")
  fi
fi
if [[ -n "$GROUP_COL" ]]; then
  COMMON_ARGS+=(--group-col "$GROUP_COL")
fi
if [[ -n "$FEATURE_COLS" ]]; then
  COMMON_ARGS+=(--feature-cols "$FEATURE_COLS")
fi
if [[ -n "$SITE" ]]; then
  COMMON_ARGS+=(--site "$SITE")
fi

mkdir -p "$OUT_ROOT"

echo "[RUN] split multihorizon short out=$OUT_ROOT/short"
"$PYTHON_BIN" -m python.ml.cli.timeseries_transformer_multihorizon_train \
  "${COMMON_ARGS[@]}" \
  --out-dir "$OUT_ROOT/short" \
  --horizons "$SHORT_HORIZONS" \
  --horizon-weights "$SHORT_HORIZON_WEIGHTS" \
  --lookback "$SHORT_LOOKBACK" \
  --stride "$SHORT_STRIDE" \
  --target-mode "$SHORT_TARGET_MODE"

echo "[RUN] split multihorizon long out=$OUT_ROOT/long"
"$PYTHON_BIN" -m python.ml.cli.timeseries_transformer_multihorizon_train \
  "${COMMON_ARGS[@]}" \
  --out-dir "$OUT_ROOT/long" \
  --horizons "$LONG_HORIZONS" \
  --horizon-weights "$LONG_HORIZON_WEIGHTS" \
  --lookback "$LONG_LOOKBACK" \
  --stride "$LONG_STRIDE" \
  --target-mode "$LONG_TARGET_MODE"
