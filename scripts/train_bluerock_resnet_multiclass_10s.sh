#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-/home/cbaguilar/miniforge3/envs/rapids-cu13/bin/python}"
REPO="${REPO:-/home/cbaguilar/svwatergo}"

DATASET="${DATASET:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/samples.parquet}"
SPLIT="${SPLIT:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/split_manifest.parquet}"

# Explicit 4-class target from dataset builder:
#   not_producing|not_delivering
#   not_producing|delivering
#   producing|not_delivering
#   producing|delivering
TARGET_COL="${TARGET_COL:-primary_class}"
TASK="${TASK:-multiclass}"
MEL_NORMALIZATION="${MEL_NORMALIZATION:-log_db}"
CMVN="${CMVN:-yes}"

# Optional train-only oversampling knobs.
OVERSAMPLE_CLASS_COL="${OVERSAMPLE_CLASS_COL:-primary_class}"
OVERSAMPLE_CLASSES="${OVERSAMPLE_CLASSES:-not_producing|delivering,producing|delivering}"
OVERSAMPLE_MULTIPLIER="${OVERSAMPLE_MULTIPLIER:-1}"
CLASS_WEIGHT="${CLASS_WEIGHT:-auto}"  # auto|balanced|none

# Optional auxiliary PCA head settings.
AUX_TARGET_PCA="${AUX_TARGET_PCA:-no}"
AUX_PCA_FEATURE_SOURCE="${AUX_PCA_FEATURE_SOURCE:-window_cols}"
AUX_PCA_FEATURE_COLS="${AUX_PCA_FEATURE_COLS:-}"
AUX_PCA_COMPONENTS="${AUX_PCA_COMPONENTS:-8}"
AUX_PCA_VARIANCE_RATIO="${AUX_PCA_VARIANCE_RATIO:-0.0}"
AUX_PCA_WEIGHT="${AUX_PCA_WEIGHT:-0.1}"

OUT_DIR="${OUT_DIR:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_resnet_multiclass_primary_class}"
PLOT_PNG="${PLOT_PNG:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_resnet_multiclass_primary_class_5panel.png}"
PLOT_META="${PLOT_META:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_resnet_multiclass_primary_class_5panel.json}"
CURVE_PNG="${CURVE_PNG:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_resnet_multiclass_primary_class_training_curves.png}"
CURVE_META="${CURVE_META:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_resnet_multiclass_primary_class_training_curves.json}"

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
mkdir -p "$(dirname "$PLOT_PNG")" "$(dirname "$PLOT_META")" "$(dirname "$CURVE_PNG")" "$(dirname "$CURVE_META")" "$OUT_DIR"

extra_args=()
if [[ "$CMVN" == "yes" ]]; then
  extra_args+=(--cmvn)
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
if [[ "$AUX_TARGET_PCA" == "yes" ]]; then
  extra_args+=(--aux-target-pca yes)
  extra_args+=(--aux-pca-feature-source "$AUX_PCA_FEATURE_SOURCE")
  extra_args+=(--aux-pca-components "$AUX_PCA_COMPONENTS")
  extra_args+=(--aux-pca-variance-ratio "$AUX_PCA_VARIANCE_RATIO")
  extra_args+=(--aux-pca-weight "$AUX_PCA_WEIGHT")
  if [[ -n "$AUX_PCA_FEATURE_COLS" ]]; then
    extra_args+=(--aux-pca-feature-cols "$AUX_PCA_FEATURE_COLS")
  fi
fi

class_weight_args=()
if [[ "$CLASS_WEIGHT" == "balanced" ]]; then
  class_weight_args+=(--class-weight balanced)
elif [[ "$CLASS_WEIGHT" == "auto" ]]; then
  if [[ -n "$OVERSAMPLE_CLASSES" && "${OVERSAMPLE_MULTIPLIER:-1}" -gt 1 ]]; then
    class_weight_args=()
  else
    class_weight_args+=(--class-weight balanced)
  fi
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
  --target-col "$TARGET_COL" \
  --epochs "$EPOCHS" \
  --batch-size "$BATCH_SIZE" \
  --learning-rate "$LEARNING_RATE" \
  --weight-decay "$WEIGHT_DECAY" \
  --lr-drop-epochs "$LR_DROP_EPOCHS" \
  --lr-drop-gamma "$LR_DROP_GAMMA" \
  --lr-plateau "$LR_PLATEAU" \
  --lr-plateau-factor "$LR_PLATEAU_FACTOR" \
  --lr-plateau-patience "$LR_PLATEAU_PATIENCE" \
  --generate-projection yes \
  --sample-rate 16000 \
  --target-seconds 10 \
  --mel-normalization "$MEL_NORMALIZATION" \
  "${class_weight_args[@]}" \
  "${extra_args[@]}"

"$PYTHON" -m python.ml.cli.audio_pca_svm_plot \
  --checkpoint-dir "$OUT_DIR" \
  --out-png "$PLOT_PNG" \
  --out-meta "$PLOT_META" \
  --title "Audio ResNet Multiclass (bluerock 10s, primary_class)"

"$PYTHON" -m python.ml.cli.audio_training_curves_plot \
  --checkpoint-dir "$OUT_DIR" \
  --out-png "$CURVE_PNG" \
  --out-meta "$CURVE_META" \
  --title "Audio ResNet Multiclass Training Curves (bluerock 10s, primary_class)"

echo "[OK] model -> $OUT_DIR/audio_tiny_cnn_model.pt"
echo "[OK] plot  -> $PLOT_PNG"
echo "[OK] curves -> $CURVE_PNG"
echo "[OK] metrics -> $OUT_DIR/audio_tiny_cnn_metrics.json"
