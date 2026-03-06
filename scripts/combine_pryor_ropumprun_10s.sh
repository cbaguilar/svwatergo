#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python3}"
REPO="${REPO:-/home/cbaguilar/work/water/svwatergo}"
DERIVED_DIR="${DERIVED_DIR:-data/derived}"
PATTERN="${PATTERN:-ropumprun_labeled_mels_Pryor_Farms_*_10s.parquet}"
OUT_PARQUET="${OUT_PARQUET:-data/derived/ropumprun_labeled_mels_Pryor_Farms_multicam_10s.parquet}"
OUT_META="${OUT_META:-data/derived/ropumprun_labeled_mels_Pryor_Farms_multicam_10s_metadata.json}"

cd "$REPO"

if ! "$PYTHON" -c "import pandas, pyarrow" >/dev/null 2>&1; then
  echo "[FATAL] pandas/pyarrow missing for interpreter: $PYTHON"
  exit 1
fi

echo "[INFO] searching ${DERIVED_DIR}/${PATTERN}"

"$PYTHON" - "$DERIVED_DIR" "$PATTERN" "$OUT_PARQUET" "$OUT_META" <<'PY'
import json
import sys
from pathlib import Path

import pandas as pd

derived_dir = Path(sys.argv[1])
pattern = sys.argv[2]
out_parquet = Path(sys.argv[3])
out_meta = Path(sys.argv[4])

files = sorted(derived_dir.glob(pattern))
if not files:
    raise SystemExit(f"[FATAL] no files matched {derived_dir / pattern}")

frames = []
for p in files:
    df = pd.read_parquet(p)
    df = df.copy()
    df["source_dataset_file"] = p.name
    frames.append(df)

combined = pd.concat(frames, ignore_index=True, sort=False)

# Keep deterministic ordering for reproducible splits/training.
sort_cols = [c for c in ("site", "camera", "segment_start_ts_utc", "segment_path") if c in combined.columns]
if sort_cols:
    combined = combined.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)

out_parquet.parent.mkdir(parents=True, exist_ok=True)
combined.to_parquet(out_parquet, index=False)

label_col = "ropumprun_label" if "ropumprun_label" in combined.columns else None
label_counts = {}
if label_col:
    label_counts = {
        str(k): int(v)
        for k, v in combined[label_col].fillna("NA").value_counts(dropna=False).to_dict().items()
    }

camera_counts = {}
if "camera" in combined.columns:
    camera_counts = {
        str(k): int(v)
        for k, v in combined["camera"].fillna("NA").value_counts(dropna=False).to_dict().items()
    }

meta = {
    "dataset": "ropumprun_labeled_mels_pryor_farms_multicam_10s",
    "source_pattern": str(derived_dir / pattern),
    "source_files": [str(p) for p in files],
    "n_source_files": int(len(files)),
    "n_rows": int(len(combined)),
    "columns": list(combined.columns),
    "camera_counts": camera_counts,
    "label_counts": label_counts,
}
out_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print(f"[OK] wrote combined parquet: {out_parquet} rows={len(combined)}")
print(f"[OK] wrote metadata: {out_meta}")
print(f"[INFO] source files ({len(files)}):")
for p in files:
    print(f"  - {p}")
if camera_counts:
    print(f"[INFO] camera counts: {camera_counts}")
if label_counts:
    print(f"[INFO] label counts: {label_counts}")
PY
