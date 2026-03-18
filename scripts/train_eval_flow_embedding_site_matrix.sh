#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

WINDOW_S="${WINDOW_S:-10}"
SITE_LIST="${SITE_LIST:-bluerock,pryorfarm,santateresa}"
INCLUDE_POOLED="${INCLUDE_POOLED:-yes}"
MATRIX_ROOT="${MATRIX_ROOT:-/mnt/d/datasets/svwatergo/domain_matrix/flow_site}"
TARGET_COLS="${TARGET_COLS:-permeateflow__mean_tw,deliveryflow__mean_tw,feedflow__mean_tw,concentrateflow__mean_tw,recycleflow__mean_tw}"
ENCODER_HIDDEN="${ENCODER_HIDDEN:-1024,512,256}"
LATENT_DIM="${LATENT_DIM:-64}"
ENCODER_DROPOUT="${ENCODER_DROPOUT:-0.2}"
EPOCHS="${EPOCHS:-30}"
BATCH_SIZE="${BATCH_SIZE:-256}"
LEARNING_RATE="${LEARNING_RATE:-3e-4}"
WEIGHT_DECAY="${WEIGHT_DECAY:-1e-4}"
EVAL_EVERY="${EVAL_EVERY:-1}"
BEST_MODEL_METRIC="${BEST_MODEL_METRIC:-main_task_metric}"
BEST_MODEL_SPLIT="${BEST_MODEL_SPLIT:-val}"
AUX_PLC_PCA="${AUX_PLC_PCA:-yes}"
AUX_PLC_TARGET_MODE="${AUX_PLC_TARGET_MODE:-raw}"
AUX_PLC_FEATURE_COLS="${AUX_PLC_FEATURE_COLS:-plc_pca1,plc_pca2,plc_pca3,plc_pca4,plc_pca5,plc_pca6,plc_pca7,plc_pca8}"
AUX_PLC_WEIGHT="${AUX_PLC_WEIGHT:-0.0}"
PANN_PCA_WEIGHT="${PANN_PCA_WEIGHT:-0.0}"
RENDER_PLOTS="${RENDER_PLOTS:-no}"

resolve_site_paths() {
  local site="$1"
  case "$site" in
    bluerock)
      DATASET="/mnt/d/datasets/svwatergo/derived_5actsplit/dataset=audio_actuation_dataset/site=bluerock/window_s=${WINDOW_S}/samples.parquet"
      SPLIT="/mnt/d/datasets/svwatergo/derived_5actsplit/dataset=audio_actuation_dataset/site=bluerock/window_s=${WINDOW_S}/split_manifest.parquet"
      EMBEDDINGS_NPZ="/mnt/d/datasets/svwatergo/derived_5actsplit/dataset=audio_actuation_dataset/site=bluerock/window_s=${WINDOW_S}/embeddings_panns.npz"
      ;;
    pryorfarm)
      DATASET="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm_5actsplit/dataset=audio_actuation_dataset/site=pryorfarm/window_s=${WINDOW_S}/samples.parquet"
      SPLIT="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm_5actsplit/dataset=audio_actuation_dataset/site=pryorfarm/window_s=${WINDOW_S}/split_manifest.parquet"
      EMBEDDINGS_NPZ="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm_5actsplit/dataset=audio_actuation_dataset/site=pryorfarm/window_s=${WINDOW_S}/embeddings_panns.npz"
      ;;
    santateresa)
      DATASET="/mnt/d/datasets/svwatergo/derived_wyze_santateresa_5actsplit/dataset=audio_actuation_dataset/site=santateresa/window_s=${WINDOW_S}/samples.parquet"
      SPLIT="/mnt/d/datasets/svwatergo/derived_wyze_santateresa_5actsplit/dataset=audio_actuation_dataset/site=santateresa/window_s=${WINDOW_S}/split_manifest.parquet"
      EMBEDDINGS_NPZ="/mnt/d/datasets/svwatergo/derived_wyze_santateresa_5actsplit/dataset=audio_actuation_dataset/site=santateresa/window_s=${WINDOW_S}/embeddings_panns.npz"
      ;;
    *)
      echo "unknown site: $site" >&2
      exit 2
      ;;
  esac
}

