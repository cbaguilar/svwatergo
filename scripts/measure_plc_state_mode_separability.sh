#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

INPUT="${INPUT:-}"
LABEL_COL="${LABEL_COL:-}"
FEATURE_SET="${FEATURE_SET:-auto}"
FEATURE_COLS="${FEATURE_COLS:-}"
SPLIT_COL="${SPLIT_COL:-split}"
SPLIT_VALUES="${SPLIT_VALUES:-}"
DROP_LABELS="${DROP_LABELS:-unknown,<NA>,nan,None}"
MIN_CLASS_ROWS="${MIN_CLASS_ROWS:-5}"
MAX_ROWS="${MAX_ROWS:-50000}"
SAMPLE_SEED="${SAMPLE_SEED:-42}"
CV_FOLDS="${CV_FOLDS:-5}"
OUT_JSON="${OUT_JSON:-}"

if [[ -z "$INPUT" ]]; then
  echo "INPUT is required" >&2
  exit 2
fi

cd "$REPO"

args=(
  python/analytics/plc_label_separability.py
  --input "$INPUT"
  --feature-set "$FEATURE_SET"
  --split-col "$SPLIT_COL"
  --drop-labels "$DROP_LABELS"
  --min-class-rows "$MIN_CLASS_ROWS"
  --max-rows "$MAX_ROWS"
  --sample-seed "$SAMPLE_SEED"
  --cv-folds "$CV_FOLDS"
)

if [[ -n "$LABEL_COL" ]]; then
  args+=(--label-col "$LABEL_COL")
fi
if [[ -n "$FEATURE_COLS" ]]; then
  args+=(--feature-cols "$FEATURE_COLS")
fi
if [[ -n "$SPLIT_VALUES" ]]; then
  args+=(--split-values "$SPLIT_VALUES")
fi
if [[ -n "$OUT_JSON" ]]; then
  args+=(--out-json "$OUT_JSON")
fi

"$PYTHON" "${args[@]}"
