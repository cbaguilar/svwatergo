#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

SITE="${SITE:-bluerock}"
LOCAL_ROOT="${LOCAL_ROOT:-/mnt/d/datasets/svwatergo/derived}"
RAW_ROOT="${RAW_ROOT:-/mnt/d/datasets/svwatergo/raw/plc}"
DATE_FROM="${DATE_FROM:-2025-12-01}"
DATE_TO="${DATE_TO:-2025-12-31}"
WINDOW_S="${WINDOW_S:-10}"
STRIDE_S="${STRIDE_S:-}"

OUT_DIR="${OUT_DIR:-/mnt/d/datasets/svwatergo/derived/plots/pca_noninteractive}"
RUN_STAMP="${RUN_STAMP:-$(date +%Y%m%d_%H%M%S)}"
RUN_DIR_NAME="${RUN_DIR_NAME:-${RUN_STAMP}_${SITE}_${DATE_FROM}_to_${DATE_TO}}"
OUT_PREFIX="${OUT_PREFIX:-pca}"
RUN_OUT_DIR="${RUN_OUT_DIR:-$OUT_DIR/$RUN_DIR_NAME}"

FIT_SAMPLE_PER_FILE="${FIT_SAMPLE_PER_FILE:-2000}"
FIT_MAX_SAMPLES="${FIT_MAX_SAMPLES:-2000000}"
BACKEND="${BACKEND:-auto}" # auto|cpu|gpu
PCA_CONTINUOUS_ONLY="${PCA_CONTINUOUS_ONLY:-yes}"
PCA_INCLUDE_REGEX="${PCA_INCLUDE_REGEX:-__mean_tw$,__d1$}"
PCA_EXCLUDE_REGEX="${PCA_EXCLUDE_REGEX:-__duty$,__mode_tw$,__transitions$,^state_unknown$}"

RENDER_MODE="${RENDER_MODE:-both}" # none|heatmap|points|both
HIST_BINS_2D="${HIST_BINS_2D:-1200}"
HIST_BINS_3D="${HIST_BINS_3D:-160}"
MAX_RENDER_POINTS="${MAX_RENDER_POINTS:-2000000}"
COLOR_GRID="${COLOR_GRID:-yes}"
COLOR_MAX_COLS="${COLOR_MAX_COLS:-18}"
COLOR_COLS="${COLOR_COLS:-}"

OPEN3D_MAX_POINTS="${OPEN3D_MAX_POINTS:-3000000}"
OPEN3D_POINT_SIZE="${OPEN3D_POINT_SIZE:-1.0}"
OPEN3D_RENDER="${OPEN3D_RENDER:-no}"
GENERATE_MISSING_WINDOWS="${GENERATE_MISSING_WINDOWS:-yes}"
REGENERATE_WINDOWS="${REGENERATE_WINDOWS:-no}"
TIMESTAMP_COL="${TIMESTAMP_COL:-plctime}"
WINDOW_JOBS="${WINDOW_JOBS:-1}"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*"; }

cd "$REPO"
T0="$(date +%s)"
if [[ "$LOCAL_ROOT" == *"/dataset=window_features" ]]; then
  WINDOW_FEATURES_ROOT="$LOCAL_ROOT"
  WINDOW_OUT_ROOT="${WINDOW_OUT_ROOT:-${LOCAL_ROOT%/dataset=window_features}}"
else
  WINDOW_OUT_ROOT="${WINDOW_OUT_ROOT:-$LOCAL_ROOT}"
  WINDOW_FEATURES_ROOT="$WINDOW_OUT_ROOT/dataset=window_features"
fi

