#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-/home/cbaguilar/miniforge3/envs/rapids-cu13/bin/python}"
REPO="${REPO:-/home/cbaguilar/svwatergo}"

DATASET="${DATASET:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/samples.parquet}"
SPLIT="${SPLIT:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/split_manifest.parquet}"

# Binary ropumprun proxy from dataset builder output.
TARGET_COL="${TARGET_COL:-overlap_s_producing}"

OUT_DIR="${OUT_DIR:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_svm_ropumprun}"
PLOT_PNG="${PLOT_PNG:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_svm_ropumprun_4panel.png}"
PLOT_META="${PLOT_META:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_svm_ropumprun_4panel.json}"
INFER_JSON="${INFER_JSON:-/mnt/d/datasets/svwatergo/derived/inference/bluerock_10s_svm_ropumprun_infer_sample.json}"

cd "$REPO"
mkdir -p "$(dirname "$PLOT_PNG")" "$(dirname "$PLOT_META")" "$(dirname "$INFER_JSON")" "$OUT_DIR"

"$PYTHON" -m python.ml.cli.audio_pca_svm_train \
  --dataset "$DATASET" \
  --split-manifest "$SPLIT" \
  --dataset-id-col sample_id \
  --split-id-col sample_id \
  --split-col split \
  --out-dir "$OUT_DIR" \
  --task binary \
  --target-col "$TARGET_COL" \
  --n-components 8 \
  --svm-class-weight balanced \
  --sample-rate 16000 \
  --target-seconds 10

"$PYTHON" -m python.ml.cli.audio_pca_svm_plot \
  --checkpoint-dir "$OUT_DIR" \
  --out-png "$PLOT_PNG" \
  --out-meta "$PLOT_META" \
  --title "Audio PCA+SVM (bluerock 10s, ${TARGET_COL})"

SAMPLE_WAV=$("$PYTHON" -c "import pandas as pd; df=pd.read_parquet('$DATASET', columns=['segment_path','split']); s=df[df['split'].astype(str)=='test']['segment_path']; print(s.iloc[0] if len(s) else df['segment_path'].iloc[0])")

"$PYTHON" -m python.ml.cli.audio_pca_svm_infer \
  --model "$OUT_DIR/audio_pca_svm_model.joblib" \
  --model-kind pca_svm \
  --wav "$SAMPLE_WAV" > "$INFER_JSON"

echo "[OK] model -> $OUT_DIR/audio_pca_svm_model.joblib"
echo "[OK] plot  -> $PLOT_PNG"
echo "[OK] infer -> $INFER_JSON"
