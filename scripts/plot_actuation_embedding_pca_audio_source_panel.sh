#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

INPUT_PARQUET="${INPUT_PARQUET:-}"
OUT_DIR="${OUT_DIR:-}"
TITLE_PREFIX="${TITLE_PREFIX:-Actuation Embedding PCA}"

PROJECTION="${PROJECTION:-3d}"
COMBO_COL="${COMBO_COL:-actuation_bits}"
COMBO_TOP_K="${COMBO_TOP_K:-0}"
DROP_UNKNOWN="${DROP_UNKNOWN:-yes}"
QUANTILE_LIMITS="${QUANTILE_LIMITS:-1,99}"
POINT_SIZE="${POINT_SIZE:-10}"
ALPHA="${ALPHA:-0.6}"
AUDIO_SOURCE_COL="${AUDIO_SOURCE_COL:-audio_source}"
AUDIO_SOURCE_OUTNAME="${AUDIO_SOURCE_OUTNAME:-audio_source.png}"
ACTUATORS="${ACTUATORS:-ropumprun,wellpumprun,feedpumprun,deliveryrun,flushrun}"

if [[ -z "$INPUT_PARQUET" ]]; then
  echo "INPUT_PARQUET is required" >&2
  exit 2
fi
if [[ -z "$OUT_DIR" ]]; then
  echo "OUT_DIR is required" >&2
  exit 2
fi

cd "$REPO"

"$PYTHON" python/analytics/plot_actuation_embedding_pca_panels.py \
  --input-parquet "$INPUT_PARQUET" \
  --out-dir "$OUT_DIR" \
  --projection "$PROJECTION" \
  --combo-col "$COMBO_COL" \
  --actuators "$ACTUATORS" \
  --combo-top-k "$COMBO_TOP_K" \
  --drop-unknown "$DROP_UNKNOWN" \
  --quantile-limits "$QUANTILE_LIMITS" \
  --point-size "$POINT_SIZE" \
  --alpha "$ALPHA" \
  --title-prefix "$TITLE_PREFIX" \
  --extra-categorical-col "$AUDIO_SOURCE_COL" \
  --extra-categorical-outname "$AUDIO_SOURCE_OUTNAME"

echo "[OK] wrote $OUT_DIR/$AUDIO_SOURCE_OUTNAME"
