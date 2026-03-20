#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

WINDOW_S="${WINDOW_S:-10}"
SITE_LIST="${SITE_LIST:-bluerock,pryorfarm,santateresa}"
MATRIX_ROOT="${MATRIX_ROOT:-/mnt/d/datasets/svwatergo/domain_matrix/source_svm}"
TARGET_COLS="${TARGET_COLS:-ropumprun_duty_target,wellpumprun_duty_target,feedpumprun_duty_target,deliveryrun_duty_target,flushrun_duty_target}"
POSITIVE_THRESHOLD="${POSITIVE_THRESHOLD:-0.5}"
N_COMPONENTS="${N_COMPONENTS:-8}"
SAMPLE_RATE="${SAMPLE_RATE:-16000}"
TARGET_SECONDS="${TARGET_SECONDS:-10}"
SVM_CLASS_WEIGHT="${SVM_CLASS_WEIGHT:-balanced}"
SVM_BACKEND="${SVM_BACKEND:-auto}"

resolve_site_paths() {
  local site="$1"
  case "$site" in
    bluerock)
      DATASET="/mnt/d/datasets/svwatergo/derived_5actsplit/dataset=audio_actuation_dataset/site=bluerock/window_s=${WINDOW_S}/samples.parquet"
      SPLIT="/mnt/d/datasets/svwatergo/derived_5actsplit/dataset=audio_actuation_dataset/site=bluerock/window_s=${WINDOW_S}/split_manifest.parquet"
      ;;
    pryorfarm)
      DATASET="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm_5actsplit/dataset=audio_actuation_dataset/site=pryorfarm/window_s=${WINDOW_S}/samples.parquet"
      SPLIT="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm_5actsplit/dataset=audio_actuation_dataset/site=pryorfarm/window_s=${WINDOW_S}/split_manifest.parquet"
      ;;
    santateresa)
      DATASET="/mnt/d/datasets/svwatergo/derived_wyze_santateresa_5actsplit/dataset=audio_actuation_dataset/site=santateresa/window_s=${WINDOW_S}/samples.parquet"
      SPLIT="/mnt/d/datasets/svwatergo/derived_wyze_santateresa_5actsplit/dataset=audio_actuation_dataset/site=santateresa/window_s=${WINDOW_S}/split_manifest.parquet"
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
  local target_cols="$5"
  python3 - "$csv_path" "$train_domain" "$eval_domain" "$metrics_path" "$target_cols" <<'PY'
import csv, json, pathlib, sys
csv_path = pathlib.Path(sys.argv[1])
train_domain = sys.argv[2]
eval_domain = sys.argv[3]
metrics_path = pathlib.Path(sys.argv[4])
target_cols = [c.strip() for c in sys.argv[5].split(",") if c.strip()]
m = json.loads(metrics_path.read_text())
tm = m.get("test_metrics") or {}
per = tm.get("per_label") or {}
row = {
    "train_domain": train_domain,
    "eval_domain": eval_domain,
    "status": "ok",
    "message": "",
    "macro_f1": tm.get("macro_f1"),
    "exact_match": tm.get("exact_match_accuracy"),
    "n_rows": tm.get("n_rows"),
}
for k in target_cols:
    node = per.get(k) or {}
    row[f"f1__{k}"] = node.get("f1")
    row[f"precision__{k}"] = node.get("precision")
    row[f"recall__{k}"] = node.get("recall")
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

