#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

SITE="${SITE:-bluerock}"
LOCAL_ROOT="${LOCAL_ROOT:-/mnt/d/datasets/svwatergo/derived}"
DATE_FROM="${DATE_FROM:-2025-12-01}"
DATE_TO="${DATE_TO:-2025-12-31}"
WINDOW_S="${WINDOW_S:-10}"
STRIDE_S="${STRIDE_S:-}"

OUT_DIR="${OUT_DIR:-/mnt/d/datasets/svwatergo/derived/plots/pca_noninteractive}"
OUT_PREFIX="${OUT_PREFIX:-${SITE}_${DATE_FROM}_to_${DATE_TO}}"

FIT_SAMPLE_PER_FILE="${FIT_SAMPLE_PER_FILE:-2000}"
FIT_MAX_SAMPLES="${FIT_MAX_SAMPLES:-2000000}"
BACKEND="${BACKEND:-auto}" # auto|cpu|gpu

RENDER_MODE="${RENDER_MODE:-both}" # none|heatmap|points|both
HIST_BINS_2D="${HIST_BINS_2D:-1200}"
HIST_BINS_3D="${HIST_BINS_3D:-160}"
MAX_RENDER_POINTS="${MAX_RENDER_POINTS:-2000000}"

OPEN3D_MAX_POINTS="${OPEN3D_MAX_POINTS:-3000000}"
OPEN3D_POINT_SIZE="${OPEN3D_POINT_SIZE:-1.0}"

cd "$REPO"

args=(
  -m python.analytics.window_pca.scalable_cli
  --local-root "$LOCAL_ROOT"
  --site "$SITE"
  --date-from "$DATE_FROM"
  --date-to "$DATE_TO"
  --window-s "$WINDOW_S"
  --n-components 3
  --controls-off
  --fit-sample-per-file "$FIT_SAMPLE_PER_FILE"
  --fit-max-samples "$FIT_MAX_SAMPLES"
  --backend "$BACKEND"
  --render-mode "$RENDER_MODE"
  --hist-bins-2d "$HIST_BINS_2D"
  --hist-bins-3d "$HIST_BINS_3D"
  --max-render-points "$MAX_RENDER_POINTS"
  --out-dir "$OUT_DIR"
  --out-prefix "$OUT_PREFIX"
  --verbose
)

if [[ -n "$STRIDE_S" ]]; then
  args+=(--stride-s "$STRIDE_S")
fi

"$PYTHON" "${args[@]}"

VOXELS="$OUT_DIR/${OUT_PREFIX}_pc123_voxels.parquet"
POINTS="$OUT_DIR/${OUT_PREFIX}_point_sample.parquet"
OPEN3D_IMG="$OUT_DIR/${OUT_PREFIX}_open3d.png"
OPEN3D_PLY="$OUT_DIR/${OUT_PREFIX}_open3d.ply"

if [[ -f "$VOXELS" ]]; then
  "$PYTHON" -m python.analytics.window_pca.open3d_render \
    --input-parquet "$VOXELS" \
    --mode voxels \
    --x-col pc1 \
    --y-col pc2 \
    --z-col pc3 \
    --count-col count \
    --max-points "$OPEN3D_MAX_POINTS" \
    --point-size "$OPEN3D_POINT_SIZE" \
    --out-image "$OPEN3D_IMG" \
    --out-ply "$OPEN3D_PLY"
elif [[ -f "$POINTS" ]]; then
  "$PYTHON" -m python.analytics.window_pca.open3d_render \
    --input-parquet "$POINTS" \
    --mode points \
    --max-points "$OPEN3D_MAX_POINTS" \
    --point-size "$OPEN3D_POINT_SIZE" \
    --out-image "$OPEN3D_IMG" \
    --out-ply "$OPEN3D_PLY"
else
  echo "[WARN] no voxels or point sample found for Open3D rendering"
fi

echo "[OK] output dir -> $OUT_DIR"
