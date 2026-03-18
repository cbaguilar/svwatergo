#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

WINDOW_S="${WINDOW_S:-10}"
SITE_LIST="${SITE_LIST:-bluerock,pryorfarm,santateresa}"
MATRIX_ROOT="${MATRIX_ROOT:-/mnt/d/datasets/svwatergo/domain_matrix/source}"
TARGET_COLS="${TARGET_COLS:-ropumprun_duty_target,wellpumprun_duty_target,feedpumprun_duty_target,deliveryrun_duty_target,flushrun_duty_target}"
POSITIVE_THRESHOLD="${POSITIVE_THRESHOLD:-0.5}"
ENCODER_HIDDEN="${ENCODER_HIDDEN:-1024,512,256}"
LATENT_DIM="${LATENT_DIM:-64}"
ENCODER_DROPOUT="${ENCODER_DROPOUT:-0.2}"
EPOCHS="${EPOCHS:-10}"
BATCH_SIZE="${BATCH_SIZE:-256}"
LEARNING_RATE="${LEARNING_RATE:-3e-4}"
WEIGHT_DECAY="${WEIGHT_DECAY:-1e-4}"
EVAL_EVERY="${EVAL_EVERY:-1}"
BEST_MODEL_METRIC="${BEST_MODEL_METRIC:-macro_f1}"
BEST_MODEL_SPLIT="${BEST_MODEL_SPLIT:-val}"
MULTILABEL_POS_WEIGHT="${MULTILABEL_POS_WEIGHT:-yes}"
AUX_PLC_PCA="${AUX_PLC_PCA:-yes}"
AUX_PLC_TARGET_MODE="${AUX_PLC_TARGET_MODE:-raw}"
AUX_PLC_FEATURE_COLS="${AUX_PLC_FEATURE_COLS:-plc_pca1,plc_pca2,plc_pca3,plc_pca4,plc_pca5,plc_pca6,plc_pca7,plc_pca8}"
AUX_PLC_WEIGHT="${AUX_PLC_WEIGHT:-0.1}"
PANN_PCA_WEIGHT="${PANN_PCA_WEIGHT:-0.0}"
RENDER_PLOTS="${RENDER_PLOTS:-yes}"
MIN_TRAIN_ROWS="${MIN_TRAIN_ROWS:-1}"
MIN_TEST_ROWS="${MIN_TEST_ROWS:-1}"

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
import csv, json, pathlib, sys
csv_path = pathlib.Path(sys.argv[1])
train_domain = sys.argv[2]
eval_domain = sys.argv[3]
metrics_path = pathlib.Path(sys.argv[4])
m = json.loads(metrics_path.read_text())
tm = m.get("test_metrics") or {}
per = tm.get("per_target") or {}
row = {
    "train_domain": train_domain,
    "eval_domain": eval_domain,
    "macro_f1": tm.get("macro_f1"),
    "exact_match": tm.get("exact_match"),
    "n_rows": tm.get("n_rows"),
}
for k, node in per.items():
    row[f"f1__{k}"] = node.get("f1")
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

