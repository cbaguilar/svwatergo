#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

DATASET="${DATASET:-/mnt/d/datasets/svwatergo/derived/dataset=audio_actuation_dataset/site=bluerock/window_s=10/embeddings_joined.parquet}"
SPLIT_FILTER="${SPLIT_FILTER:-}"
DROP_UNKNOWN="${DROP_UNKNOWN:-yes}"
CV_FOLDS="${CV_FOLDS:-5}"
MAX_ITER="${MAX_ITER:-2000}"
RANDOM_STATE="${RANDOM_STATE:-42}"

OUT_CSV="${OUT_CSV:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_actuation_embedding_cmi.csv}"
OUT_JSON="${OUT_JSON:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_actuation_embedding_cmi.json}"

cd "$REPO"

args=(
  python/analytics/actuation_embedding_cmi.py
  --dataset "$DATASET"
  --drop-unknown "$DROP_UNKNOWN"
  --cv-folds "$CV_FOLDS"
  --max-iter "$MAX_ITER"
  --random-state "$RANDOM_STATE"
  --out-csv "$OUT_CSV"
  --out-json "$OUT_JSON"
)

if [[ -n "$SPLIT_FILTER" ]]; then
  args+=(--split "$SPLIT_FILTER")
fi

"$PYTHON" "${args[@]}"

echo "[OK] scores -> $OUT_CSV"
