#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

DATASET="${DATASET:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/samples.parquet}"
SPLIT="${SPLIT:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/split_manifest.parquet}"

OUT_DIR="${OUT_DIR:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_panns_embedding_experiment}"
TASK="${TASK:-multiclass}"
TARGET_COL="${TARGET_COL:-primary_class}"
AUDIO_PATH_COL="${AUDIO_PATH_COL:-segment_path}"
TARGET_SECONDS="${TARGET_SECONDS:-10}"

RUN_PARTIAL_FINETUNE="${RUN_PARTIAL_FINETUNE:-yes}"
FINETUNE_EPOCHS="${FINETUNE_EPOCHS:-5}"
FINETUNE_BATCH_SIZE="${FINETUNE_BATCH_SIZE:-8}"
FINETUNE_LR_HEAD="${FINETUNE_LR_HEAD:-1e-3}"
FINETUNE_LR_BACKBONE="${FINETUNE_LR_BACKBONE:-1e-5}"
FINETUNE_UNFREEZE_MODULES="${FINETUNE_UNFREEZE_MODULES:-1}"

cd "$REPO"
mkdir -p "$OUT_DIR"

"$PYTHON" -m python.ml.cli.audio_pretrained_embedding_train \
  --dataset "$DATASET" \
  --split-manifest "$SPLIT" \
  --split-col split \
  --dataset-id-col sample_id \
  --split-id-col sample_id \
  --audio-path-col "$AUDIO_PATH_COL" \
  --out-dir "$OUT_DIR" \
  --backend panns \
  --task "$TASK" \
  --target-col "$TARGET_COL" \
  --target-seconds "$TARGET_SECONDS" \
  --run-partial-finetune "$RUN_PARTIAL_FINETUNE" \
  --finetune-epochs "$FINETUNE_EPOCHS" \
  --finetune-batch-size "$FINETUNE_BATCH_SIZE" \
  --finetune-lr-head "$FINETUNE_LR_HEAD" \
  --finetune-lr-backbone "$FINETUNE_LR_BACKBONE" \
  --finetune-unfreeze-modules "$FINETUNE_UNFREEZE_MODULES"

echo "[OK] metrics -> $OUT_DIR/audio_pretrained_embedding_metrics.json"