append_skip_summary() {
  local csv_path="$1"
  local train_domain="$2"
  local eval_domain="$3"
  local status="$4"
  local message="$5"
  local train_rows="$6"
  local test_rows="$7"
  local val_rows="$8"
  python3 - "$csv_path" "$train_domain" "$eval_domain" "$status" "$message" "$train_rows" "$test_rows" "$val_rows" <<'PY'
import csv, pathlib, sys
csv_path = pathlib.Path(sys.argv[1])
row = {
    "train_domain": sys.argv[2],
    "eval_domain": sys.argv[3],
    "status": sys.argv[4],
    "message": sys.argv[5],
    "macro_f1": None,
    "exact_match": None,
    "n_rows": None,
    "train_rows": int(sys.argv[6]),
    "test_rows": int(sys.argv[7]),
    "val_rows": int(sys.argv[8]),
}
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

domain_split_counts() {
  local dataset="$1"
  local split_manifest="$2"
  local source="$3"
  "$PYTHON" - "$dataset" "$split_manifest" "$source" <<'PY'
import pandas as pd, sys
dataset, split_manifest, source = sys.argv[1:4]
df = pd.read_parquet(dataset, columns=["sample_id", "audio_source"])
sm = pd.read_parquet(split_manifest, columns=["sample_id", "split"])
df = df[df["audio_source"].astype(str) == str(source)].copy()
merged = df.merge(sm, on="sample_id", how="left")
counts = merged["split"].astype(str).value_counts(dropna=False).to_dict()
train = int(counts.get("train", 0))
test = int(counts.get("test", 0))
val = int(counts.get("val", 0))
print(f"{train}|{test}|{val}")
PY
}

cd "$REPO"
mkdir -p "$MATRIX_ROOT"
SUMMARY_CSV="$MATRIX_ROOT/source_matrix_summary.csv"
rm -f "$SUMMARY_CSV"

IFS=',' read -r -a SITES <<< "$SITE_LIST"

declare -A DATASET_BY_SITE
declare -A SPLIT_BY_SITE
declare -A EMB_BY_SITE
declare -a DOMAIN_SPECS

for SITE in "${SITES[@]}"; do
  SITE="$(echo "$SITE" | xargs)"
  [[ -n "$SITE" ]] || continue
  resolve_site_paths "$SITE"
  DATASET_BY_SITE["$SITE"]="$DATASET"
  SPLIT_BY_SITE["$SITE"]="$SPLIT"
  EMB_BY_SITE["$SITE"]="$EMBEDDINGS_NPZ"
  while IFS= read -r SRC; do
    [[ -n "$SRC" ]] || continue
    COUNTS="$(domain_split_counts "$DATASET" "$SPLIT" "$SRC")"
    IFS='|' read -r TRAIN_ROWS TEST_ROWS VAL_ROWS <<< "$COUNTS"
    DOMAIN_SPECS+=("${SITE}|${SRC}|${DATASET}|${SPLIT}|${EMBEDDINGS_NPZ}|${TRAIN_ROWS}|${TEST_ROWS}|${VAL_ROWS}")
  done < <("$PYTHON" - "$DATASET" <<'PY'
import pandas as pd, sys
df = pd.read_parquet(sys.argv[1], columns=["audio_source"])
vals = sorted(set(str(x).strip() for x in df["audio_source"].dropna().tolist() if str(x).strip()))
for v in vals:
    print(v)
PY
  )
done

for TRAIN_SPEC in "${DOMAIN_SPECS[@]}"; do
  IFS='|' read -r TRAIN_SITE TRAIN_SOURCE TRAIN_DATASET TRAIN_SPLIT TRAIN_EMB TRAIN_ROWS TEST_ROWS VAL_ROWS <<< "$TRAIN_SPEC"
  TRAIN_LABEL="${TRAIN_SITE}__${TRAIN_SOURCE}"
  if (( TRAIN_ROWS < MIN_TRAIN_ROWS || TEST_ROWS < MIN_TEST_ROWS )); then
    echo "[SKIP TRAIN] domain=$TRAIN_LABEL train_rows=$TRAIN_ROWS test_rows=$TEST_ROWS val_rows=$VAL_ROWS"
    for EVAL_SPEC in "${DOMAIN_SPECS[@]}"; do
      IFS='|' read -r EVAL_SITE EVAL_SOURCE _ _ _ ETRAIN_ROWS ETEST_ROWS EVAL_ROWS <<< "$EVAL_SPEC"
      EVAL_LABEL="${EVAL_SITE}__${EVAL_SOURCE}"
      append_skip_summary "$SUMMARY_CSV" "$TRAIN_LABEL" "$EVAL_LABEL" "skipped_train" "insufficient train/test rows for training domain" "$TRAIN_ROWS" "$TEST_ROWS" "$VAL_ROWS"
    done
    continue
  fi
  TRAIN_OUT="$MATRIX_ROOT/checkpoints/train_${TRAIN_LABEL}"
  mkdir -p "$TRAIN_OUT"
  echo "[TRAIN] domain=$TRAIN_LABEL"
  "$PYTHON" -m python.ml.cli.audio_pretrained_embedding_multitask_train \
    --dataset "$TRAIN_DATASET" \
    --split-manifest "$TRAIN_SPLIT" \
    --split-col split \
    --dataset-id-col sample_id \
    --split-id-col sample_id \
    --audio-path-col segment_path \
    --embeddings-npz "$TRAIN_EMB" \
    --embeddings-key embeddings \
    --source-filter-col audio_source \
    --source-filter-values "$TRAIN_SOURCE" \
    --out-dir "$TRAIN_OUT" \
    --task-mode multilabel \
    --target-cols "$TARGET_COLS" \
    --positive-threshold "$POSITIVE_THRESHOLD" \
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
    --multilabel-pos-weight "$MULTILABEL_POS_WEIGHT" \
    --aux-plc-pca "$AUX_PLC_PCA" \
    --aux-plc-target-mode "$AUX_PLC_TARGET_MODE" \
    --aux-plc-feature-cols "$AUX_PLC_FEATURE_COLS" \
    --aux-plc-weight "$AUX_PLC_WEIGHT" \
    --pann-pca-weight "$PANN_PCA_WEIGHT"

  BEST_CKPT="$TRAIN_OUT/audio_pretrained_embedding_multitask_best.pt"
  for EVAL_SPEC in "${DOMAIN_SPECS[@]}"; do
    IFS='|' read -r EVAL_SITE EVAL_SOURCE EVAL_DATASET EVAL_SPLIT EVAL_EMB ETRAIN_ROWS ETEST_ROWS EVAL_ROWS <<< "$EVAL_SPEC"
    EVAL_LABEL="${EVAL_SITE}__${EVAL_SOURCE}"
    if (( ETRAIN_ROWS < MIN_TRAIN_ROWS || ETEST_ROWS < MIN_TEST_ROWS )); then
      echo "[SKIP EVAL] train=$TRAIN_LABEL eval=$EVAL_LABEL train_rows=$ETRAIN_ROWS test_rows=$ETEST_ROWS val_rows=$EVAL_ROWS"
      append_skip_summary "$SUMMARY_CSV" "$TRAIN_LABEL" "$EVAL_LABEL" "skipped_eval" "insufficient train/test rows for eval domain" "$ETRAIN_ROWS" "$ETEST_ROWS" "$EVAL_ROWS"
      continue
    fi
    EVAL_OUT="$MATRIX_ROOT/evals/train_${TRAIN_LABEL}__eval_${EVAL_LABEL}"
    mkdir -p "$EVAL_OUT"
    echo "[EVAL] train=$TRAIN_LABEL eval=$EVAL_LABEL"
    "$PYTHON" -m python.ml.cli.audio_pretrained_embedding_multitask_train \
      --dataset "$EVAL_DATASET" \
      --split-manifest "$EVAL_SPLIT" \
      --split-col split \
      --dataset-id-col sample_id \
      --split-id-col sample_id \
      --audio-path-col segment_path \
      --embeddings-npz "$EVAL_EMB" \
      --embeddings-key embeddings \
      --source-filter-col audio_source \
      --source-filter-values "$EVAL_SOURCE" \
      --out-dir "$EVAL_OUT" \
      --task-mode multilabel \
      --target-cols "$TARGET_COLS" \
      --positive-threshold "$POSITIVE_THRESHOLD" \
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
      --multilabel-pos-weight "$MULTILABEL_POS_WEIGHT" \
      --aux-plc-pca "$AUX_PLC_PCA" \
      --aux-plc-target-mode "$AUX_PLC_TARGET_MODE" \
      --aux-plc-feature-cols "$AUX_PLC_FEATURE_COLS" \
      --aux-plc-weight "$AUX_PLC_WEIGHT" \
      --pann-pca-weight "$PANN_PCA_WEIGHT" \
      --init-model "$BEST_CKPT"
    append_summary "$SUMMARY_CSV" "$TRAIN_LABEL" "$EVAL_LABEL" "$EVAL_OUT/audio_pretrained_embedding_multitask_metrics.json"
  done
done

echo "[OK] summary -> $SUMMARY_CSV"
