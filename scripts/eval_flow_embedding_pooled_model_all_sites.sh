#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

WINDOW_S="${WINDOW_S:-10}"
SITE_LIST="${SITE_LIST:-bluerock,pryorfarm,santateresa}"
MATRIX_ROOT="${MATRIX_ROOT:-/mnt/d/datasets/svwatergo/domain_matrix/flow_site_aux0_ep100_common}"
CHECKPOINT="${CHECKPOINT:-$MATRIX_ROOT/checkpoints/train_all_sites/audio_pretrained_embedding_multitask_best.pt}"
OUT_ROOT="${OUT_ROOT:-$MATRIX_ROOT/evals_pooled_all_sites}"
SUMMARY_CSV="${SUMMARY_CSV:-$OUT_ROOT/pooled_model_eval_summary.csv}"
USE_EXISTING_SPLITS="${USE_EXISTING_SPLITS:-yes}" # yes|no

TARGET_COLS="${TARGET_COLS:-permeateflow__mean_tw,deliveryflow__mean_tw,feedflow__mean_tw,inletflow__mean_tw,concentrateflow__mean_tw,recycleflow__mean_tw}"
ENCODER_HIDDEN="${ENCODER_HIDDEN:-1024,512,256}"
LATENT_DIM="${LATENT_DIM:-64}"
ENCODER_DROPOUT="${ENCODER_DROPOUT:-0.2}"
BATCH_SIZE="${BATCH_SIZE:-256}"
LEARNING_RATE="${LEARNING_RATE:-3e-4}"
WEIGHT_DECAY="${WEIGHT_DECAY:-1e-4}"
BEST_MODEL_METRIC="${BEST_MODEL_METRIC:-main_task_metric}"
BEST_MODEL_SPLIT="${BEST_MODEL_SPLIT:-val}"
AUX_PLC_PCA="${AUX_PLC_PCA:-yes}"
AUX_PLC_TARGET_MODE="${AUX_PLC_TARGET_MODE:-raw}"
AUX_PLC_FEATURE_COLS="${AUX_PLC_FEATURE_COLS:-plc_pca1,plc_pca2,plc_pca3,plc_pca4,plc_pca5,plc_pca6,plc_pca7,plc_pca8}"
AUX_PLC_WEIGHT="${AUX_PLC_WEIGHT:-0.0}"
PANN_PCA_WEIGHT="${PANN_PCA_WEIGHT:-0.0}"

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
  local eval_domain="$2"
  local metrics_path="$3"
  "$PYTHON" - "$csv_path" "$eval_domain" "$metrics_path" <<'PY'
import csv
import json
import pathlib
import sys

csv_path = pathlib.Path(sys.argv[1])
eval_domain = sys.argv[2]
metrics_path = pathlib.Path(sys.argv[3])
obj = json.loads(metrics_path.read_text())
tm = obj.get("test_metrics") or {}
per = tm.get("per_target") or {}
rmse_mean = tm.get("rmse_mean")
row = {
    "train_domain": "all_sites",
    "eval_domain": eval_domain,
    "mae_mean": tm.get("mae_mean"),
    "rmse_mean": rmse_mean,
    "mse_mean": (float(rmse_mean) ** 2 if rmse_mean is not None else None),
    "r2_mean": tm.get("r2_mean"),
    "n_rows": tm.get("n_rows"),
}
for target, node in per.items():
    rmse = node.get("rmse")
    row[f"mae__{target}"] = node.get("mae")
    row[f"rmse__{target}"] = rmse
    row[f"mse__{target}"] = (float(rmse) ** 2 if rmse is not None else None)
    row[f"r2__{target}"] = node.get("r2")

existing_rows = []
fieldnames = list(row.keys())
if csv_path.exists():
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        existing_rows = list(csv.DictReader(f))
    for prev in existing_rows:
        for k in prev.keys():
            if k not in fieldnames:
                fieldnames.append(k)
for k in row.keys():
    if k not in fieldnames:
        fieldnames.append(k)

