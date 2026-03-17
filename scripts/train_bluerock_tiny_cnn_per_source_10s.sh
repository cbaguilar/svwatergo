#!/usr/bin/env bash
set -u -o pipefail

# Train one Tiny CNN model per bluerock audio source (rpi + each wyze source).
# This script:
#  1) Reads a unified dataset/split manifest.
#  2) Auto-discovers source values from `audio_source` (or uses SOURCE_LIST if set).
#  3) Writes per-source filtered parquet shards.
#  4) Trains a source-specific model.
#  5) Renders source-specific 5-panel plots.
#
# Example:
#   bash scripts/train_bluerock_tiny_cnn_per_source_10s.sh
#
# Example with explicit sources:
#   SOURCE_LIST="rpi_audio,wyze_Bluerock_Cam_1,wyze_Bluerock_Cam_2,wyze_camera_5" \
#   bash scripts/train_bluerock_tiny_cnn_per_source_10s.sh

PYTHON="${PYTHON:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

DATASET="${DATASET:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/samples.parquet}"
SPLIT="${SPLIT:-/mnt/d/datasets/svwatergo/derived/dataset=audio_event_dataset/site=bluerock/window_s=10/split_manifest.parquet}"

# Comma-separated source names. Empty = auto-discover from DATASET[audio_source].
SOURCE_LIST="${SOURCE_LIST:-}"

TARGET_COLS="${TARGET_COLS:-ropumprun_duty,deliveryrun_duty}"
POSITIVE_THRESHOLD="${POSITIVE_THRESHOLD:-0.5}"
MEL_NORMALIZATION="${MEL_NORMALIZATION:-log_db}"
CMVN="${CMVN:-yes}"
MODEL_ARCH="${MODEL_ARCH:-resnet_small}"
CLASS_WEIGHT="${CLASS_WEIGHT:-balanced}"

EPOCHS="${EPOCHS:-12}"
BATCH_SIZE="${BATCH_SIZE:-64}"
LEARNING_RATE="${LEARNING_RATE:-1e-3}"
WEIGHT_DECAY="${WEIGHT_DECAY:-1e-4}"

MIN_ROWS_PER_SOURCE="${MIN_ROWS_PER_SOURCE:-500}"
MIN_POS_PER_TARGET="${MIN_POS_PER_TARGET:-20}"
SEED="${SEED:-42}"

TMP_ROOT="${TMP_ROOT:-/mnt/d/datasets/svwatergo/derived/tmp/per_source_bluerock_10s}"
OUT_ROOT="${OUT_ROOT:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_per_source}"
PLOT_ROOT="${PLOT_ROOT:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_per_source}"
SUMMARY_JSON="${SUMMARY_JSON:-/mnt/d/datasets/svwatergo/derived/plots/bluerock_10s_per_source_summary.json}"

if [[ ! -f "$DATASET" ]]; then
  echo "[FATAL] missing dataset: $DATASET"
  exit 1
fi
if [[ ! -f "$SPLIT" ]]; then
  echo "[FATAL] missing split manifest: $SPLIT"
  exit 1
fi

mkdir -p "$TMP_ROOT" "$OUT_ROOT" "$PLOT_ROOT"
if [[ ! -d "$REPO" ]]; then
  echo "[FATAL] REPO path does not exist: $REPO"
  exit 1
fi
cd "$REPO" || exit 1

extra_args=()
if [[ "$CMVN" == "yes" ]]; then
  extra_args+=(--cmvn)
fi
if [[ -n "$CLASS_WEIGHT" ]]; then
  extra_args+=(--class-weight "$CLASS_WEIGHT")
fi

if [[ -z "$SOURCE_LIST" ]]; then
  SOURCE_LIST="$("$PYTHON" - "$DATASET" <<'PY'
import sys
import pandas as pd
p = sys.argv[1]
df = pd.read_parquet(p, columns=["audio_source"])
vals = sorted(set(str(x).strip() for x in df["audio_source"].dropna().tolist() if str(x).strip()))
print(",".join(vals))
PY
)"
fi

