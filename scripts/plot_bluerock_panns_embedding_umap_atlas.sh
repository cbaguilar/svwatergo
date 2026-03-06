#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

DATASET="${DATASET:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/samples.parquet}"
SPLIT="${SPLIT:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/split_manifest.parquet}"
EMBEDDINGS_NPZ="${EMBEDDINGS_NPZ:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_panns_embedding_experiment/embeddings_panns.npz}"
EMBEDDINGS_KEY="${EMBEDDINGS_KEY:-embeddings}"

UMAP_INPUT_PARQUET="${UMAP_INPUT_PARQUET:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_panns_embedding_experiment/embeddings_for_umap.parquet}"
REBUILD_INPUT="${REBUILD_INPUT:-no}"

LABEL_COL="${LABEL_COL:-ropumprun_duty}"
PRED_COL="${PRED_COL:-}"
SCORE_COL="${SCORE_COL:-score_positive}"
POSITIVE_THRESHOLD="${POSITIVE_THRESHOLD:-0.5}"

UMAP_BACKEND="${UMAP_BACKEND:-cpu}"
UMAP_N_NEIGHBORS="${UMAP_N_NEIGHBORS:-20}"
UMAP_MIN_DIST="${UMAP_MIN_DIST:-0.1}"
UMAP_METRIC="${UMAP_METRIC:-cosine}"
UMAP_MAX_FIT_POINTS="${UMAP_MAX_FIT_POINTS:-0}"

OUT_DIR="${OUT_DIR:-/mnt/d/datasets/svwatergo/derived/plots}"
PREFIX="${PREFIX:-bluerock_frozen_pann_umap_atlas}"
TITLE="${TITLE:-Bluerock Frozen PANN UMAP Atlas}"

FEATURE_ATLAS="${FEATURE_ATLAS:-yes}"
FEATURE_MAX_COLS="${FEATURE_MAX_COLS:-96}"
MAX_POINTS_PLOT="${MAX_POINTS_PLOT:-12000}"
FEATURE_PAIR="${FEATURE_PAIR:-1:2}"

cd "$REPO"

if [[ "$REBUILD_INPUT" == "yes" || ! -f "$UMAP_INPUT_PARQUET" ]]; then
  "$PYTHON" - "$DATASET" "$SPLIT" "$EMBEDDINGS_NPZ" "$EMBEDDINGS_KEY" "$UMAP_INPUT_PARQUET" <<'PY'
import numpy as np
import pandas as pd
from pathlib import Path
import sys

if len(sys.argv) != 6:
    raise SystemExit(f"expected 5 args, got {len(sys.argv)-1}")
samples = Path(sys.argv[1])
split = Path(sys.argv[2])
npz = Path(sys.argv[3])
emb_key = str(sys.argv[4] or "embeddings")
out = Path(sys.argv[5])

if not samples.exists():
    raise SystemExit(f"dataset not found: {samples}")
if not split.exists():
    raise SystemExit(f"split manifest not found: {split}")
if not npz.exists():
    raise SystemExit(f"embeddings npz not found: {npz}")

df = pd.read_parquet(samples)
sm = pd.read_parquet(split)
if "sample_id" in df.columns and "sample_id" in sm.columns and "split" in sm.columns:
    keep = sm[["sample_id", "split"]].drop_duplicates(subset=["sample_id"], keep="last")
    df = df.merge(keep, on="sample_id", how="left")

z = np.load(npz)
if emb_key not in z.files:
    raise SystemExit(f"embedding key not found: {emb_key}; available={list(z.files)}")
emb = np.asarray(z[emb_key], dtype=np.float32)
if emb.ndim != 2:
    emb = emb.reshape(emb.shape[0], -1)

if len(df) != emb.shape[0]:
    raise SystemExit(f"row mismatch: dataset={len(df)} embeddings={emb.shape[0]}")

for j in range(emb.shape[1]):
    df[f"embedding_{j:04d}"] = emb[:, j].astype("float32")

out.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(out, index=False)
print(f"[OK] wrote {out} rows={len(df)} dim={emb.shape[1]}")
PY
fi

args=(
  -m python.analytics.pann_umap_atlas_pipeline
  --input-parquet "$UMAP_INPUT_PARQUET"
  --embedding-col-regex '^embedding_[0-9]+$'
  --label-col "$LABEL_COL"
  --positive-threshold "$POSITIVE_THRESHOLD"
  --umap-backend "$UMAP_BACKEND"
  --umap-n-neighbors "$UMAP_N_NEIGHBORS"
  --umap-min-dist "$UMAP_MIN_DIST"
  --umap-metric "$UMAP_METRIC"
  --umap-max-fit-points "$UMAP_MAX_FIT_POINTS"
  --feature-atlas "$FEATURE_ATLAS"
  --feature-max-cols "$FEATURE_MAX_COLS"
  --max-points-plot "$MAX_POINTS_PLOT"
  --feature-pair "$FEATURE_PAIR"
  --out-dir "$OUT_DIR"
  --prefix "$PREFIX"
  --title "$TITLE"
)

if [[ -n "$PRED_COL" ]]; then
  args+=(--pred-col "$PRED_COL")
fi
if [[ -n "$SCORE_COL" ]]; then
  args+=(--score-col "$SCORE_COL")
fi

"$PYTHON" "${args[@]}"

echo "[OK] atlas -> $OUT_DIR/${PREFIX}_atlas.png"
