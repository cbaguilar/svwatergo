#!/usr/bin/env bash
set -euo pipefail

# Convenience wrapper: run per-source training with resnet_small architecture
# and dedicated output folders so results do not overwrite tiny-cnn runs.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_SCRIPT="${SCRIPT_DIR}/train_bluerock_tiny_cnn_per_source_10s.sh"

if [[ ! -f "$BASE_SCRIPT" ]]; then
  echo "[FATAL] missing base script: $BASE_SCRIPT"
  exit 1
fi

MODEL_ARCH="${MODEL_ARCH:-resnet_small}" \
OUT_ROOT="${OUT_ROOT:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_per_source_resnet}" \
PLOT_ROOT="${PLOT_ROOT:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_per_source_resnet}" \
SUMMARY_JSON="${SUMMARY_JSON:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_per_source_resnet_summary.json}" \
TMP_ROOT="${TMP_ROOT:-/mnt/d/datasets/svwatergo/derived/tmp/per_source_bluerock_10s_resnet}" \
bash "$BASE_SCRIPT"