append_summary() {
  local csv_path="$1"
  local train_domain="$2"
  local eval_domain="$3"
  local metrics_path="$4"
  python3 - "$csv_path" "$train_domain" "$eval_domain" "$metrics_path" <<'PY'
import csv, json, math, pathlib, sys
csv_path = pathlib.Path(sys.argv[1])
train_domain = sys.argv[2]
eval_domain = sys.argv[3]
metrics_path = pathlib.Path(sys.argv[4])
m = json.loads(metrics_path.read_text())
tm = m.get("test_metrics") or {}
per = tm.get("per_target") or {}
rmse_mean = tm.get("rmse_mean")
row = {
    "train_domain": train_domain,
    "eval_domain": eval_domain,
    "mae_mean": tm.get("mae_mean"),
    "rmse_mean": rmse_mean,
    "mse_mean": (float(rmse_mean) ** 2 if rmse_mean is not None else None),
    "r2_mean": tm.get("r2_mean"),
    "n_rows": tm.get("n_rows"),
}
for k, node in per.items():
    rmse = node.get("rmse")
    row[f"mae__{k}"] = node.get("mae")
    row[f"rmse__{k}"] = rmse
    row[f"mse__{k}"] = (float(rmse) ** 2 if rmse is not None else None)
    row[f"r2__{k}"] = node.get("r2")
header = list(row.keys())
exists = csv_path.exists()
csv_path.parent.mkdir(parents=True, exist_ok=True)
with csv_path.open("a", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=header)
    if not exists:
        w.writeheader()
    w.writerow(row)
PY
}

resolve_target_cols() {
  if [[ "$TARGET_COLS" != "auto_common" ]]; then
    echo "$TARGET_COLS"
    return 0
  fi
  "$PYTHON" - "${DATASET_BY_SITE[@]}" <<'PY'
import sys
import pandas as pd

paths = sys.argv[1:]
common = None
for path in paths:
    cols = set(pd.read_parquet(path).columns)
    flow_cols = {
        str(c) for c in cols
        if str(c).endswith("__mean_tw")
        and str(c) in {
            "permeateflow__mean_tw",
            "deliveryflow__mean_tw",
            "feedflow__mean_tw",
            "concentrateflow__mean_tw",
            "recycleflow__mean_tw",
        }
    }
    common = flow_cols if common is None else (common & flow_cols)
common = sorted(common or [])
if not common:
    raise SystemExit("No common flow __mean_tw target columns found across selected sites")
print(",".join(common))
PY
}

cd "$REPO"
mkdir -p "$MATRIX_ROOT"
SUMMARY_CSV="$MATRIX_ROOT/site_matrix_summary.csv"
rm -f "$SUMMARY_CSV"

IFS=',' read -r -a SITES <<< "$SITE_LIST"

declare -A DATASET_BY_SITE
declare -A SPLIT_BY_SITE
declare -A EMB_BY_SITE

for SITE in "${SITES[@]}"; do
  SITE="$(echo "$SITE" | xargs)"
  [[ -n "$SITE" ]] || continue
  resolve_site_paths "$SITE"
  DATASET_BY_SITE["$SITE"]="$DATASET"
  SPLIT_BY_SITE["$SITE"]="$SPLIT"
  EMB_BY_SITE["$SITE"]="$EMBEDDINGS_NPZ"
done

TARGET_COLS_RESOLVED="$(resolve_target_cols)"
echo "[targets] using $TARGET_COLS_RESOLVED"

