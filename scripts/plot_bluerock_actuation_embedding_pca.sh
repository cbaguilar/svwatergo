#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

DATASET="${DATASET:-/mnt/d/datasets/svwatergo/derived/dataset=audio_actuation_dataset/site=bluerock/window_s=10/samples.parquet}"
SPLIT="${SPLIT:-/mnt/d/datasets/svwatergo/derived/dataset=audio_actuation_dataset/site=bluerock/window_s=10/split_manifest.parquet}"
EMBEDDINGS_NPZ="${EMBEDDINGS_NPZ:-/mnt/d/datasets/svwatergo/derived/dataset=audio_actuation_dataset/site=bluerock/window_s=10/embeddings_panns.npz}"

OUT_PARQUET="${OUT_PARQUET:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_actuation_embedding_pca_combo.parquet}"
OUT_META="${OUT_META:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_actuation_embedding_pca_combo.json}"

N_COMPONENTS="${N_COMPONENTS:-3}"
SPLIT_FILTER="${SPLIT_FILTER:-}"
SOURCE_FILTER="${SOURCE_FILTER:-}"
LIMIT="${LIMIT:-12000}"

cd "$REPO"

args=(
  python/analytics/build_actuation_embedding_pca.py
  --dataset "$DATASET"
  --split-manifest "$SPLIT"
  --embeddings-npz "$EMBEDDINGS_NPZ"
  --out-parquet "$OUT_PARQUET"
  --out-meta "$OUT_META"
  --limit "$LIMIT"
  --n-components "$N_COMPONENTS"
)

if [[ -n "$SPLIT_FILTER" ]]; then
  args+=(--split "$SPLIT_FILTER")
fi
if [[ -n "$SOURCE_FILTER" ]]; then
  args+=(--source "$SOURCE_FILTER")
fi

"$PYTHON" "${args[@]}"

echo "[OK] points -> $OUT_PARQUET"
