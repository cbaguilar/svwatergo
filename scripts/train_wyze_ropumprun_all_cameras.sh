#!/usr/bin/env bash
set -uo pipefail

PYTHON="${PYTHON:-python3}"
REPO="${REPO:-/home/cbaguilar/work/water/svwatergo}"
SRC_ROOT="${SRC_ROOT:-/run/media/cbaguilar/T7/wyze_dump}"
DATE="${DATE:-$(date -u -d 'yesterday' +%F)}"

PLC_BUCKET="${PLC_BUCKET:-svwaternet}"
PLC_PREFIX="${PLC_PREFIX:-exports/postgres/plc}"

TARGET_SECONDS="${TARGET_SECONDS:-10}"
SAMPLE_RATE="${SAMPLE_RATE:-16000}"
MIN_SIZE_BYTES="${MIN_SIZE_BYTES:-1024}"

cd "$REPO"

if ! command -v aws >/dev/null; then
  echo "[FATAL] aws CLI not found in PATH"
  exit 1
fi
if ! command -v ffmpeg >/dev/null; then
  echo "[FATAL] ffmpeg not found in PATH"
  exit 1
fi
if ! command -v ffprobe >/dev/null; then
  echo "[FATAL] ffprobe not found in PATH"
  exit 1
fi
if ! "$PYTHON" -c "import pyarrow" >/dev/null 2>&1; then
  echo "[FATAL] pyarrow missing for interpreter: $PYTHON"
  echo "        Install with: $PYTHON -m pip install pyarrow"
  exit 1
fi

declare -a CAMERAS=(
  "Bluerock_Cam_1"
  "Bluerock_Cam_2"
  "camera_5"
  "Pryor_Farms_1"
  "Pryor_Farms_1_inside_near_door_"
  "Pryor_Farms_3_behind_ro_"
  "Santa_Teresa_Cam_1"
  "Santa_Teresa_Outside"
)

declare -A CAMERA_SITE=(
  ["Bluerock_Cam_1"]="bluerock"
  ["Bluerock_Cam_2"]="bluerock"
  ["camera_5"]="bluerock"
  ["Pryor_Farms_1"]="pryorfarm"
  ["Pryor_Farms_1_inside_near_door_"]="pryorfarm"
  ["Pryor_Farms_3_behind_ro_"]="pryorfarm"
  ["Santa_Teresa_Cam_1"]="santateresa"
  ["Santa_Teresa_Outside"]="santateresa"
)

echo "============================================================"
echo "[START] Wyze audio train/infer pipeline $(date -u)"
echo "[INFO] DATE=${DATE} TARGET_SECONDS=${TARGET_SECONDS} SAMPLE_RATE=${SAMPLE_RATE}"
echo "============================================================"

TOTAL_CAMERAS=0
OK_CAMERAS=0
SKIP_CAMERAS=0
FAIL_CAMERAS=0

for SITE in bluerock pryorfarm santateresa; do
  PLC_LOCAL_DIR="data/raw/plc/${SITE}/date=${DATE}"
  PLC_LOCAL_PATH="${PLC_LOCAL_DIR}/data.parquet"
  mkdir -p "$PLC_LOCAL_DIR"
  echo "[PLC] s3://$PLC_BUCKET/$PLC_PREFIX/site=${SITE}/date=${DATE}/data.parquet -> $PLC_LOCAL_PATH"
  if ! aws s3 cp \
    "s3://${PLC_BUCKET}/${PLC_PREFIX}/site=${SITE}/date=${DATE}/data.parquet" \
    "$PLC_LOCAL_PATH"; then
    echo "[FATAL] failed to download PLC parquet for site=${SITE} date=${DATE}"
    exit 1
  fi
done

