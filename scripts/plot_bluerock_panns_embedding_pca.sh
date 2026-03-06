#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

DATASET="${DATASET:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/samples.parquet}"
SPLIT="${SPLIT:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/split_manifest.parquet}"
EMBEDDINGS_NPZ="${EMBEDDINGS_NPZ:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_panns_embedding_experiment/embeddings_panns.npz}"

OUT_PNG="${OUT_PNG:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_panns_embedding_pca_primary_class.png}"
OUT_PARQUET="${OUT_PARQUET:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_panns_embedding_pca_primary_class.parquet}"
OUT_META="${OUT_META:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_panns_embedding_pca_primary_class.json}"

COLOR_COL="${COLOR_COL:-primary_class}"
SPLIT_FILTER="${SPLIT_FILTER:-}"
SOURCE_FILTER="${SOURCE_FILTER:-}"
LIMIT="${LIMIT:-12000}"
TITLE="${TITLE:-PANN Embedding PCA (bluerock 10s)}"

cd "$REPO"

args=(
  -m python.ml.cli.audio_embedding_pca_plot
  --dataset "$DATASET"
  --split-manifest "$SPLIT"
  --embeddings-npz "$EMBEDDINGS_NPZ"
  --out-png "$OUT_PNG"
  --out-parquet "$OUT_PARQUET"
  --out-meta "$OUT_META"
  --color-col "$COLOR_COL"
  --limit "$LIMIT"
  --title "$TITLE"
)

if [[ -n "$SPLIT_FILTER" ]]; then
  args+=(--split "$SPLIT_FILTER")
fi
if [[ -n "$SOURCE_FILTER" ]]; then
  args+=(--source "$SOURCE_FILTER")
fi

"$PYTHON" "${args[@]}"

echo "[OK] plot -> $OUT_PNG"
