#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

MATRIX_ROOT="${1:-${MATRIX_ROOT:-}}"
if [[ -z "$MATRIX_ROOT" ]]; then
  echo "usage: $0 /path/to/domain_matrix/run_dir" >&2
  echo "   or: MATRIX_ROOT=/path/to/domain_matrix/run_dir $0" >&2
  exit 2
fi

SUMMARY_CSV="${SUMMARY_CSV:-$MATRIX_ROOT/site_matrix_summary.csv}"
OUT_DIR="${OUT_DIR:-$MATRIX_ROOT/latex}"
METRICS="${METRICS:-mae_mean,rmse_mean,mse_mean,r2_mean}"
LABEL_MAP="${LABEL_MAP:-bluerock=Site A,pryorfarm=Site C,santateresa=Site B,all_sites=Pooled Train}"
CAPTION_PREFIX="${CAPTION_PREFIX:-$(basename "$MATRIX_ROOT")}"
LABEL_PREFIX="${LABEL_PREFIX:-$(basename "$MATRIX_ROOT")}"
PRECISION="${PRECISION:-3}"
TABLE_ENV="${TABLE_ENV:-table*}"
SIZE_CMD="${SIZE_CMD:-\\small}"

cd "$REPO"
"$PYTHON" python/analytics/generate_domain_matrix_latex.py \
  --csv "$SUMMARY_CSV" \
  --out-dir "$OUT_DIR" \
  --metrics "$METRICS" \
  --label-map "$LABEL_MAP" \
  --caption-prefix "$CAPTION_PREFIX" \
  --label-prefix "$LABEL_PREFIX" \
  --precision "$PRECISION" \
  --table-env "$TABLE_ENV" \
  --size-cmd "$SIZE_CMD"

echo "[OK] latex -> $OUT_DIR"
