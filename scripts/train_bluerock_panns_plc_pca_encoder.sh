#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
REPO="${REPO:-$HOME/svwatergo}"

DATASET="${DATASET:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/samples.parquet}"
SPLIT="${SPLIT:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/split_manifest.parquet}"
OUT_DIR="${OUT_DIR:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_panns_plc_pca_encoder}"
# Optional source filter (for example: rpi_audio).
AUDIO_SOURCE_FILTER="${AUDIO_SOURCE_FILTER:-}"
AUDIO_SOURCE_COL="${AUDIO_SOURCE_COL:-audio_source}"
DROP_STATE_UNKNOWN="${DROP_STATE_UNKNOWN:-yes}"
STATE_UNKNOWN_COL="${STATE_UNKNOWN_COL:-state_unknown}"
DROP_STATE_UNKNOWN_SCOPE="${DROP_STATE_UNKNOWN_SCOPE:-train_only}"

TARGET_SECONDS="${TARGET_SECONDS:-10}"
EXTRACT_BATCH_SIZE="${EXTRACT_BATCH_SIZE:-32}"
EXTRACT_NUM_WORKERS="${EXTRACT_NUM_WORKERS:-8}"
EXTRACT_LOG_EVERY="${EXTRACT_LOG_EVERY:-512}"

ENCODER_HIDDEN="${ENCODER_HIDDEN:-512,256}"
ENCODER_DROPOUT="${ENCODER_DROPOUT:-0.2}"
EPOCHS="${EPOCHS:-100}"
BATCH_SIZE="${BATCH_SIZE:-128}"
LEARNING_RATE="${LEARNING_RATE:-1e-3}"
WEIGHT_DECAY="${WEIGHT_DECAY:-1e-4}"
EVAL_EVERY="${EVAL_EVERY:-5}"

# Explicit PCA-encoder objective: frozen embeddings -> PLC PCA.
TASK_MODE="${TASK_MODE:-plc_pca_encoder}"
TARGET_COL="${TARGET_COL:-primary_class}"
TARGET_COLS="${TARGET_COLS:-ropumprun_duty,deliveryrun_duty}"
MAIN_TASK_WEIGHT="${MAIN_TASK_WEIGHT:-0.0}"
PANN_PCA_WEIGHT="${PANN_PCA_WEIGHT:-0.0}"
BEST_MODEL_METRIC="${BEST_MODEL_METRIC:-plc_pca_r2}"
BEST_MODEL_SPLIT="${BEST_MODEL_SPLIT:-val}"

# PLC PCA target definition.
AUX_PLC_PCA="${AUX_PLC_PCA:-yes}"
AUX_PLC_FEATURE_COLS="${AUX_PLC_FEATURE_COLS:-}"
AUX_PLC_INCLUDE_DUTY_COLS="${AUX_PLC_INCLUDE_DUTY_COLS:-yes}"
AUX_PLC_COMPONENTS="${AUX_PLC_COMPONENTS:-8}"
AUX_PLC_VARIANCE_RATIO="${AUX_PLC_VARIANCE_RATIO:-0.0}"
AUX_PLC_WEIGHT="${AUX_PLC_WEIGHT:-1.0}"
PLC_CONTRASTIVE_WEIGHT="${PLC_CONTRASTIVE_WEIGHT:-0.0}"
PLC_CONTRASTIVE_TEMPERATURE="${PLC_CONTRASTIVE_TEMPERATURE:-0.1}"

cd "$REPO"
mkdir -p "$OUT_DIR"

args=(
  -m python.ml.cli.audio_pretrained_embedding_multitask_train
  --dataset "$DATASET"
  --split-manifest "$SPLIT"
  --split-col split
  --dataset-id-col sample_id
  --split-id-col sample_id
  --audio-path-col segment_path
  --source-filter-col "$AUDIO_SOURCE_COL"
  --drop-state-unknown "$DROP_STATE_UNKNOWN"
  --state-unknown-col "$STATE_UNKNOWN_COL"
  --drop-state-unknown-scope "$DROP_STATE_UNKNOWN_SCOPE"
  --out-dir "$OUT_DIR"
  --task-mode "$TASK_MODE"
  --target-col "$TARGET_COL"
  --target-cols "$TARGET_COLS"
  --target-seconds "$TARGET_SECONDS"
  --extract-batch-size "$EXTRACT_BATCH_SIZE"
  --extract-num-workers "$EXTRACT_NUM_WORKERS"
  --extract-log-every "$EXTRACT_LOG_EVERY"
  --encoder-hidden "$ENCODER_HIDDEN"
  --encoder-dropout "$ENCODER_DROPOUT"
  --epochs "$EPOCHS"
  --batch-size "$BATCH_SIZE"
  --learning-rate "$LEARNING_RATE"
  --weight-decay "$WEIGHT_DECAY"
  --eval-every "$EVAL_EVERY"
  --main-task-weight "$MAIN_TASK_WEIGHT"
  --best-model-metric "$BEST_MODEL_METRIC"
  --best-model-split "$BEST_MODEL_SPLIT"
  --aux-plc-pca "$AUX_PLC_PCA"
  --aux-plc-include-duty-cols "$AUX_PLC_INCLUDE_DUTY_COLS"
  --aux-plc-components "$AUX_PLC_COMPONENTS"
  --aux-plc-variance-ratio "$AUX_PLC_VARIANCE_RATIO"
  --aux-plc-weight "$AUX_PLC_WEIGHT"
  --plc-contrastive-weight "$PLC_CONTRASTIVE_WEIGHT"
  --plc-contrastive-temperature "$PLC_CONTRASTIVE_TEMPERATURE"
  --pann-pca-components 8
  --pann-pca-variance-ratio 0.0
  --pann-pca-weight "$PANN_PCA_WEIGHT"
)

if [[ -n "$AUX_PLC_FEATURE_COLS" ]]; then
  args+=(--aux-plc-feature-cols "$AUX_PLC_FEATURE_COLS")
fi
if [[ -n "$AUDIO_SOURCE_FILTER" ]]; then
  args+=(--source-filter-values "$AUDIO_SOURCE_FILTER")
fi

"$PYTHON" "${args[@]}"

echo "[OK] model(last) -> $OUT_DIR/audio_pretrained_embedding_multitask.pt"
echo "[OK] model(best) -> $OUT_DIR/audio_pretrained_embedding_multitask_best.pt"
echo "[OK] plc_encoder(last) -> $OUT_DIR/audio_pretrained_embedding_plc_encoder.pt"
echo "[OK] plc_encoder(best) -> $OUT_DIR/audio_pretrained_embedding_plc_encoder_best.pt"
echo "[OK] metrics -> $OUT_DIR/audio_pretrained_embedding_multitask_metrics.json"
