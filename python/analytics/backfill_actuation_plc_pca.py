#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from python.analytics.build_audio_actuation_dataset import _fit_and_write_plc_pca


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill PLC PCA artifacts into an existing actuation dataset without rerunning full data generation."
    )
    p.add_argument("--dataset-root", required=True, help="Path like .../dataset=audio_actuation_dataset/site=.../window_s=10")
    p.add_argument("--samples-parquet", default="", help="Optional explicit samples.parquet path")
    p.add_argument("--write-plc-pca", action="store_true", default=True)
    p.add_argument("--plc-pca-components", type=int, default=8)
    p.add_argument("--plc-pca-fill-value", type=float, default=0.0)
    p.add_argument("--plc-pca-clip-abs", type=float, default=None)
    p.add_argument("--plc-pca-controls-weight", type=float, default=1.0)
    p.add_argument("--plc-pca-fit-split", default="train", choices=["train", "all"])
    p.add_argument("--plc-pca-cols", default="")
    p.add_argument("--plc-pca-include-regex", action="append", default=[])
    p.add_argument("--plc-pca-exclude-regex", action="append", default=[])
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    dataset_root = Path(args.dataset_root)
    if not dataset_root.exists():
        raise SystemExit(f"dataset root not found: {dataset_root}")

    samples_path = Path(args.samples_parquet) if str(args.samples_parquet).strip() else (dataset_root / "samples.parquet")
    if not samples_path.exists():
        raise SystemExit(f"samples parquet not found: {samples_path}")

    samples = pd.read_parquet(samples_path)
    if samples.empty:
        raise SystemExit("samples parquet is empty")

    updated, targets_path, model_path, meta_path = _fit_and_write_plc_pca(
        samples=samples,
        out_dataset_root=dataset_root,
        args=args,
    )

    updated.to_parquet(samples_path, index=False)
    print(f"[ok] updated {samples_path}", flush=True)

    report_path = dataset_root / "build_report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        outputs = report.setdefault("outputs", {})
        outputs["samples_parquet"] = str(samples_path)
        outputs["plc_pca_targets_parquet"] = str(targets_path) if targets_path else None
        outputs["plc_pca_model_npz"] = str(model_path) if model_path else None
        outputs["plc_pca_model_json"] = str(meta_path) if meta_path else None
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[ok] updated {report_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
