#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

WINDOW_S="${WINDOW_S:-10}"
SITE="${SITE:-bluerock}"
SOURCE_VALUE="${SOURCE_VALUE:-rpi_audio}"
MATRIX_ROOT="${MATRIX_ROOT:-/mnt/d/datasets/svwatergo/domain_matrix/source}"
CHECKPOINT_RUN="${CHECKPOINT_RUN:-train_${SITE}__${SOURCE_VALUE}_auxsweep_1p0_ep15}"
DAY="${DAY:-2025-07-04}"
TIMEZONE="${TIMEZONE:-America/New_York}"
DATASET="${DATASET:-}"
EMBEDDINGS_NPZ="${EMBEDDINGS_NPZ:-}"
MODEL="${MODEL:-}"
OUT_DIR="${OUT_DIR:-}"
OUT_PARQUET="${OUT_PARQUET:-}"
OUT_PNG="${OUT_PNG:-}"
OUT_JSON="${OUT_JSON:-}"

resolve_site_paths() {
  local site="$1"
  case "$site" in
    bluerock)
      DATASET_DEFAULT="/mnt/d/datasets/svwatergo/derived_5actsplit/dataset=audio_actuation_dataset/site=bluerock/window_s=${WINDOW_S}/samples.parquet"
      EMBEDDINGS_DEFAULT="/mnt/d/datasets/svwatergo/derived_5actsplit/dataset=audio_actuation_dataset/site=bluerock/window_s=${WINDOW_S}/embeddings_panns.npz"
      OUT_DIR_DEFAULT="/mnt/d/datasets/svwatergo/derived_5actsplit/plots/site=bluerock/window_s=${WINDOW_S}/day_window_inference/source=${SOURCE_VALUE}/day=${DAY}"
      ;;
    pryorfarm)
      DATASET_DEFAULT="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm_5actsplit/dataset=audio_actuation_dataset/site=pryorfarm/window_s=${WINDOW_S}/samples.parquet"
      EMBEDDINGS_DEFAULT="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm_5actsplit/dataset=audio_actuation_dataset/site=pryorfarm/window_s=${WINDOW_S}/embeddings_panns.npz"
      OUT_DIR_DEFAULT="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm_5actsplit/plots/site=pryorfarm/window_s=${WINDOW_S}/day_window_inference/source=${SOURCE_VALUE}/day=${DAY}"
      ;;
    santateresa)
      DATASET_DEFAULT="/mnt/d/datasets/svwatergo/derived_wyze_santateresa_5actsplit/dataset=audio_actuation_dataset/site=santateresa/window_s=${WINDOW_S}/samples.parquet"
      EMBEDDINGS_DEFAULT="/mnt/d/datasets/svwatergo/derived_wyze_santateresa_5actsplit/dataset=audio_actuation_dataset/site=santateresa/window_s=${WINDOW_S}/embeddings_panns.npz"
      OUT_DIR_DEFAULT="/mnt/d/datasets/svwatergo/derived_wyze_santateresa_5actsplit/plots/site=santateresa/window_s=${WINDOW_S}/day_window_inference/source=${SOURCE_VALUE}/day=${DAY}"
      ;;
    *)
      echo "unknown site: $site" >&2
      exit 2
      ;;
  esac
}

cd "$REPO"

resolve_site_paths "$SITE"

DATASET="${DATASET:-$DATASET_DEFAULT}"
EMBEDDINGS_NPZ="${EMBEDDINGS_NPZ:-$EMBEDDINGS_DEFAULT}"
MODEL="${MODEL:-$MATRIX_ROOT/checkpoints/${CHECKPOINT_RUN}/audio_pretrained_embedding_multitask_best.pt}"
OUT_DIR="${OUT_DIR:-$OUT_DIR_DEFAULT}"
OUT_PARQUET="${OUT_PARQUET:-$OUT_DIR/${SITE}_${SOURCE_VALUE}_${DAY}_true_vs_pred.parquet}"
OUT_PNG="${OUT_PNG:-$OUT_DIR/${SITE}_${SOURCE_VALUE}_${DAY}_true_vs_pred.png}"
OUT_JSON="${OUT_JSON:-$OUT_DIR/${SITE}_${SOURCE_VALUE}_${DAY}_true_vs_pred.json}"

"$PYTHON" python/analytics/predict_actuation_day_window.py \
  --dataset "$DATASET" \
  --embeddings-npz "$EMBEDDINGS_NPZ" \
  --model "$MODEL" \
  --day "$DAY" \
  --timezone "$TIMEZONE" \
  --source-value "$SOURCE_VALUE" \
  --out-parquet "$OUT_PARQUET" \
  --out-png "$OUT_PNG" \
  --out-json "$OUT_JSON"