for TRAIN_SITE in "${SITES[@]}"; do
  TRAIN_SITE="$(echo "$TRAIN_SITE" | xargs)"
  [[ -n "$TRAIN_SITE" ]] || continue
  TRAIN_OUT="$MATRIX_ROOT/checkpoints/train_${TRAIN_SITE}"
  mkdir -p "$TRAIN_OUT"
  echo "[TRAIN] site=$TRAIN_SITE"
  "$PYTHON" -m python.ml.cli.audio_pretrained_embedding_multitask_train \
    --dataset "${DATASET_BY_SITE[$TRAIN_SITE]}" \
    --split-manifest "${SPLIT_BY_SITE[$TRAIN_SITE]}" \
    --split-col split \
    --dataset-id-col sample_id \
    --split-id-col sample_id \
    --audio-path-col segment_path \
    --embeddings-npz "${EMB_BY_SITE[$TRAIN_SITE]}" \
    --embeddings-key embeddings \
    --out-dir "$TRAIN_OUT" \
    --task-mode multiregression \
    --target-cols "$TARGET_COLS_RESOLVED" \
    --encoder-hidden "$ENCODER_HIDDEN" \
    --latent-dim "$LATENT_DIM" \
    --encoder-dropout "$ENCODER_DROPOUT" \
    --epochs "$EPOCHS" \
    --batch-size "$BATCH_SIZE" \
    --learning-rate "$LEARNING_RATE" \
    --weight-decay "$WEIGHT_DECAY" \
    --eval-every "$EVAL_EVERY" \
    --render-plots "$RENDER_PLOTS" \
    --best-model-metric "$BEST_MODEL_METRIC" \
    --best-model-split "$BEST_MODEL_SPLIT" \
    --aux-plc-pca "$AUX_PLC_PCA" \
    --aux-plc-target-mode "$AUX_PLC_TARGET_MODE" \
    --aux-plc-feature-cols "$AUX_PLC_FEATURE_COLS" \
    --aux-plc-weight "$AUX_PLC_WEIGHT" \
    --pann-pca-weight "$PANN_PCA_WEIGHT"

  BEST_CKPT="$TRAIN_OUT/audio_pretrained_embedding_multitask_best.pt"
  for EVAL_SITE in "${SITES[@]}"; do
    EVAL_SITE="$(echo "$EVAL_SITE" | xargs)"
    [[ -n "$EVAL_SITE" ]] || continue
    EVAL_OUT="$MATRIX_ROOT/evals/train_${TRAIN_SITE}__eval_${EVAL_SITE}"
    mkdir -p "$EVAL_OUT"
    echo "[EVAL] train=$TRAIN_SITE eval=$EVAL_SITE"
    "$PYTHON" -m python.ml.cli.audio_pretrained_embedding_multitask_train \
      --dataset "${DATASET_BY_SITE[$EVAL_SITE]}" \
      --split-manifest "${SPLIT_BY_SITE[$EVAL_SITE]}" \
      --split-col split \
      --dataset-id-col sample_id \
      --split-id-col sample_id \
      --audio-path-col segment_path \
      --embeddings-npz "${EMB_BY_SITE[$EVAL_SITE]}" \
      --embeddings-key embeddings \
      --out-dir "$EVAL_OUT" \
      --task-mode multiregression \
      --target-cols "$TARGET_COLS_RESOLVED" \
      --encoder-hidden "$ENCODER_HIDDEN" \
      --latent-dim "$LATENT_DIM" \
      --encoder-dropout "$ENCODER_DROPOUT" \
      --epochs 0 \
      --batch-size "$BATCH_SIZE" \
      --learning-rate "$LEARNING_RATE" \
      --weight-decay "$WEIGHT_DECAY" \
      --eval-every 1 \
      --render-plots "$RENDER_PLOTS" \
      --best-model-metric "$BEST_MODEL_METRIC" \
      --best-model-split "$BEST_MODEL_SPLIT" \
      --aux-plc-pca "$AUX_PLC_PCA" \
      --aux-plc-target-mode "$AUX_PLC_TARGET_MODE" \
      --aux-plc-feature-cols "$AUX_PLC_FEATURE_COLS" \
      --aux-plc-weight "$AUX_PLC_WEIGHT" \
      --pann-pca-weight "$PANN_PCA_WEIGHT" \
      --init-model "$BEST_CKPT"
    append_summary "$SUMMARY_CSV" "$TRAIN_SITE" "$EVAL_SITE" "$EVAL_OUT/audio_pretrained_embedding_multitask_metrics.json"
  done
done