for CAM in "${CAMERAS[@]}"; do
  TOTAL_CAMERAS=$((TOTAL_CAMERAS + 1))
  SITE="${CAMERA_SITE[$CAM]}"
  CAM_SAFE="$(echo "$CAM" | tr -cs 'A-Za-z0-9._-' '_' | sed 's/^_//; s/_$//')"

  CAM_SRC="${SRC_ROOT}/camera=${CAM}/date=${DATE}"
  if [[ ! -d "$CAM_SRC" ]]; then
    echo "[SKIP] missing camera folder: $CAM_SRC"
    SKIP_CAMERAS=$((SKIP_CAMERAS + 1))
    continue
  fi

  PLC_LOCAL_PATH="data/raw/plc/${SITE}/date=${DATE}/data.parquet"
  if [[ ! -f "$PLC_LOCAL_PATH" ]]; then
    echo "[SKIP] missing PLC parquet for site=${SITE} day=${DATE}"
    SKIP_CAMERAS=$((SKIP_CAMERAS + 1))
    continue
  fi

  WAV_OUT="data/raw/${CAM_SAFE}_${DATE}_wav"
  MEL_OUT="data/derived/${CAM_SAFE}_${DATE}_mel_${TARGET_SECONDS}s"
  LABELED_OUT="data/derived/ropumprun_labeled_mels_${CAM_SAFE}_${DATE}_${TARGET_SECONDS}s.parquet"
  CKPT_OUT="data/checkpoints/ropumprun_on_pca_svm_${CAM_SAFE}_${DATE}_${TARGET_SECONDS}s"
  PLOT_PNG="data/plots/${CAM_SAFE}_${DATE}_${TARGET_SECONDS}s_4panel.png"
  PLOT_META="data/plots/${CAM_SAFE}_${DATE}_${TARGET_SECONDS}s_4panel.json"
  INFER_JSON="data/inference/${CAM_SAFE}_${DATE}_${TARGET_SECONDS}s_infer_sample.json"

  mkdir -p "$(dirname "$LABELED_OUT")" "$CKPT_OUT" "$(dirname "$PLOT_PNG")" "$(dirname "$INFER_JSON")"

  echo
  echo "------------------------------------------------------------"
  echo "[RUN] camera=${CAM} site=${SITE} date=${DATE}"
  echo "------------------------------------------------------------"

  if ! "$PYTHON" python/analytics/wyze_webm_to_wav.py \
    --local-root "$CAM_SRC" \
    --out-dir "$WAV_OUT" \
    --site "$SITE" \
    --camera "$CAM" \
    --timestamp-kind start \
    --sample-rate "$SAMPLE_RATE" \
    --channels 1 \
    --min-size-bytes "$MIN_SIZE_BYTES" \
    --skip-existing; then
    echo "[FAIL] wyze_webm_to_wav failed for camera=${CAM}"
    FAIL_CAMERAS=$((FAIL_CAMERAS + 1))
    continue
  fi

  WAV_MANIFEST="${WAV_OUT}/dataset=wyze_webm_wav/site=${SITE}/wyze_webm_wav_manifest.parquet"
  if [[ ! -f "$WAV_MANIFEST" ]]; then
    echo "[SKIP] missing wav manifest: $WAV_MANIFEST"
    SKIP_CAMERAS=$((SKIP_CAMERAS + 1))
    continue
  fi

  if ! "$PYTHON" python/analytics/audio_mel_segments.py \
    --segments-root "$WAV_OUT" \
    --segments-manifest "$WAV_MANIFEST" \
    --out-dir "$MEL_OUT" \
    --site "$SITE" \
    --sample-rate "$SAMPLE_RATE" \
    --target-seconds "$TARGET_SECONDS" \
    --skip-existing-shards \
    --partition-by utc_day; then
    echo "[FAIL] audio_mel_segments failed for camera=${CAM}"
    FAIL_CAMERAS=$((FAIL_CAMERAS + 1))
    continue
  fi

  MEL_MANIFEST="${MEL_OUT}/dataset=audio_mel_segments/site=${SITE}/audio_mel_segments.parquet"
  if [[ ! -f "$MEL_MANIFEST" ]]; then
    echo "[SKIP] missing mel manifest: $MEL_MANIFEST"
    SKIP_CAMERAS=$((SKIP_CAMERAS + 1))
    continue
  fi

  if ! "$PYTHON" -m python.ml.cli.audio_plc_dataset \
    --mel-manifest "$MEL_MANIFEST" \
    --plc-rows "$PLC_LOCAL_PATH" \
    --camera "$CAM" \
    --site "$SITE" \
    --plc-col ropumprun \
    --timestamp-col plctime \
    --out-parquet "$LABELED_OUT"; then
    echo "[FAIL] audio_plc_dataset failed for camera=${CAM}"
    FAIL_CAMERAS=$((FAIL_CAMERAS + 1))
    continue
  fi

  "$PYTHON" - "$LABELED_OUT" <<'PY'
