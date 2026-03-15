#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

INPUT_PARQUET="${INPUT_PARQUET:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_actuation_embedding_pca_combo.parquet}"
OUT_DIR="${OUT_DIR:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_actuation_embedding_pca_panels}"
PROJECTION="${PROJECTION:-3d}"
COMBO_COL="${COMBO_COL:-actuation_bits}"
COMBO_TOP_K="${COMBO_TOP_K:-0}"
DROP_UNKNOWN="${DROP_UNKNOWN:-yes}"
QUANTILE_LIMITS="${QUANTILE_LIMITS:-1,99}"
POINT_SIZE="${POINT_SIZE:-10}"
ALPHA="${ALPHA:-0.6}"
TITLE_PREFIX="${TITLE_PREFIX:-Bluerock PANN Embedding PCA}"

cd "$REPO"

"$PYTHON" python/analytics/plot_actuation_embedding_pca_panels.py \
  --input-parquet "$INPUT_PARQUET" \
  --out-dir "$OUT_DIR" \
  --projection "$PROJECTION" \
  --combo-col "$COMBO_COL" \
  --combo-top-k "$COMBO_TOP_K" \
  --drop-unknown "$DROP_UNKNOWN" \
  --quantile-limits "$QUANTILE_LIMITS" \
  --point-size "$POINT_SIZE" \
  --alpha "$ALPHA" \
  --title-prefix "$TITLE_PREFIX"
