#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

INPUT_PARQUET="${INPUT_PARQUET:-}"
OUT_DIR="${OUT_DIR:-}"
TITLE_PREFIX="${TITLE_PREFIX:-Actuation PLC PCA}"
PROJECTION="${PROJECTION:-3d}"
COMBO_COL="${COMBO_COL:-actuation_bits}"
ACTUATORS="${ACTUATORS:-ropumprun,wellpumprun,feedpumprun,deliveryrun,flushrun}"
COMBO_TOP_K="${COMBO_TOP_K:-0}"
DROP_UNKNOWN="${DROP_UNKNOWN:-yes}"
QUANTILE_LIMITS="${QUANTILE_LIMITS:-1,99}"
POINT_SIZE="${POINT_SIZE:-10}"
ALPHA="${ALPHA:-0.6}"
X_COL="${X_COL:-plc_pca1}"
Y_COL="${Y_COL:-plc_pca2}"
Z_COL="${Z_COL:-plc_pca3}"
EXTRA_CATEGORICAL_COL="${EXTRA_CATEGORICAL_COL:-}"
EXTRA_CATEGORICAL_OUTNAME="${EXTRA_CATEGORICAL_OUTNAME:-}"

if [[ -z "$INPUT_PARQUET" ]]; then
  echo "INPUT_PARQUET is required" >&2
  exit 2
fi
if [[ -z "$OUT_DIR" ]]; then
  echo "OUT_DIR is required" >&2
  exit 2
fi

cd "$REPO"

args=(
  python/analytics/plot_actuation_embedding_pca_panels.py
  --input-parquet "$INPUT_PARQUET"
  --out-dir "$OUT_DIR"
  --x-col "$X_COL"
  --y-col "$Y_COL"
  --z-col "$Z_COL"
  --projection "$PROJECTION"
  --combo-col "$COMBO_COL"
  --actuators "$ACTUATORS"
  --combo-top-k "$COMBO_TOP_K"
  --drop-unknown "$DROP_UNKNOWN"
  --quantile-limits "$QUANTILE_LIMITS"
  --point-size "$POINT_SIZE"
  --alpha "$ALPHA"
  --title-prefix "$TITLE_PREFIX"
)

if [[ -n "$EXTRA_CATEGORICAL_COL" ]]; then
  args+=(--extra-categorical-col "$EXTRA_CATEGORICAL_COL")
fi
if [[ -n "$EXTRA_CATEGORICAL_OUTNAME" ]]; then
  args+=(--extra-categorical-outname "$EXTRA_CATEGORICAL_OUTNAME")
fi

"$PYTHON" "${args[@]}"
