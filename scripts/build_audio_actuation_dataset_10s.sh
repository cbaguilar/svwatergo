#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-/home/cbaguilar/miniforge3/envs/rapids-cu13/bin/python}"
SITE="${SITE:-bluerock}"
RAW_ROOT="${RAW_ROOT:-/mnt/d/datasets/svwatergo/raw}"
OUT_ROOT="${OUT_ROOT:-/mnt/d/datasets/svwatergo/derived}"

INCLUDE_RPI="${INCLUDE_RPI:-yes}"
INCLUDE_WYZE="${INCLUDE_WYZE:-yes}"
SKIP_EXISTING="${SKIP_EXISTING:-yes}"
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
SPLIT_ACTUATORS="${SPLIT_ACTUATORS:-ropumprun,wellpumprun,feedpumprun,deliveryrun,flushrun}"
SPLIT_MIN_POSITIVE_COUNT="${SPLIT_MIN_POSITIVE_COUNT:-3}"

EMBEDDING_DEVICE="${EMBEDDING_DEVICE:-cuda}"
EMBEDDING_TARGET_SECONDS="${EMBEDDING_TARGET_SECONDS:-10}"
EMBEDDING_BATCH_SIZE="${EMBEDDING_BATCH_SIZE:-32}"
EMBEDDING_NUM_WORKERS="${EMBEDDING_NUM_WORKERS:-8}"
EMBEDDING_LOG_EVERY="${EMBEDDING_LOG_EVERY:-512}"
WRITE_EMBEDDINGS_JOINED="${WRITE_EMBEDDINGS_JOINED:-yes}"

DATE_LIST="${DATE_LIST:-}"
WYZE_CAMERA_LIST="${WYZE_CAMERA_LIST:-}"

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
  --split-actuators "$SPLIT_ACTUATORS"
  --split-min-positive-count "$SPLIT_MIN_POSITIVE_COUNT"
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
  --embedding-device "$EMBEDDING_DEVICE"
  --embedding-target-seconds "$EMBEDDING_TARGET_SECONDS"
  --embedding-batch-size "$EMBEDDING_BATCH_SIZE"
  --embedding-num-workers "$EMBEDDING_NUM_WORKERS"
  --embedding-log-every "$EMBEDDING_LOG_EVERY"
  --write-embeddings-joined "$WRITE_EMBEDDINGS_JOINED"
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

echo "[run] site=$SITE include_rpi=$INCLUDE_RPI include_wyze=$INCLUDE_WYZE embedding_device=$EMBEDDING_DEVICE"
"$PYTHON" python/analytics/build_audio_actuation_dataset.py "${args[@]}"