import sys
import pandas as pd
path = sys.argv[1]
df = pd.read_parquet(path, columns=["ropumprun_label"])
vals = sorted([str(x) for x in df["ropumprun_label"].dropna().unique().tolist()])
print(f"[INFO] label classes={vals} n_unique={len(vals)}")
sys.exit(0 if len(vals) >= 2 else 2)
PY
  rc=$?
  if [[ $rc -ne 0 ]]; then
    if [[ $rc -eq 2 ]]; then
      echo "[SKIP] training skipped for camera=${CAM} (only one class present in labels)"
      SKIP_CAMERAS=$((SKIP_CAMERAS + 1))
      continue
    fi
    echo "[FAIL] class check failed for camera=${CAM}"
    FAIL_CAMERAS=$((FAIL_CAMERAS + 1))
    continue
  fi

  if ! "$PYTHON" -m python.ml.cli.audio_pca_svm_train \
    --dataset "$LABELED_OUT" \
    --out-dir "$CKPT_OUT" \
    --task binary \
    --target-col ropumprun_label \
    --positive-label on \
    --n-components 8 \
    --svm-class-weight balanced \
    --sample-rate "$SAMPLE_RATE" \
    --target-seconds "$TARGET_SECONDS"; then
    echo "[FAIL] audio_pca_svm_train failed for camera=${CAM}"
    FAIL_CAMERAS=$((FAIL_CAMERAS + 1))
    continue
  fi

  if ! "$PYTHON" -m python.ml.cli.audio_pca_svm_plot \
    --checkpoint-dir "$CKPT_OUT" \
    --out-png "$PLOT_PNG" \
    --out-meta "$PLOT_META" \
    --title "Audio PCA+SVM (${CAM}, ${DATE}, ${TARGET_SECONDS}s)"; then
    echo "[FAIL] audio_pca_svm_plot failed for camera=${CAM}"
    FAIL_CAMERAS=$((FAIL_CAMERAS + 1))
    continue
  fi

  SAMPLE_WAV="$(find "$WAV_OUT" -type f -name '*.wav' | head -n 1 || true)"
  if [[ -n "$SAMPLE_WAV" ]]; then
    if ! "$PYTHON" -m python.ml.cli.audio_pca_svm_infer \
      --model "${CKPT_OUT}/audio_pca_svm_model.joblib" \
      --wav "$SAMPLE_WAV" > "$INFER_JSON"; then
      echo "[FAIL] audio_pca_svm_infer failed for camera=${CAM}"
      FAIL_CAMERAS=$((FAIL_CAMERAS + 1))
      continue
    fi
    echo "[OK] inference -> $INFER_JSON"
  else
    echo "[SKIP] no wav found for inference in $WAV_OUT"
  fi

  echo "[OK] plot -> $PLOT_PNG"
  echo "[OK] model -> ${CKPT_OUT}/audio_pca_svm_model.joblib"
  OK_CAMERAS=$((OK_CAMERAS + 1))
done

echo
echo "============================================================"
echo "[DONE] Wyze audio train/infer pipeline $(date -u)"
echo "[SUMMARY] total=${TOTAL_CAMERAS} ok=${OK_CAMERAS} skipped=${SKIP_CAMERAS} failed=${FAIL_CAMERAS}"
echo "============================================================"