append_status_summary() {
  local csv_path="$1"
  local train_domain="$2"
  local eval_domain="$3"
  local status="$4"
  local message="$5"
  local target_cols="$6"
  python3 - "$csv_path" "$train_domain" "$eval_domain" "$status" "$message" "$target_cols" <<'PY'
import csv, pathlib, sys
csv_path = pathlib.Path(sys.argv[1])
train_domain = sys.argv[2]
eval_domain = sys.argv[3]
status = sys.argv[4]
message = sys.argv[5]
target_cols = [c.strip() for c in sys.argv[6].split(",") if c.strip()]
row = {
    "train_domain": train_domain,
    "eval_domain": eval_domain,
    "status": status,
    "message": message,
    "macro_f1": None,
    "exact_match": None,
    "n_rows": None,
}
for k in target_cols:
    row[f"f1__{k}"] = None
    row[f"precision__{k}"] = None
    row[f"recall__{k}"] = None
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

prepare_source_dataset() {
  local src_dataset="$1"
  local source_value="$2"
  local out_dataset="$3"
  python3 - "$src_dataset" "$source_value" "$out_dataset" <<'PY'
import sys
from pathlib import Path
import pandas as pd

src_dataset = Path(sys.argv[1])
source_value = str(sys.argv[2])
out_dataset = Path(sys.argv[3])

df = pd.read_parquet(src_dataset)
if "audio_source" not in df.columns:
    raise SystemExit("dataset missing audio_source column")
sub = df[df["audio_source"].astype(str) == source_value].copy()
if sub.empty:
    raise SystemExit(f"no rows found for source={source_value}")
out_dataset.parent.mkdir(parents=True, exist_ok=True)
sub.to_parquet(out_dataset, index=False)
print(out_dataset)
PY
}

eval_svm_models() {
  local model_dir="$1"
  local dataset_path="$2"
  local split_path="$3"
  local source_value="$4"
  local out_metrics="$5"
  local target_cols="$6"
  local pos_threshold="$7"
  python3 - "$model_dir" "$dataset_path" "$split_path" "$source_value" "$out_metrics" "$target_cols" "$pos_threshold" <<'PY'
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from python.ml.train.audio_pca_svm import _attach_split_labels, _normalize_split_value, load_audio_pca_svm_bundle, load_training_mels
from python.ml.train.audio_tiny_cnn import _exact_match_acc, _metrics_multilabel

model_dir = Path(sys.argv[1])
dataset_path = Path(sys.argv[2])
split_path = Path(sys.argv[3])
source_value = str(sys.argv[4])
out_metrics = Path(sys.argv[5])
target_cols = [c.strip() for c in sys.argv[6].split(",") if c.strip()]
positive_threshold = float(sys.argv[7])

df = pd.read_parquet(dataset_path)
if "audio_source" not in df.columns:
    raise SystemExit("dataset missing audio_source column")
df = df[df["audio_source"].astype(str) == source_value].reset_index(drop=True)
if df.empty:
    raise SystemExit(f"no rows found for source={source_value}")

Y = np.stack(
    [np.clip(pd.to_numeric(df[c], errors="coerce").fillna(0.0).to_numpy(dtype=np.float32), 0.0, 1.0) for c in target_cols],
    axis=1,
)
split_df = pd.read_parquet(split_path) if str(split_path) else None
df2, split_ser, _ = _attach_split_labels(
    df,
    split_manifest_df=split_df,
    split_col="split",
    dataset_id_col="sample_id",
    split_manifest_id_col="sample_id",
)
if split_ser is None:
    raise SystemExit("split manifest attach failed")
split_norm = split_ser.map(_normalize_split_value).astype("string")
keep_mask = split_norm.isin(["train", "test", "val"])
df2 = df2.loc[keep_mask].reset_index(drop=True)
Y = Y[np.asarray(keep_mask.to_numpy(), dtype=bool)]
split_norm = split_norm.loc[keep_mask].reset_index(drop=True)
idx_test = np.arange(len(df2), dtype=np.int64)[split_norm.to_numpy() == "test"]
if len(idx_test) <= 0:
    raise SystemExit("no test rows found in eval dataset")

first_bundle = load_audio_pca_svm_bundle(model_dir.joinpath(f"{target_cols[0]}/audio_pca_svm_model.joblib"))
mel_cfg = first_bundle.get("mel_config") or {}
X_mel = load_training_mels(df2, mel_config=mel_cfg, audio_path_col="segment_path").astype("float32", copy=False)
X = X_mel.reshape(X_mel.shape[0], -1).astype("float32", copy=False)

scores = []
preds = []
for target in target_cols:
    bundle = load_audio_pca_svm_bundle(model_dir.joinpath(f"{target}/audio_pca_svm_model.joblib"))
    x = X
    scaler = bundle.get("input_scaler")
    if scaler is not None:
        x = scaler.transform(x)
    z = bundle["pca"].transform(x)
    svm = bundle["svm"]
    if hasattr(svm, "predict_proba"):
        s = svm.predict_proba(z)[:, 1]
    else:
        s = svm.predict(z).astype(np.float64)
    p = (np.asarray(s) >= 0.5).astype(np.int64)
    scores.append(np.asarray(s, dtype=np.float64))
    preds.append(np.asarray(p, dtype=np.int64))

Y_score = np.stack(scores, axis=1)
Y_pred = np.stack(preds, axis=1)
Y_true_bin = (Y >= positive_threshold).astype(np.int64)

test_metrics = _metrics_multilabel(
    y_true=np.asarray(Y_true_bin[idx_test], dtype=np.int64),
    y_pred=np.asarray(Y_pred[idx_test], dtype=np.int64),
    y_score=np.asarray(Y_score[idx_test], dtype=np.float64),
    class_names=target_cols,
)
test_metrics["n_rows"] = int(len(idx_test))
test_metrics["exact_match_accuracy"] = float(_exact_match_acc(Y_true_bin[idx_test], Y_pred[idx_test], task="multilabel"))

payload = {
    "task": "multilabel_from_binary_svms",
    "source_value": source_value,
    "target_cols": target_cols,
    "positive_threshold": positive_threshold,
    "test_metrics": test_metrics,
}
out_metrics.parent.mkdir(parents=True, exist_ok=True)
out_metrics.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(out_metrics)
PY
}

cd "$REPO"
mkdir -p "$MATRIX_ROOT"
SUMMARY_CSV="$MATRIX_ROOT/source_matrix_summary.csv"
rm -f "$SUMMARY_CSV"

IFS=',' read -r -a SITES <<< "$SITE_LIST"

declare -a DOMAIN_SPECS

for SITE in "${SITES[@]}"; do
  SITE="$(echo "$SITE" | xargs)"
  [[ -n "$SITE" ]] || continue
  resolve_site_paths "$SITE"
  while IFS= read -r SRC; do
    [[ -n "$SRC" ]] || continue
    DOMAIN_SPECS+=("${SITE}|${SRC}|${DATASET}|${SPLIT}")
  done < <("$PYTHON" - "$DATASET" <<'PY'
import pandas as pd, sys
df = pd.read_parquet(sys.argv[1], columns=["audio_source"])
vals = sorted(set(str(x).strip() for x in df["audio_source"].dropna().tolist() if str(x).strip()))
for v in vals:
    print(v)
PY
  )
done

train_svm_group() {
  local train_label="$1"
  shift
  local out_root="$1"
  shift
  local dataset_path="$1"
  local trained_targets=()
  mkdir -p "$out_root"
  for TARGET in ${TARGET_COLS//,/ }; do
    local target_clean
    local log_path
    target_clean="$(echo "$TARGET" | xargs)"
    [[ -n "$target_clean" ]] || continue
    echo "[TRAIN] domain=$train_label target=$target_clean" >&2
    log_path="$(mktemp)"
    if "$PYTHON" -m python.ml.cli.audio_pca_svm_train \
        --dataset "$dataset_path" \
        --split-col split \
        --dataset-id-col sample_id \
        --split-id-col sample_id \
        --audio-path-col segment_path \
        --out-dir "$out_root/$target_clean" \
        --task binary \
        --backend "$SVM_BACKEND" \
        --target-col "$target_clean" \
        --n-components "$N_COMPONENTS" \
        --sample-rate "$SAMPLE_RATE" \
        --target-seconds "$TARGET_SECONDS" \
        --svm-class-weight "$SVM_CLASS_WEIGHT" \
        2>&1 | tee "$log_path" >&2; then
      trained_targets+=("$target_clean")
    else
      if grep -q "Train split has only one class after filtering" "$log_path"; then
        echo "[SKIP] domain=$train_label target=$target_clean reason=single_class_after_filter" >&2
      else
        cat "$log_path" >&2
        rm -f "$log_path"
        return 1
      fi
    fi
    rm -f "$log_path"
  done
  IFS=','; echo "${trained_targets[*]}"
}

for TRAIN_SPEC in "${DOMAIN_SPECS[@]}"; do
  IFS='|' read -r TRAIN_SITE TRAIN_SOURCE TRAIN_DATASET TRAIN_SPLIT <<< "$TRAIN_SPEC"
  TRAIN_LABEL="${TRAIN_SITE}__${TRAIN_SOURCE}"
  TRAIN_OUT="$MATRIX_ROOT/checkpoints/train_${TRAIN_LABEL}"
  TRAIN_FILTERED="$MATRIX_ROOT/prepared/train_${TRAIN_LABEL}.parquet"
  prepare_source_dataset "$TRAIN_DATASET" "$TRAIN_SOURCE" "$TRAIN_FILTERED"
  TRAINED_TARGETS="$(train_svm_group "$TRAIN_LABEL" "$TRAIN_OUT" "$TRAIN_FILTERED")"
  for EVAL_SPEC in "${DOMAIN_SPECS[@]}"; do
    IFS='|' read -r EVAL_SITE EVAL_SOURCE EVAL_DATASET EVAL_SPLIT <<< "$EVAL_SPEC"
    EVAL_LABEL="${EVAL_SITE}__${EVAL_SOURCE}"
    EVAL_OUT="$MATRIX_ROOT/evals/train_${TRAIN_LABEL}__eval_${EVAL_LABEL}"
    mkdir -p "$EVAL_OUT"
    if [[ -z "$TRAINED_TARGETS" ]]; then
      echo "[SKIP] train=$TRAIN_LABEL eval=$EVAL_LABEL reason=no_trained_targets"
      append_status_summary "$SUMMARY_CSV" "$TRAIN_LABEL" "$EVAL_LABEL" "skipped_train" "No targets trained for this train domain." "$TARGET_COLS"
      continue
    fi
    echo "[EVAL] train=$TRAIN_LABEL eval=$EVAL_LABEL"
    eval_svm_models \
      "$TRAIN_OUT" \
      "$EVAL_DATASET" \
      "$EVAL_SPLIT" \
      "$EVAL_SOURCE" \
      "$EVAL_OUT/audio_svm_eval_metrics.json" \
      "$TRAINED_TARGETS" \
      "$POSITIVE_THRESHOLD"
    append_summary "$SUMMARY_CSV" "$TRAIN_LABEL" "$EVAL_LABEL" "$EVAL_OUT/audio_svm_eval_metrics.json" "$TARGET_COLS"
  done
done

echo "[OK] summary -> $SUMMARY_CSV"
