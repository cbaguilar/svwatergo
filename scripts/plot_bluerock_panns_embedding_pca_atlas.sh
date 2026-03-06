#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

DATASET="${DATASET:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/samples.parquet}"
SPLIT="${SPLIT:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/split_manifest.parquet}"
EMBEDDINGS_NPZ="${EMBEDDINGS_NPZ:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_panns_embedding_experiment/embeddings_panns.npz}"

OUT_PNG="${OUT_PNG:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_panns_embedding_pca_BIGASS_atlas.png}"
OUT_META="${OUT_META:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_panns_embedding_pca_BIGASS_atlas.json}"

SPLIT_FILTER="${SPLIT_FILTER:-}"
SOURCE_FILTER="${SOURCE_FILTER:-}"
LIMIT="${LIMIT:-30000}"
MAX_COLS="${MAX_COLS:-96}"
TITLE="${TITLE:-PANN Embedding PCA BIG Atlas (primary class + duty + mean + derivative)}"

cd "$REPO"

args=(
  -m python.ml.cli.audio_embedding_pca_atlas
  --dataset "$DATASET"
  --split-manifest "$SPLIT"
  --embeddings-npz "$EMBEDDINGS_NPZ"
  --out-png "$OUT_PNG"
  --out-meta "$OUT_META"
  --limit "$LIMIT"
  --max-cols "$MAX_COLS"
  --title "$TITLE"
)

if [[ -n "$SPLIT_FILTER" ]]; then
  args+=(--split "$SPLIT_FILTER")
fi
if [[ -n "$SOURCE_FILTER" ]]; then
  args+=(--source "$SOURCE_FILTER")
fi

"$PYTHON" "${args[@]}"

echo "[OK] atlas -> $OUT_PNG"
