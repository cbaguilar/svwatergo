#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python3}"
REPO="${REPO:-/home/cbaguilar/work/water/svwatergo}"
DATE="${DATE:-2026-03-01}"
TARGET_SECONDS="${TARGET_SECONDS:-10}"

cd "$REPO"

DATASET="data/derived/ropumprun_labeled_mels_camera_5_${DATE}_${TARGET_SECONDS}s.parquet"
WAV_ROOT="data/raw/camera_5_${DATE}_wav"

PCA_OUT="data/checkpoints/ropumprun_on_pca_svm_camera_5_${DATE}_${TARGET_SECONDS}s"
CNN_OUT="data/checkpoints/ropumprun_on_tiny_cnn_camera_5_${DATE}_${TARGET_SECONDS}s"
INFER_DIR="data/inference"

mkdir -p "$PCA_OUT" "$CNN_OUT" "$INFER_DIR"

if [[ ! -f "$DATASET" ]]; then
  echo "[FATAL] labeled dataset not found: $DATASET"
  exit 1
fi

SAMPLE_WAV="$(find "$WAV_ROOT" -type f -name '*.wav' | head -n 1 || true)"
if [[ -z "$SAMPLE_WAV" ]]; then
  echo "[FATAL] no sample wav found under $WAV_ROOT"
  exit 1
fi

echo "[RUN] camera_5 ropumprun baseline PCA+SVM"
"$PYTHON" -m python.ml.cli.audio_pca_svm_train \
  --dataset "$DATASET" \
  --out-dir "$PCA_OUT" \
  --task binary \
  --target-col ropumprun_label \
  --positive-label on \
  --n-components 8 \
  --svm-class-weight balanced \
  --sample-rate 16000 \
  --target-seconds "$TARGET_SECONDS"

echo "[RUN] inference (PCA+SVM) from new WAV"
"$PYTHON" -m python.ml.cli.audio_pca_svm_infer \
  --model "$PCA_OUT/audio_pca_svm_model.joblib" \
  --model-kind pca_svm \
  --wav "$SAMPLE_WAV" > "$INFER_DIR/camera_5_${DATE}_${TARGET_SECONDS}s_pca_infer.json"

if "$PYTHON" - <<'PY'
import sys
try:
    import torch  # noqa: F401
    sys.exit(0)
except Exception:
    sys.exit(1)
PY
then
  echo "[RUN] tiny CNN (ropumprun)"
  "$PYTHON" -m python.ml.cli.audio_tiny_cnn_train \
    --dataset "$DATASET" \
    --out-dir "$CNN_OUT" \
    --task binary \
    --target-col ropumprun_label \
    --positive-label on \
    --epochs 12 \
    --batch-size 64 \
    --learning-rate 0.001 \
    --weight-decay 0.0001 \
    --sample-rate 16000 \
    --target-seconds "$TARGET_SECONDS"

  echo "[RUN] 4-panel plot (tiny CNN)"
  "$PYTHON" -m python.ml.cli.audio_pca_svm_plot \
    --checkpoint-dir "$CNN_OUT" \
    --out-png "data/plots/camera_5_${DATE}_${TARGET_SECONDS}s_tiny_cnn_4panel.png" \
    --out-meta "data/plots/camera_5_${DATE}_${TARGET_SECONDS}s_tiny_cnn_4panel.json" \
    --title "Audio Tiny-CNN (camera_5, ${DATE}, ${TARGET_SECONDS}s)"

  echo "[RUN] inference (tiny CNN) from new WAV"
  "$PYTHON" -m python.ml.cli.audio_pca_svm_infer \
    --model "$CNN_OUT/audio_tiny_cnn_model.pt" \
    --model-kind tiny_cnn \
    --wav "$SAMPLE_WAV" > "$INFER_DIR/camera_5_${DATE}_${TARGET_SECONDS}s_tiny_cnn_infer.json"
else
  echo "[SKIP] torch import failed for $PYTHON; tiny CNN training skipped."
  echo "       If error mentions executable stack/libtorch_cpu.so, run:"
  echo "       execstack -c \$CONDA_PREFIX/lib/python*/site-packages/torch/lib/*.so"
fi

echo "[DONE] outputs:"
echo "  - $PCA_OUT"
echo "  - $CNN_OUT"
echo "  - $INFER_DIR"
