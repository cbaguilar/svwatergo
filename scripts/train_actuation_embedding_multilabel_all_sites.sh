#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

SITE_LIST="${SITE_LIST:-bluerock,pryorfarm,santateresa}"
WINDOW_S="${WINDOW_S:-10}"
TARGET_COLS="${TARGET_COLS:-ropumprun_duty_target,wellpumprun_duty_target,feedpumprun_duty_target,deliveryrun_duty_target,flushrun_duty_target}"
POSITIVE_THRESHOLD="${POSITIVE_THRESHOLD:-0.5}"
ENCODER_HIDDEN="${ENCODER_HIDDEN:-512,256}"
ENCODER_DROPOUT="${ENCODER_DROPOUT:-0.2}"
EPOCHS="${EPOCHS:-60}"
BATCH_SIZE="${BATCH_SIZE:-128}"
LEARNING_RATE="${LEARNING_RATE:-1e-3}"
WEIGHT_DECAY="${WEIGHT_DECAY:-1e-4}"
EVAL_EVERY="${EVAL_EVERY:-5}"
TARGET_SECONDS="${TARGET_SECONDS:-10}"
EXTRACT_BATCH_SIZE="${EXTRACT_BATCH_SIZE:-32}"
EXTRACT_NUM_WORKERS="${EXTRACT_NUM_WORKERS:-8}"
EXTRACT_LOG_EVERY="${EXTRACT_LOG_EVERY:-512}"
AUX_PLC_PCA="${AUX_PLC_PCA:-yes}"
AUX_PLC_INCLUDE_DUTY_COLS="${AUX_PLC_INCLUDE_DUTY_COLS:-no}"
AUX_PLC_COMPONENTS="${AUX_PLC_COMPONENTS:-8}"
AUX_PLC_WEIGHT="${AUX_PLC_WEIGHT:-0.3}"
PANN_PCA_COMPONENTS="${PANN_PCA_COMPONENTS:-8}"
PANN_PCA_WEIGHT="${PANN_PCA_WEIGHT:-1.0}"
BEST_MODEL_SPLIT="${BEST_MODEL_SPLIT:-val}"

resolve_site_paths() {
  local site="$1"
  case "$site" in
    bluerock)
      DATASET="/mnt/d/datasets/svwatergo/derived/dataset=audio_actuation_dataset/site=bluerock/window_s=${WINDOW_S}/samples.parquet"
      SPLIT="/mnt/d/datasets/svwatergo/derived/dataset=audio_actuation_dataset/site=bluerock/window_s=${WINDOW_S}/split_manifest.parquet"
      EMBEDDINGS_NPZ="/mnt/d/datasets/svwatergo/derived/dataset=audio_actuation_dataset/site=bluerock/window_s=${WINDOW_S}/embeddings_panns.npz"
      OUT_DIR="/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_${WINDOW_S}s_panns_actuation_5bool_multilabel"
      ;;
    pryorfarm)
      DATASET="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm/dataset=audio_actuation_dataset/site=pryorfarm/window_s=${WINDOW_S}/samples.parquet"
      SPLIT="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm/dataset=audio_actuation_dataset/site=pryorfarm/window_s=${WINDOW_S}/split_manifest.parquet"
      EMBEDDINGS_NPZ="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm/dataset=audio_actuation_dataset/site=pryorfarm/window_s=${WINDOW_S}/embeddings_panns.npz"
      OUT_DIR="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm/checkpoints/pryorfarm_${WINDOW_S}s_panns_actuation_5bool_multilabel"
      ;;
    santateresa)
      DATASET="/mnt/d/datasets/svwatergo/derived_wyze_santateresa/dataset=audio_actuation_dataset/site=santateresa/window_s=${WINDOW_S}/samples.parquet"
      SPLIT="/mnt/d/datasets/svwatergo/derived_wyze_santateresa/dataset=audio_actuation_dataset/site=santateresa/window_s=${WINDOW_S}/split_manifest.parquet"
      EMBEDDINGS_NPZ="/mnt/d/datasets/svwatergo/derived_wyze_santateresa/dataset=audio_actuation_dataset/site=santateresa/window_s=${WINDOW_S}/embeddings_panns.npz"
      OUT_DIR="/mnt/d/datasets/svwatergo/derived_wyze_santateresa/checkpoints/santateresa_${WINDOW_S}s_panns_actuation_5bool_multilabel"
      ;;
    *)
      echo "unknown site: $site" >&2
      exit 2
      ;;
  esac
}

cd "$REPO"

IFS=',' read -r -a SITES <<< "$SITE_LIST"
for SITE in "${SITES[@]}"; do
  SITE="$(echo "$SITE" | xargs)"
  [[ -n "$SITE" ]] || continue
  resolve_site_paths "$SITE"
  mkdir -p "$OUT_DIR"
  echo "[RUN] site=$SITE"
  echo "      dataset=$DATASET"
  echo "      embeddings=$EMBEDDINGS_NPZ"
  echo "      out_dir=$OUT_DIR"
  "$PYTHON" -m python.ml.cli.audio_pretrained_embedding_multitask_train \
    --dataset "$DATASET" \
    --split-manifest "$SPLIT" \
    --split-col split \
    --dataset-id-col sample_id \
    --split-id-col sample_id \
    --audio-path-col segment_path \
    --embeddings-npz "$EMBEDDINGS_NPZ" \
    --embeddings-key embeddings \
    --out-dir "$OUT_DIR" \
    --task-mode multilabel \
    --target-cols "$TARGET_COLS" \
    --positive-threshold "$POSITIVE_THRESHOLD" \
    --target-seconds "$TARGET_SECONDS" \
    --extract-batch-size "$EXTRACT_BATCH_SIZE" \
    --extract-num-workers "$EXTRACT_NUM_WORKERS" \
    --extract-log-every "$EXTRACT_LOG_EVERY" \
    --encoder-hidden "$ENCODER_HIDDEN" \
    --encoder-dropout "$ENCODER_DROPOUT" \
    --epochs "$EPOCHS" \
    --batch-size "$BATCH_SIZE" \
    --learning-rate "$LEARNING_RATE" \
    --weight-decay "$WEIGHT_DECAY" \
    --eval-every "$EVAL_EVERY" \
    --best-model-split "$BEST_MODEL_SPLIT" \
    --aux-plc-pca "$AUX_PLC_PCA" \
    --aux-plc-include-duty-cols "$AUX_PLC_INCLUDE_DUTY_COLS" \
    --aux-plc-components "$AUX_PLC_COMPONENTS" \
    --aux-plc-weight "$AUX_PLC_WEIGHT" \
    --pann-pca-components "$PANN_PCA_COMPONENTS" \
    --pann-pca-weight "$PANN_PCA_WEIGHT"
done