csv_path.parent.mkdir(parents=True, exist_ok=True)
with csv_path.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for prev in existing_rows:
        if prev.get("eval_domain") == eval_domain and prev.get("train_domain") == "all_sites":
            continue
        w.writerow(prev)
    w.writerow(row)
PY
}

maybe_extract_checkpoint_config() {
  local ckpt="$1"
  local tmp_env="$2"
  if [[ ! -f "$ckpt" ]]; then
    echo "[WARN] checkpoint not found for config extraction: $ckpt" >&2
    return 0
  fi
  "$PYTHON" - "$ckpt" "$tmp_env" <<'PY'
import pathlib
import sys

ckpt = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2])
try:
    import torch  # type: ignore
except Exception:
    raise SystemExit(0)

obj = torch.load(str(ckpt), map_location="cpu")
if not isinstance(obj, dict):
    raise SystemExit(0)
hidden = obj.get("hidden")
z_dim = obj.get("z_dim")
target_cols = obj.get("target_cols")
lines = []
if isinstance(hidden, (list, tuple)) and hidden:
    lines.append(f'ENCODER_HIDDEN="{",".join(str(int(x)) for x in hidden)}"')
if isinstance(z_dim, int) and z_dim > 0:
    lines.append(f'LATENT_DIM="{int(z_dim)}"')
if isinstance(target_cols, (list, tuple)) and target_cols:
    lines.append(f'TARGET_COLS="{",".join(str(x) for x in target_cols)}"')
out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
PY
}

resolve_target_cols() {
  "$PYTHON" - "$TARGET_COLS" "${all_datasets[@]}" <<'PY'
import sys
import pandas as pd

requested_raw = str(sys.argv[1]).strip()
paths = sys.argv[2:]
allowed = [
    "permeateflow__mean_tw",
    "deliveryflow__mean_tw",
    "feedflow__mean_tw",
    "inletflow__mean_tw",
    "concentrateflow__mean_tw",
    "recycleflow__mean_tw",
]
if requested_raw == "auto_common":
    requested = allowed
else:
    requested = [x.strip() for x in requested_raw.split(",") if x.strip()]

common = None
for path in paths:
    cols = set(pd.read_parquet(path).columns)
    cur = {c for c in allowed if c in cols}
    common = cur if common is None else (common & cur)
common = sorted(common or [])
resolved = [c for c in requested if c in common]
dropped = [c for c in requested if c not in common]
if not resolved:
    raise SystemExit("No common requested flow __mean_tw target columns found across selected sites")
print(",".join(resolved))
if dropped:
    print("[targets] dropped missing/non-common: " + ",".join(dropped), file=sys.stderr)
PY
}

build_eval_manifest() {
  local out_path="$1"
  shift
  "$PYTHON" - "$out_path" "$@" <<'PY'
import pathlib
import sys
import pandas as pd

out_path = pathlib.Path(sys.argv[1])
dataset_paths = sys.argv[2:]
parts = []
for dataset_path in dataset_paths:
    df = pd.read_parquet(dataset_path, columns=["sample_id"])
    split = ["test"] * len(df)
    if len(split) >= 1:
        split[0] = "train"
    if len(split) >= 2:
        split[1] = "train"
    parts.append(pd.DataFrame({"sample_id": df["sample_id"].astype(str), "split": split}))
out_df = pd.concat(parts, axis=0, ignore_index=True)
out_path.parent.mkdir(parents=True, exist_ok=True)
out_df.to_parquet(out_path, index=False)
print(out_path)
PY
}

