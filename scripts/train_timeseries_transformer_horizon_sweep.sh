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
OUT_ROOT="${OUT_ROOT:-data/checkpoints/timeseries_transformer_sweep}"

LOOKBACK="${LOOKBACK:-256}"
STRIDE="${STRIDE:-1}"
MAX_GAP_SECONDS="${MAX_GAP_SECONDS:-0}"
TARGET_MODE="${TARGET_MODE:-mean}"

EPOCHS="${EPOCHS:-20}"
BATCH_SIZE="${BATCH_SIZE:-128}"
LEARNING_RATE="${LEARNING_RATE:-0.001}"
WEIGHT_DECAY="${WEIGHT_DECAY:-0.0001}"
D_MODEL="${D_MODEL:-128}"
NHEAD="${NHEAD:-4}"
NUM_LAYERS="${NUM_LAYERS:-2}"
FF_DIM="${FF_DIM:-256}"
DROPOUT="${DROPOUT:-0.1}"
DEVICE="${DEVICE:-auto}"
RESUME_FROM="${RESUME_FROM:-}"
SAVE_EVERY_EPOCHS="${SAVE_EVERY_EPOCHS:-1}"
KEEP_EPOCH_CHECKPOINTS="${KEEP_EPOCH_CHECKPOINTS:-yes}"

if [[ -z "$DATASETS" && -z "$DATASET_ROOT" ]]; then
  echo "Set DATASETS and/or DATASET_ROOT."
  echo "Examples:"
  echo "  DATASETS='data/raw/site_a.parquet data/raw/site_b.parquet' bash scripts/train_timeseries_transformer_horizon_sweep.sh"
  echo "  DATASET_ROOT='data/raw/plc/bluerock' DATE_FROM='2025-01-01' DATE_TO='2025-12-31' TIMESTAMP_COL=plctime bash scripts/train_timeseries_transformer_horizon_sweep.sh"
  exit 1
fi

mkdir -p "$OUT_ROOT"

for H in 1m 1h 6h 24h; do
  OUT_DIR="$OUT_ROOT/horizon_${H}"
  mkdir -p "$OUT_DIR"

  CMD=(
    "$PYTHON_BIN" -m python.ml.cli.timeseries_transformer_train
    --out-dir "$OUT_DIR"
    --timestamp-col "$TIMESTAMP_COL"
    --horizon "$H"
    --lookback "$LOOKBACK"
    --stride "$STRIDE"
    --max-gap-seconds "$MAX_GAP_SECONDS"
    --target-mode "$TARGET_MODE"
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
    --save-every-epochs "$SAVE_EVERY_EPOCHS"
    --keep-epoch-checkpoints "$KEEP_EPOCH_CHECKPOINTS"
  )
  if [[ -n "$RESUME_FROM" ]]; then
    CMD+=(--resume-from "$RESUME_FROM")
  fi

  if [[ -n "$DATASETS" ]]; then
    # shellcheck disable=SC2206
    DATASET_ARR=($DATASETS)
    CMD+=(--dataset "${DATASET_ARR[@]}")
  fi
  if [[ -n "$DATASET_ROOT" ]]; then
    CMD+=(--dataset-root "$DATASET_ROOT" --dataset-filename "$DATASET_FILENAME")
    if [[ -n "$DATE_FROM" ]]; then
      CMD+=(--date-from "$DATE_FROM")
    fi
    if [[ -n "$DATE_TO" ]]; then
      CMD+=(--date-to "$DATE_TO")
    fi
  fi

  if [[ -n "$GROUP_COL" ]]; then
    CMD+=(--group-col "$GROUP_COL")
  fi
  if [[ -n "$FEATURE_COLS" ]]; then
    CMD+=(--feature-cols "$FEATURE_COLS")
  fi

  echo "[RUN] horizon=$H out=$OUT_DIR"
  # shellcheck disable=SC2086
  "${CMD[@]}"
done

echo "[DONE] Sweep complete -> $OUT_ROOT"