log "Starting noninteractive PCA/Open3D pipeline"
log "Config: RUN_STAMP=$RUN_STAMP SITE=$SITE DATE_FROM=$DATE_FROM DATE_TO=$DATE_TO WINDOW_S=$WINDOW_S BACKEND=$BACKEND OUT_DIR=$OUT_DIR RUN_DIR_NAME=$RUN_DIR_NAME OUT_PREFIX=$OUT_PREFIX RUN_OUT_DIR=$RUN_OUT_DIR"
log "Paths: RAW_ROOT=$RAW_ROOT WINDOW_FEATURES_ROOT=$WINDOW_FEATURES_ROOT WINDOW_OUT_ROOT=$WINDOW_OUT_ROOT"
log "Headless mode: OPEN3D_RENDER=$OPEN3D_RENDER (no=skip Open3D image render)"
log "Color grid: COLOR_GRID=$COLOR_GRID COLOR_MAX_COLS=$COLOR_MAX_COLS"
log "PCA feature mode: PCA_CONTINUOUS_ONLY=$PCA_CONTINUOUS_ONLY"
log "Window rebuild flags: GENERATE_MISSING_WINDOWS=$GENERATE_MISSING_WINDOWS REGENERATE_WINDOWS=$REGENERATE_WINDOWS"

if [[ "$GENERATE_MISSING_WINDOWS" == "yes" ]]; then
  mapfile -t DAYS < <("$PYTHON" - <<PY
import datetime as dt
d0=dt.date.fromisoformat("$DATE_FROM")
d1=dt.date.fromisoformat("$DATE_TO")
n=(d1-d0).days
for i in range(n+1):
    print((d0+dt.timedelta(days=i)).isoformat())
PY
)

  missing=0
  MISSING_DAYS=()
  for DAY in "${DAYS[@]}"; do
    WF_PATH="$WINDOW_FEATURES_ROOT/window_s=${WINDOW_S}/site=${SITE}/date=${DAY}/window_features.parquet"
    if [[ -n "$STRIDE_S" && "$STRIDE_S" != "$WINDOW_S" ]]; then
      WF_PATH="$WINDOW_FEATURES_ROOT/window_s=${WINDOW_S}/stride_s=${STRIDE_S}/site=${SITE}/date=${DAY}/window_features.parquet"
    fi
    if [[ "$REGENERATE_WINDOWS" == "yes" ]]; then
      missing=$((missing+1))
      MISSING_DAYS+=("$DAY")
    elif [[ ! -f "$WF_PATH" ]]; then
      missing=$((missing+1))
      MISSING_DAYS+=("$DAY")
    fi
  done
  log "Window feature precheck: missing_days=$missing total_days=${#DAYS[@]} window_jobs=$WINDOW_JOBS"

  if [[ "$missing" -gt 0 ]]; then
    if [[ "$WINDOW_JOBS" -le 1 ]]; then
      for DAY in "${MISSING_DAYS[@]}"; do
        if [[ "$REGENERATE_WINDOWS" == "yes" ]]; then
          DAY_DIR="$WINDOW_FEATURES_ROOT/window_s=${WINDOW_S}/site=${SITE}/date=${DAY}"
          if [[ -n "$STRIDE_S" && "$STRIDE_S" != "$WINDOW_S" ]]; then
            DAY_DIR="$WINDOW_FEATURES_ROOT/window_s=${WINDOW_S}/stride_s=${STRIDE_S}/site=${SITE}/date=${DAY}"
          fi
          rm -rf "$DAY_DIR"
        fi
        log "Generating window features for missing day: $DAY"
        gen_args=(
          -m python.analytics.s3_day_to_window_features
          --site "$SITE"
          --day "$DAY"
          --local-root "$RAW_ROOT"
          --out-dir "$WINDOW_OUT_ROOT"
          --timestamp-col "$TIMESTAMP_COL"
          --window-seconds "$WINDOW_S"
        )
        if [[ -n "$STRIDE_S" ]]; then
          gen_args+=(--stride-seconds "$STRIDE_S")
        fi
        "$PYTHON" "${gen_args[@]}"
      done
    else
      log "Generating missing window features in parallel"
      running=0
      for DAY in "${MISSING_DAYS[@]}"; do
        (
          if [[ "$REGENERATE_WINDOWS" == "yes" ]]; then
            DAY_DIR="$WINDOW_FEATURES_ROOT/window_s=${WINDOW_S}/site=${SITE}/date=${DAY}"
            if [[ -n "$STRIDE_S" && "$STRIDE_S" != "$WINDOW_S" ]]; then
              DAY_DIR="$WINDOW_FEATURES_ROOT/window_s=${WINDOW_S}/stride_s=${STRIDE_S}/site=${SITE}/date=${DAY}"
            fi
            rm -rf "$DAY_DIR"
          fi
          echo "[$(ts)] [wf] start day=$DAY"
          gen_args=(
            -m python.analytics.s3_day_to_window_features
            --site "$SITE"
            --day "$DAY"
            --local-root "$RAW_ROOT"
            --out-dir "$WINDOW_OUT_ROOT"
            --timestamp-col "$TIMESTAMP_COL"
            --window-seconds "$WINDOW_S"
          )
          if [[ -n "$STRIDE_S" ]]; then
            gen_args+=(--stride-seconds "$STRIDE_S")
          fi
          "$PYTHON" "${gen_args[@]}"
          echo "[$(ts)] [wf] done day=$DAY"
        ) &
        running=$((running + 1))
        if [[ "$running" -ge "$WINDOW_JOBS" ]]; then
          wait -n
          running=$((running - 1))
        fi
      done
      wait
      log "Parallel window generation complete"
    fi
  fi
