#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-$HOME/svwatergo}"
BASE_SCRIPT="${BASE_SCRIPT:-$REPO/scripts/train_bluerock_panns_plc_pca_encoder.sh}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d_%H%M%S)}"

OUT_ROOT="${OUT_ROOT:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_panns_plc_pca_encoder_sweep_${RUN_TS}}"
LOG_ROOT="${LOG_ROOT:-/mnt/d/datasets/svwatergo/derived/logs/bluerock_10s_panns_plc_pca_encoder_sweep_${RUN_TS}}"

# Comma-separated list of sources to run individually.
SOURCES="${SOURCES:-rpi_audio,wyze_Bluerock_Cam_1,wyze_Bluerock_Cam_2,wyze_camera_5}"

mkdir -p "$OUT_ROOT" "$LOG_ROOT"

echo "[RUN] all_sources"
echo "      OUT_DIR=$OUT_ROOT/all_sources"
echo "      LOG=$LOG_ROOT/all_sources.log"
OUT_DIR="$OUT_ROOT/all_sources" \
AUDIO_SOURCE_FILTER="" \
bash "$BASE_SCRIPT" 2>&1 | tee "$LOG_ROOT/all_sources.log"

IFS=',' read -r -a SOURCE_ARR <<< "$SOURCES"
for src in "${SOURCE_ARR[@]}"; do
  src_trim="$(echo "$src" | xargs)"
  [[ -n "$src_trim" ]] || continue
  safe_name="$(echo "$src_trim" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9_' '_')"

  echo "[RUN] source=$src_trim"
  echo "      OUT_DIR=$OUT_ROOT/source_${safe_name}"
  echo "      LOG=$LOG_ROOT/source_${safe_name}.log"
  OUT_DIR="$OUT_ROOT/source_${safe_name}" \
  AUDIO_SOURCE_FILTER="$src_trim" \
  bash "$BASE_SCRIPT" 2>&1 | tee "$LOG_ROOT/source_${safe_name}.log"
done

echo "[DONE] sweep outputs -> $OUT_ROOT"
echo "[DONE] sweep logs -> $LOG_ROOT"