if [[ "$INCLUDE_POOLED" == "yes" ]]; then
  POOLED_OUT="$MATRIX_ROOT/checkpoints/train_all_sites"
  mkdir -p "$POOLED_OUT"
  DATASET_ARGS=()
  SPLIT_ARGS=()
  EMB_ARGS=()
  for SITE in "${SITES[@]}"; do
    SITE="$(echo "$SITE" | xargs)"
    [[ -n "$SITE" ]] || continue
    DATASET_ARGS+=("${DATASET_BY_SITE[$SITE]}")
    SPLIT_ARGS+=("${SPLIT_BY_SITE[$SITE]}")
    EMB_ARGS+=("${EMB_BY_SITE[$SITE]}")
  done
  echo "[TRAIN] site=all_sites"
  "$PYTHON" -m python.ml.cli.audio_pretrained_embedding_multitask_train \
    --dataset "${DATASET_ARGS[@]}" \
    --split-manifest "${SPLIT_ARGS[@]}" \
    --split-col split \
    --dataset-id-col sample_id \
    --split-id-col sample_id \
    --audio-path-col segment_path \
    --embeddings-npz "${EMB_ARGS[@]}" \
    --embeddings-key embeddings \
    --out-dir "$POOLED_OUT" \
    --task-mode multiregression \
    --target-cols "$TARGET_COLS_RESOLVED" \
    --encoder-hidden "$ENCODER_HIDDEN" \
    --latent-dim "$LATENT_DIM" \
    --encoder-dropout "$ENCODER_DROPOUT" \
    --epochs "$EPOCHS" \
    --batch-size "$BATCH_SIZE" \
    --learning-rate "$LEARNING_RATE" \
    --weight-decay "$WEIGHT_DECAY" \
    --eval-every "$EVAL_EVERY" \
    --render-plots "$RENDER_PLOTS" \
    --best-model-metric "$BEST_MODEL_METRIC" \
    --best-model-split "$BEST_MODEL_SPLIT" \
    --aux-plc-pca "$AUX_PLC_PCA" \
    --aux-plc-target-mode "$AUX_PLC_TARGET_MODE" \
    --aux-plc-feature-cols "$AUX_PLC_FEATURE_COLS" \
    --aux-plc-weight "$AUX_PLC_WEIGHT" \
    --pann-pca-weight "$PANN_PCA_WEIGHT"

  BEST_CKPT="$POOLED_OUT/audio_pretrained_embedding_multitask_best.pt"
  for EVAL_SITE in "${SITES[@]}"; do
    EVAL_SITE="$(echo "$EVAL_SITE" | xargs)"
    [[ -n "$EVAL_SITE" ]] || continue
    EVAL_OUT="$MATRIX_ROOT/evals/train_all_sites__eval_${EVAL_SITE}"
    mkdir -p "$EVAL_OUT"
    echo "[EVAL] train=all_sites eval=$EVAL_SITE"
    "$PYTHON" -m python.ml.cli.audio_pretrained_embedding_multitask_train \
      --dataset "${DATASET_BY_SITE[$EVAL_SITE]}" \
      --split-manifest "${SPLIT_BY_SITE[$EVAL_SITE]}" \
      --split-col split \
      --dataset-id-col sample_id \
      --split-id-col sample_id \
      --audio-path-col segment_path \
      --embeddings-npz "${EMB_BY_SITE[$EVAL_SITE]}" \
      --embeddings-key embeddings \
      --out-dir "$EVAL_OUT" \
      --task-mode multiregression \
      --target-cols "$TARGET_COLS_RESOLVED" \
      --encoder-hidden "$ENCODER_HIDDEN" \
      --latent-dim "$LATENT_DIM" \
      --encoder-dropout "$ENCODER_DROPOUT" \
      --epochs 0 \
      --batch-size "$BATCH_SIZE" \
      --learning-rate "$LEARNING_RATE" \
      --weight-decay "$WEIGHT_DECAY" \
      --eval-every 1 \
      --render-plots "$RENDER_PLOTS" \
      --best-model-metric "$BEST_MODEL_METRIC" \
      --best-model-split "$BEST_MODEL_SPLIT" \
      --aux-plc-pca "$AUX_PLC_PCA" \
      --aux-plc-target-mode "$AUX_PLC_TARGET_MODE" \
      --aux-plc-feature-cols "$AUX_PLC_FEATURE_COLS" \
      --aux-plc-weight "$AUX_PLC_WEIGHT" \
      --pann-pca-weight "$PANN_PCA_WEIGHT" \
      --init-model "$BEST_CKPT"
    append_summary "$SUMMARY_CSV" "all_sites" "$EVAL_SITE" "$EVAL_OUT/audio_pretrained_embedding_multitask_metrics.json"
  done
fi

echo "[OK] summary -> $SUMMARY_CSV"