if [[ -z "$SOURCE_LIST" ]]; then
  echo "[FATAL] no sources found. Set SOURCE_LIST or verify dataset audio_source column."
  exit 1
fi

IFS=',' read -r -a SOURCES <<< "$SOURCE_LIST"
echo "[INFO] sources=${#SOURCES[@]} :: $SOURCE_LIST"

OK=0
SKIP=0
FAIL=0
RESULTS_NDJSON="${TMP_ROOT}/results.ndjson"
rm -f "$RESULTS_NDJSON"

for SRC_RAW in "${SOURCES[@]}"; do
  SRC="$(echo "$SRC_RAW" | xargs)"
  if [[ -z "$SRC" ]]; then
    continue
  fi
  SRC_SAFE="$(echo "$SRC" | tr -cs 'A-Za-z0-9._-' '_' | sed 's/^_//; s/_$//')"
  SRC_DATASET="${TMP_ROOT}/samples_${SRC_SAFE}.parquet"
  SRC_STATS="${TMP_ROOT}/stats_${SRC_SAFE}.json"
  SRC_OUT_DIR="${OUT_ROOT}/${SRC_SAFE}"
  SRC_PLOT_PNG="${PLOT_ROOT}/${SRC_SAFE}_5panel.png"
  SRC_PLOT_META="${PLOT_ROOT}/${SRC_SAFE}_5panel.json"

  echo
  echo "============================================================"
  echo "[SOURCE] ${SRC}"
  echo "============================================================"

  "$PYTHON" - "$DATASET" "$SRC" "$SRC_DATASET" "$SRC_STATS" "$TARGET_COLS" "$POSITIVE_THRESHOLD" "$MIN_ROWS_PER_SOURCE" "$MIN_POS_PER_TARGET" <<'PY'
import json
import sys
from pathlib import Path
import pandas as pd

dataset, src, out_ds, out_stats, target_cols_csv, th_s, min_rows_s, min_pos_s = sys.argv[1:9]
th = float(th_s)
min_rows = int(min_rows_s)
min_pos = int(min_pos_s)
targets = [c.strip() for c in target_cols_csv.split(",") if c.strip()]

df = pd.read_parquet(dataset)
if "audio_source" not in df.columns:
    raise SystemExit("dataset missing audio_source column")
if "sample_id" not in df.columns:
    raise SystemExit("dataset missing sample_id column")

sub = df[df["audio_source"].astype(str) == src].copy()
rows = int(len(sub))
stats = {
    "source": src,
    "rows": rows,
    "skip_reason": "",
    "target_counts": {},
}
if rows < min_rows:
    stats["skip_reason"] = f"rows<{min_rows}"
    Path(out_stats).write_text(json.dumps(stats, indent=2), encoding="utf-8")
    raise SystemExit(2)

for t in targets:
    if t not in sub.columns:
        stats["skip_reason"] = f"missing_target:{t}"
        Path(out_stats).write_text(json.dumps(stats, indent=2), encoding="utf-8")
        raise SystemExit(2)
    x = pd.to_numeric(sub[t], errors="coerce").fillna(0.0)
    n_pos = int((x >= th).sum())
    n_neg = int((x < th).sum())
    stats["target_counts"][t] = {"pos": n_pos, "neg": n_neg}
    if n_pos < min_pos or n_neg < min_pos:
        stats["skip_reason"] = f"class_imbalance:{t}:pos={n_pos}:neg={n_neg}:min={min_pos}"
        Path(out_stats).write_text(json.dumps(stats, indent=2), encoding="utf-8")
        raise SystemExit(2)

