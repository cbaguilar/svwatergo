#!/usr/bin/env bash
set -euo pipefail

# Generic site dataset builder for 10s audio-event windows.
# Example:
#   SITE=pryorfarm bash scripts/build_audio_event_dataset_10s.sh
#   SITE=santateresa INCLUDE_WYZE=yes bash scripts/build_audio_event_dataset_10s.sh
#
# Wyze camera defaults by site (from builder code):
#   bluerock:    Bluerock_Cam_1, Bluerock_Cam_2, camera_5
#   pryorfarm:   Pryor_Farms_1, Pryor_Farms_1_inside_near_door_, Pryor_Farms_3_behind_ro_
#   santateresa: Santa_Teresa_Cam_1, Santa_Teresa_Outside
# Override with:
#   WYZE_CAMERA_LIST="cam_a,cam_b"

PYTHON="${PYTHON:-/home/cbaguilar/miniforge3/envs/rapids-cu13/bin/python}"
SITE="${SITE:-bluerock}"
RAW_ROOT="${RAW_ROOT:-/mnt/d/datasets/svwatergo/raw}"
OUT_ROOT="${OUT_ROOT:-/mnt/d/datasets/svwatergo/derived}"

INCLUDE_RPI="${INCLUDE_RPI:-yes}"
INCLUDE_WYZE="${INCLUDE_WYZE:-yes}"
SKIP_EXISTING="${SKIP_EXISTING:-no}"
SKIP_WYZE_CONVERSION="${SKIP_WYZE_CONVERSION:-no}"

WINDOW_SECONDS="${WINDOW_SECONDS:-10}"
STRIDE_SECONDS="${STRIDE_SECONDS:-10}"
MAX_EVENT_GAP_SECONDS="${MAX_EVENT_GAP_SECONDS:-60}"
MAX_EVENT_WINDOW_SECONDS="${MAX_EVENT_WINDOW_SECONDS:-200}"
MAX_GAP_STALE_S="${MAX_GAP_STALE_S:-300}"

MEL_N_FFT="${MEL_N_FFT:-1024}"
MEL_WIN_LENGTH="${MEL_WIN_LENGTH:-1024}"
MEL_HOP_LENGTH="${MEL_HOP_LENGTH:-256}"
MEL_N_MELS="${MEL_N_MELS:-64}"
MEL_FMIN="${MEL_FMIN:-20}"
MEL_FMAX="${MEL_FMAX:-8000}"
MEL_POWER="${MEL_POWER:-2.0}"
MEL_LOG_EPS="${MEL_LOG_EPS:-1e-10}"
MEL_NORMALIZATION="${MEL_NORMALIZATION:-log_db}"
MEL_DTYPE="${MEL_DTYPE:-float32}"
MEL_SHARD_SIZE="${MEL_SHARD_SIZE:-1024}"

TRAIN_RATIO="${TRAIN_RATIO:-0.70}"
TEST_RATIO="${TEST_RATIO:-0.15}"
VAL_RATIO="${VAL_RATIO:-0.15}"
SPLIT_SEED="${SPLIT_SEED:-1337}"

DATE_LIST="${DATE_LIST:-}"          # comma-separated dates
WYZE_CAMERA_LIST="${WYZE_CAMERA_LIST:-}"  # comma-separated camera names

args=(
  --site "$SITE"
  --raw-root "$RAW_ROOT"
  --out-root "$OUT_ROOT"
  --sample-rate 16000
  --window-seconds "$WINDOW_SECONDS"
  --stride-seconds "$STRIDE_SECONDS"
  --max-event-gap-seconds "$MAX_EVENT_GAP_SECONDS"
  --max-event-window-seconds "$MAX_EVENT_WINDOW_SECONDS"
  --max-gap-stale-s "$MAX_GAP_STALE_S"
  --split-seed "$SPLIT_SEED"
  --train-ratio "$TRAIN_RATIO"
  --test-ratio "$TEST_RATIO"
  --val-ratio "$VAL_RATIO"
  --mel-n-fft "$MEL_N_FFT"
  --mel-win-length "$MEL_WIN_LENGTH"
  --mel-hop-length "$MEL_HOP_LENGTH"
  --mel-n-mels "$MEL_N_MELS"
  --mel-fmin "$MEL_FMIN"
  --mel-fmax "$MEL_FMAX"
  --mel-power "$MEL_POWER"
  --mel-log-eps "$MEL_LOG_EPS"
  --mel-normalization "$MEL_NORMALIZATION"
  --mel-dtype "$MEL_DTYPE"
  --mel-shard-size "$MEL_SHARD_SIZE"
)

if [[ "$INCLUDE_RPI" == "yes" ]]; then
  args+=(--include-rpi)
fi
if [[ "$INCLUDE_WYZE" == "yes" ]]; then
  args+=(--include-wyze)
fi
if [[ "$SKIP_EXISTING" == "yes" ]]; then
  args+=(--skip-existing)
else
  args+=(--no-skip-existing)
fi
if [[ "$SKIP_WYZE_CONVERSION" == "yes" ]]; then
  args+=(--skip-wyze-conversion)
fi

if [[ -n "$DATE_LIST" ]]; then
  IFS=',' read -r -a _dates <<< "$DATE_LIST"
  for d in "${_dates[@]}"; do
    d="$(echo "$d" | xargs)"
    [[ -n "$d" ]] && args+=(--date "$d")
  done
fi

if [[ -n "$WYZE_CAMERA_LIST" ]]; then
  IFS=',' read -r -a _cams <<< "$WYZE_CAMERA_LIST"
  for c in "${_cams[@]}"; do
    c="$(echo "$c" | xargs)"
    [[ -n "$c" ]] && args+=(--wyze-camera "$c")
  done
fi

echo "[run] site=$SITE mel_normalization=$MEL_NORMALIZATION include_rpi=$INCLUDE_RPI include_wyze=$INCLUDE_WYZE"
"$PYTHON" python/analytics/build_bluerock_audio_dataset.py "${args[@]}"