run_eval() {
  local eval_label="$1"
  local out_dir="$2"
  shift 2
  local -a dataset_paths=()
  local -a split_paths=()
  local -a emb_paths=()

  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --dataset)
        dataset_paths+=("$2")
        shift 2
        ;;
      --split)
        split_paths+=("$2")
        shift 2
        ;;
      --emb)
        emb_paths+=("$2")
        shift 2
        ;;
      *)
        echo "unknown run_eval arg: $1" >&2
        exit 2
        ;;
    esac
  done

  mkdir -p "$out_dir"
  local -a effective_splits=()
  if [[ "$USE_EXISTING_SPLITS" == "yes" ]]; then
    effective_splits=("${split_paths[@]}")
  else
    local manifest_path="$OUT_ROOT/manifests/${eval_label}_eval_all_rows.parquet"
    build_eval_manifest "$manifest_path" "${dataset_paths[@]}" >/dev/null
    effective_splits=("$manifest_path")
  fi

  echo "[EVAL] pooled_flow_model -> $eval_label"
  "$PYTHON" -m python.ml.cli.audio_pretrained_embedding_multitask_train \
    --dataset "${dataset_paths[@]}" \
    --split-manifest "${effective_splits[@]}" \
    --split-col split \
    --dataset-id-col sample_id \
    --split-id-col sample_id \
    --audio-path-col segment_path \
    --embeddings-npz "${emb_paths[@]}" \
    --embeddings-key embeddings \
    --out-dir "$out_dir" \
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
    --render-plots no \
    --best-model-metric "$BEST_MODEL_METRIC" \
    --best-model-split "$BEST_MODEL_SPLIT" \
    --aux-plc-pca "$AUX_PLC_PCA" \
    --aux-plc-target-mode "$AUX_PLC_TARGET_MODE" \
    --aux-plc-feature-cols "$AUX_PLC_FEATURE_COLS" \
    --aux-plc-weight "$AUX_PLC_WEIGHT" \
    --pann-pca-weight "$PANN_PCA_WEIGHT" \
    --init-model "$CHECKPOINT"
  append_summary "$SUMMARY_CSV" "$eval_label" "$out_dir/audio_pretrained_embedding_multitask_metrics.json"
}

cd "$REPO"
mkdir -p "$OUT_ROOT"
rm -f "$SUMMARY_CSV"

tmp_env="$(mktemp)"
maybe_extract_checkpoint_config "$CHECKPOINT" "$tmp_env"
# shellcheck disable=SC1090
source "$tmp_env"
rm -f "$tmp_env"

IFS=',' read -r -a SITES <<< "$SITE_LIST"
declare -A DATASET_BY_SITE
declare -A SPLIT_BY_SITE
declare -A EMB_BY_SITE

all_datasets=()
all_eval_args=()
for SITE in "${SITES[@]}"; do
  SITE="$(echo "$SITE" | xargs)"
  [[ -n "$SITE" ]] || continue
  resolve_site_paths "$SITE"
  DATASET_BY_SITE["$SITE"]="$DATASET"
  SPLIT_BY_SITE["$SITE"]="$SPLIT"
  EMB_BY_SITE["$SITE"]="$EMBEDDINGS_NPZ"
  all_datasets+=("$DATASET")
  all_eval_args+=(--dataset "$DATASET")
  all_eval_args+=(--split "$SPLIT")
  all_eval_args+=(--emb "$EMBEDDINGS_NPZ")
done

TARGET_COLS_RESOLVED="$(resolve_target_cols)"
echo "[targets] using $TARGET_COLS_RESOLVED"

for SITE in "${SITES[@]}"; do
  SITE="$(echo "$SITE" | xargs)"
  [[ -n "$SITE" ]] || continue
  run_eval \
    "$SITE" \
    "$OUT_ROOT/train_all_sites__eval_${SITE}" \
    --dataset "${DATASET_BY_SITE[$SITE]}" \
    --split "${SPLIT_BY_SITE[$SITE]}" \
    --emb "${EMB_BY_SITE[$SITE]}"
done

run_eval \
  "all_sites" \
  "$OUT_ROOT/train_all_sites__eval_all_sites" \
  "${all_eval_args[@]}"

echo "[OK] pooled flow eval summary -> $SUMMARY_CSV"
echo "[OK] pooled flow eval outputs -> $OUT_ROOT"
