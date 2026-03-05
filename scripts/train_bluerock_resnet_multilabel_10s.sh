#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-/home/cbaguilar/miniforge3/envs/rapids-cu13/bin/python}"
REPO="${REPO:-/home/cbaguilar/svwatergo}"

DATASET="${DATASET:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/samples.parquet}"
SPLIT="${SPLIT:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/split_manifest.parquet}"

TARGET_COLS="${TARGET_COLS:-ropumprun_duty,deliveryrun_duty}"
POSITIVE_THRESHOLD="${POSITIVE_THRESHOLD:-0.5}"
MEL_NORMALIZATION="${MEL_NORMALIZATION:-log_db}"

OUT_DIR="${OUT_DIR:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_resnet_multilabel_ro_delivery}"
PLOT_PNG="${PLOT_PNG:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_resnet_multilabel_ro_delivery_5panel.png}"
PLOT_META="${PLOT_META:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_resnet_multilabel_ro_delivery_5panel.json}"

EPOCHS="${EPOCHS:-30}"
BATCH_SIZE="${BATCH_SIZE:-64}"
LEARNING_RATE="${LEARNING_RATE:-5e-4}"
WEIGHT_DECAY="${WEIGHT_DECAY:-1e-4}"

cd "$REPO"
mkdir -p "$(dirname "$PLOT_PNG")" "$(dirname "$PLOT_META")" "$OUT_DIR"

"$PYTHON" -m python.ml.cli.audio_tiny_cnn_train \
  --dataset "$DATASET" \
  --split-manifest "$SPLIT" \
  --dataset-id-col sample_id \
  --split-id-col sample_id \
  --split-col split \
  --out-dir "$OUT_DIR" \
  --model-arch resnet_small \
  --task multilabel \
  --target-cols "$TARGET_COLS" \
  --positive-threshold "$POSITIVE_THRESHOLD" \
  --epochs "$EPOCHS" \
  --batch-size "$BATCH_SIZE" \
  --learning-rate "$LEARNING_RATE" \
  --weight-decay "$WEIGHT_DECAY" \
  --class-weight balanced \
  --sample-rate 16000 \
  --target-seconds 10 \
  --mel-normalization "$MEL_NORMALIZATION"

"$PYTHON" -m python.ml.cli.audio_pca_svm_plot \
  --checkpoint-dir "$OUT_DIR" \
  --use-tuned-thresholds yes \
  --out-png "$PLOT_PNG" \
  --out-meta "$PLOT_META" \
  --title "Audio ResNet Multilabel (bluerock 10s, ro+delivery)"

echo "[OK] model -> $OUT_DIR/audio_tiny_cnn_model.pt"
echo "[OK] plot  -> $PLOT_PNG"
