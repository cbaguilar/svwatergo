#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-/home/cbaguilar/miniforge3/envs/rapids-cu13/bin/python}"
REPO="${REPO:-/home/cbaguilar/svwatergo}"

DATASET="${DATASET:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/samples.parquet}"
SPLIT="${SPLIT:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/split_manifest.parquet}"

TARGET_COLS="${TARGET_COLS:-ropumprun_duty,deliveryrun_duty}"
POSITIVE_THRESHOLD="${POSITIVE_THRESHOLD:-0.5}"
TASK="${TASK:-multiregression}"
TARGET_COL="${TARGET_COL:-primary_class}"
MEL_NORMALIZATION="${MEL_NORMALIZATION:-log_db}"
CMVN="${CMVN:-yes}"
SPLIT_STRATIFY_COL="${SPLIT_STRATIFY_COL:-}"
OVERSAMPLE_CLASS_COL="${OVERSAMPLE_CLASS_COL:-primary_class}"
OVERSAMPLE_CLASSES="${OVERSAMPLE_CLASSES:-}"
OVERSAMPLE_MULTIPLIER="${OVERSAMPLE_MULTIPLIER:-1}"

OUT_DIR="${OUT_DIR:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_resnet_multilabel_ro_delivery}"
PLOT_PNG="${PLOT_PNG:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_resnet_multilabel_ro_delivery_5panel.png}"
PLOT_META="${PLOT_META:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_resnet_multilabel_ro_delivery_5panel.json}"

EPOCHS="${EPOCHS:-30}"
BATCH_SIZE="${BATCH_SIZE:-64}"
LEARNING_RATE="${LEARNING_RATE:-5e-4}"
WEIGHT_DECAY="${WEIGHT_DECAY:-1e-4}"
LR_DROP_EPOCHS="${LR_DROP_EPOCHS:-10,15}"
LR_DROP_GAMMA="${LR_DROP_GAMMA:-0.5}"
LR_PLATEAU="${LR_PLATEAU:-yes}"
LR_PLATEAU_FACTOR="${LR_PLATEAU_FACTOR:-0.5}"
LR_PLATEAU_PATIENCE="${LR_PLATEAU_PATIENCE:-2}"

cd "$REPO"
mkdir -p "$(dirname "$PLOT_PNG")" "$(dirname "$PLOT_META")" "$OUT_DIR"

extra_args=()
if [[ "$CMVN" == "yes" ]]; then
  extra_args+=(--cmvn)
fi
if [[ -n "$SPLIT_STRATIFY_COL" ]]; then
  extra_args+=(--split-stratify-col "$SPLIT_STRATIFY_COL")
fi
if [[ -n "$OVERSAMPLE_CLASS_COL" ]]; then
  extra_args+=(--oversample-class-col "$OVERSAMPLE_CLASS_COL")
fi
if [[ -n "$OVERSAMPLE_CLASSES" ]]; then
  extra_args+=(--oversample-classes "$OVERSAMPLE_CLASSES")
fi
if [[ -n "$OVERSAMPLE_MULTIPLIER" ]]; then
  extra_args+=(--oversample-multiplier "$OVERSAMPLE_MULTIPLIER")
fi
if [[ "$TASK" == "multiclass" || "$TASK" == "binary" ]]; then
  extra_args+=(--target-col "$TARGET_COL")
fi

"$PYTHON" -m python.ml.cli.audio_tiny_cnn_train \
  --dataset "$DATASET" \
  --split-manifest "$SPLIT" \
  --dataset-id-col sample_id \
  --split-id-col sample_id \
  --split-col split \
  --out-dir "$OUT_DIR" \
  --model-arch resnet_small \
  --task "$TASK" \
  --target-cols "$TARGET_COLS" \
  --positive-threshold "$POSITIVE_THRESHOLD" \
  --epochs "$EPOCHS" \
  --batch-size "$BATCH_SIZE" \
  --learning-rate "$LEARNING_RATE" \
  --weight-decay "$WEIGHT_DECAY" \
  --lr-drop-epochs "$LR_DROP_EPOCHS" \
  --lr-drop-gamma "$LR_DROP_GAMMA" \
  --lr-plateau "$LR_PLATEAU" \
  --lr-plateau-factor "$LR_PLATEAU_FACTOR" \
  --lr-plateau-patience "$LR_PLATEAU_PATIENCE" \
  --class-weight balanced \
  --generate-projection yes \
  --sample-rate 16000 \
  --target-seconds 10 \
  --mel-normalization "$MEL_NORMALIZATION" \
  "${extra_args[@]}"

"$PYTHON" -m python.ml.cli.audio_pca_svm_plot \
  --checkpoint-dir "$OUT_DIR" \
  --use-tuned-thresholds yes \
  --out-png "$PLOT_PNG" \
  --out-meta "$PLOT_META" \
  --title "Audio ResNet ${TASK} (bluerock 10s, ro+delivery)"

echo "[OK] model -> $OUT_DIR/audio_tiny_cnn_model.pt"
echo "[OK] plot  -> $PLOT_PNG"