Path(out_ds).parent.mkdir(parents=True, exist_ok=True)
sub.to_parquet(out_ds, index=False)
Path(out_stats).write_text(json.dumps(stats, indent=2), encoding="utf-8")
print(f"[OK] wrote {out_ds}")
print(f"[OK] wrote {out_stats}")
PY
  rc=$?
  if [[ $rc -ne 0 ]]; then
    if [[ $rc -eq 2 ]]; then
      echo "[SKIP] source ${SRC} did not meet row/class minimums"
      SKIP=$((SKIP + 1))
      echo "{\"source\":\"${SRC}\",\"status\":\"skipped\",\"stats\":\"${SRC_STATS}\"}" >> "$RESULTS_NDJSON"
      continue
    fi
    echo "[FAIL] failed preparing source dataset for ${SRC}"
    FAIL=$((FAIL + 1))
    echo "{\"source\":\"${SRC}\",\"status\":\"failed_prepare\"}" >> "$RESULTS_NDJSON"
    continue
  fi

  mkdir -p "$SRC_OUT_DIR" "$(dirname "$SRC_PLOT_PNG")"
  if ! "$PYTHON" -m python.ml.cli.audio_tiny_cnn_train \
    --dataset "$SRC_DATASET" \
    --split-manifest "$SPLIT" \
    --dataset-id-col sample_id \
    --split-id-col sample_id \
    --split-col split \
    --audio-path-col segment_path \
    --out-dir "$SRC_OUT_DIR" \
    --task multilabel \
    --target-cols "$TARGET_COLS" \
    --positive-threshold "$POSITIVE_THRESHOLD" \
    --epochs "$EPOCHS" \
    --batch-size "$BATCH_SIZE" \
    --learning-rate "$LEARNING_RATE" \
    --weight-decay "$WEIGHT_DECAY" \
    --sample-rate 16000 \
    --target-seconds 10 \
    --model-arch "$MODEL_ARCH" \
    --mel-normalization "$MEL_NORMALIZATION" \
    --random-state "$SEED" \
    "${extra_args[@]}"; then
    echo "[FAIL] training failed for source ${SRC}"
    FAIL=$((FAIL + 1))
    echo "{\"source\":\"${SRC}\",\"status\":\"failed_train\",\"out_dir\":\"${SRC_OUT_DIR}\"}" >> "$RESULTS_NDJSON"
    continue
  fi

  if ! "$PYTHON" -m python.ml.cli.audio_pca_svm_plot \
    --checkpoint-dir "$SRC_OUT_DIR" \
    --out-png "$SRC_PLOT_PNG" \
    --out-meta "$SRC_PLOT_META" \
    --title "Audio ${MODEL_ARCH} Multilabel (bluerock 10s, source=${SRC})"; then
    echo "[WARN] plot generation failed for source ${SRC}"
  fi

  echo "[OK] model -> ${SRC_OUT_DIR}/audio_tiny_cnn_model.pt"
  echo "[OK] plot  -> ${SRC_PLOT_PNG}"
  OK=$((OK + 1))
  echo "{\"source\":\"${SRC}\",\"status\":\"ok\",\"out_dir\":\"${SRC_OUT_DIR}\",\"plot\":\"${SRC_PLOT_PNG}\",\"stats\":\"${SRC_STATS}\"}" >> "$RESULTS_NDJSON"
done

"$PYTHON" - "$RESULTS_NDJSON" "$SUMMARY_JSON" "$SOURCE_LIST" "$OK" "$SKIP" "$FAIL" <<'PY'
import json
import sys
from pathlib import Path

res_path, out_path, source_list, ok_s, skip_s, fail_s = sys.argv[1:7]
rows = []
p = Path(res_path)
if p.exists():
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass

summary = {
    "sources_requested": [x.strip() for x in source_list.split(",") if x.strip()],
    "ok": int(ok_s),
    "skipped": int(skip_s),
    "failed": int(fail_s),
    "results": rows,
}
Path(out_path).parent.mkdir(parents=True, exist_ok=True)
Path(out_path).write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(f"[OK] wrote {out_path}")
PY

echo
echo "============================================================"
echo "[DONE] per-source training"
echo "[SUMMARY] ok=${OK} skipped=${SKIP} failed=${FAIL}"
echo "[SUMMARY_JSON] ${SUMMARY_JSON}"
echo "============================================================"

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
exit 0
