#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-/home/cbaguilar/miniforge3/envs/rapids-cu13/bin/python}"
REPO="${REPO:-/home/cbaguilar/svwatergo}"

DATASET="${DATASET:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/samples.parquet}"
SPLIT="${SPLIT:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/split_manifest.parquet}"

# Binary ropumprun proxy from dataset builder output.
TARGET_COL="${TARGET_COL:-overlap_s_producing}"
SPLIT_STRATIFY_COL="${SPLIT_STRATIFY_COL:-}"
OVERSAMPLE_CLASS_COL="${OVERSAMPLE_CLASS_COL:-primary_class}"
OVERSAMPLE_CLASSES="${OVERSAMPLE_CLASSES:-}"
OVERSAMPLE_MULTIPLIER="${OVERSAMPLE_MULTIPLIER:-1}"

OUT_DIR="${OUT_DIR:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_tiny_cnn_ropumprun}"
PLOT_PNG="${PLOT_PNG:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_tiny_cnn_ropumprun_4panel.png}"
PLOT_META="${PLOT_META:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_tiny_cnn_ropumprun_4panel.json}"
INFER_JSON="${INFER_JSON:-/mnt/d/datasets/svwatergo/derived/inference/bluerock_10s_tiny_cnn_ropumprun_infer_sample.json}"

EPOCHS="${EPOCHS:-12}"
BATCH_SIZE="${BATCH_SIZE:-64}"
LEARNING_RATE="${LEARNING_RATE:-1e-3}"
WEIGHT_DECAY="${WEIGHT_DECAY:-1e-4}"

cd "$REPO"
mkdir -p "$(dirname "$PLOT_PNG")" "$(dirname "$PLOT_META")" "$(dirname "$INFER_JSON")" "$OUT_DIR"

extra_args=()
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

"$PYTHON" -m python.ml.cli.audio_tiny_cnn_train \
  --dataset "$DATASET" \
  --split-manifest "$SPLIT" \
  --dataset-id-col sample_id \
  --split-id-col sample_id \
  --split-col split \
  --out-dir "$OUT_DIR" \
  --task binary \
  --target-col "$TARGET_COL" \
  --epochs "$EPOCHS" \
  --batch-size "$BATCH_SIZE" \
  --learning-rate "$LEARNING_RATE" \
  --weight-decay "$WEIGHT_DECAY" \
  --class-weight balanced \
  --sample-rate 16000 \
  --target-seconds 10 \
  "${extra_args[@]}"

"$PYTHON" -m python.ml.cli.audio_pca_svm_plot \
  --checkpoint-dir "$OUT_DIR" \
  --out-png "$PLOT_PNG" \
  --out-meta "$PLOT_META" \
  --title "Audio Tiny CNN (bluerock 10s, ${TARGET_COL})"

SAMPLE_WAV=$("$PYTHON" -c "import pandas as pd; df=pd.read_parquet('$DATASET', columns=['segment_path','split']); s=df[df['split'].astype(str)=='test']['segment_path']; print(s.iloc[0] if len(s) else df['segment_path'].iloc[0])")

"$PYTHON" -m python.ml.cli.audio_pca_svm_infer \
  --model "$OUT_DIR/audio_tiny_cnn_model.pt" \
  --wav "$SAMPLE_WAV" > "$INFER_JSON"

echo "[OK] model -> $OUT_DIR/audio_tiny_cnn_model.pt"
echo "[OK] plot  -> $PLOT_PNG"
echo "[OK] infer -> $INFER_JSON"