fi

args=(
  -m python.analytics.window_pca.scalable_cli
  --local-root "$WINDOW_FEATURES_ROOT"
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
  --out-dir "$RUN_OUT_DIR"
  --out-prefix "$OUT_PREFIX"
  --verbose
)

if [[ -n "$STRIDE_S" ]]; then
  args+=(--stride-s "$STRIDE_S")
fi
if [[ "$PCA_CONTINUOUS_ONLY" == "yes" ]]; then
  IFS=',' read -r -a _inc <<< "$PCA_INCLUDE_REGEX"
  IFS=',' read -r -a _exc <<< "$PCA_EXCLUDE_REGEX"
  for x in "${_inc[@]}"; do
    [[ -n "$x" ]] && args+=(--include-regex "$x")
  done
  for x in "${_exc[@]}"; do
    [[ -n "$x" ]] && args+=(--exclude-regex "$x")
  done
fi
if [[ "$COLOR_GRID" == "yes" ]]; then
  args+=(--color-grid --color-max-cols "$COLOR_MAX_COLS")
  if [[ -n "$COLOR_COLS" ]]; then
    args+=(--color-cols "$COLOR_COLS")
  fi
fi

log "Running scalable PCA projection + render artifact generation"
"$PYTHON" "${args[@]}"
log "PCA stage complete"

VOXELS="$RUN_OUT_DIR/${OUT_PREFIX}_pc123_voxels.parquet"
POINTS="$RUN_OUT_DIR/${OUT_PREFIX}_point_sample.parquet"
OPEN3D_IMG="$RUN_OUT_DIR/${OUT_PREFIX}_open3d.png"
OPEN3D_PLY="$RUN_OUT_DIR/${OUT_PREFIX}_open3d.ply"

if [[ "$OPEN3D_RENDER" == "yes" ]]; then
  if [[ -f "$VOXELS" ]]; then
    log "Rendering Open3D from voxel cloud: $VOXELS"
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
      --out-ply "$OPEN3D_PLY" || log "[WARN] Open3D render failed; continuing headless outputs only"
  elif [[ -f "$POINTS" ]]; then
    log "Rendering Open3D from point sample: $POINTS"
    "$PYTHON" -m python.analytics.window_pca.open3d_render \
      --input-parquet "$POINTS" \
      --mode points \
      --max-points "$OPEN3D_MAX_POINTS" \
      --point-size "$OPEN3D_POINT_SIZE" \
      --out-image "$OPEN3D_IMG" \
      --out-ply "$OPEN3D_PLY" || log "[WARN] Open3D render failed; continuing headless outputs only"
  else
    log "[WARN] no voxels or point sample found for Open3D rendering"
  fi
else
  log "Skipping Open3D render (OPEN3D_RENDER=no). Use *_pc_heatmaps.png and *_pc123_points.png outputs."
fi

T1="$(date +%s)"
ELAPSED="$((T1 - T0))"
log "Done. Elapsed=${ELAPSED}s run_output_dir=$RUN_OUT_DIR"
