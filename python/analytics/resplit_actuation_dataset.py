#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

from python.analytics.build_audio_actuation_dataset import (
    ACTUATORS,
    _build_selected_actuation_key,
    _build_stats,
    _parse_csv_list,
    _split_assign_by_combo,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Resplit an existing actuation dataset using a reduced actuator subset without rerunning audio conversion or embeddings."
    )
    p.add_argument("--dataset-root", required=True, help="Existing dataset root")
    p.add_argument("--out-dataset-root", default="", help="Optional output dataset root; defaults to in-place update")
    p.add_argument("--samples-parquet", default="", help="Optional explicit samples.parquet path")
    p.add_argument("--split-seed", type=int, default=1337)
    p.add_argument("--train-ratio", type=float, default=0.70)
    p.add_argument("--test-ratio", type=float, default=0.15)
    p.add_argument("--val-ratio", type=float, default=0.15)
    p.add_argument(
        "--split-actuators",
        default="ropumprun,wellpumprun,feedpumprun,deliveryrun,flushrun",
        help="Comma-separated actuator subset used for split stratification key",
    )
    p.add_argument("--split-min-positive-count", type=int, default=3)
    p.add_argument("--copy-artifacts", default="yes", choices=["yes", "no"])
    return p.parse_args()


def _copy_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> int:
    args = _parse_args()
    dataset_root = Path(args.dataset_root)
    if not dataset_root.exists():
        raise SystemExit(f"dataset root not found: {dataset_root}")
    out_dataset_root = Path(args.out_dataset_root) if str(args.out_dataset_root).strip() else dataset_root
    out_dataset_root.mkdir(parents=True, exist_ok=True)

    samples_path = Path(args.samples_parquet) if str(args.samples_parquet).strip() else (dataset_root / "samples.parquet")
    if not samples_path.exists():
        raise SystemExit(f"samples parquet not found: {samples_path}")

    samples = pd.read_parquet(samples_path)
    if samples.empty:
        raise SystemExit("samples parquet is empty")
    if "event_window_id" not in samples.columns:
        raise SystemExit("samples parquet is missing event_window_id; cannot resplit")

    split_actuators = _parse_csv_list(str(args.split_actuators))
    if not split_actuators:
        raise SystemExit("--split-actuators must include at least one actuator")
    invalid_actuators = [a for a in split_actuators if a not in ACTUATORS]
    if invalid_actuators:
        raise SystemExit(f"unknown split actuators: {', '.join(invalid_actuators)}")

    work = samples.copy()
    work = _build_selected_actuation_key(work, split_actuators)
    work = _split_assign_by_combo(
        work,
        combo_col="split_actuation_combo",
        split_actuators=split_actuators,
        min_positive_count=int(args.split_min_positive_count),
        seed=int(args.split_seed),
        train_ratio=float(args.train_ratio),
        test_ratio=float(args.test_ratio),
        val_ratio=float(args.val_ratio),
    )

    out_samples_path = out_dataset_root / "samples.parquet"
    out_split_manifest_path = out_dataset_root / "split_manifest.parquet"
    out_stats_path = out_dataset_root / "combo_stats.json"
    out_report_path = out_dataset_root / "build_report.json"

    work.to_parquet(out_samples_path, index=False)

    split_cols = [
        "sample_id",
        "site",
        "audio_source",
        "camera",
        "day_utc",
        "segment_start_ts_utc",
        "segment_end_ts_utc",
        "actuation_combo",
        "actuation_bits",
        "split_actuators",
        "split_actuation_combo",
        "split_actuation_bits",
        "event_window_id",
        "split_group_id",
        "split",
        "split_seed",
        "split_min_positive_count",
    ]
    split_manifest = work[[c for c in split_cols if c in work.columns]].copy()
    split_manifest.to_parquet(out_split_manifest_path, index=False)

    stats = _build_stats(work)
    out_stats_path.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = {}
    src_report_path = dataset_root / "build_report.json"
    if src_report_path.exists():
        report = json.loads(src_report_path.read_text(encoding="utf-8"))
    outputs = report.setdefault("outputs", {})
    outputs["samples_parquet"] = str(out_samples_path)
    outputs["split_manifest_parquet"] = str(out_split_manifest_path)
    outputs["combo_stats_json"] = str(out_stats_path)
    split_node = report.setdefault("split", {})
    split_node["seed"] = int(args.split_seed)
    split_node["train_ratio"] = float(args.train_ratio)
    split_node["test_ratio"] = float(args.test_ratio)
    split_node["val_ratio"] = float(args.val_ratio)
    split_node["split_actuators"] = split_actuators
    split_node["min_positive_count"] = int(args.split_min_positive_count)
    split_node["actual"] = {
        str(k): float(v) for k, v in work["split"].value_counts(normalize=True).sort_index().to_dict().items()
    }
    report["n_samples"] = int(len(work))
    report["n_actuation_combos"] = int(work["actuation_combo"].nunique())
    out_report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if str(args.copy_artifacts) == "yes" and out_dataset_root != dataset_root:
        for name in (
            "embeddings_panns.npz",
            "embeddings_joined.parquet",
            "plc_window_pca_targets.parquet",
            "plc_window_pca_model.npz",
            "plc_window_pca_model.json",
            "combo_stats.json",
        ):
            src = dataset_root / name
            if name == "combo_stats.json":
                continue
            _copy_if_exists(src, out_dataset_root / name)

    print(f"[ok] wrote {out_samples_path}", flush=True)
    print(f"[ok] wrote {out_split_manifest_path}", flush=True)
    print(f"[ok] wrote {out_stats_path}", flush=True)
    print(f"[ok] wrote {out_report_path}", flush=True)
    if out_dataset_root != dataset_root:
        print(f"[ok] reused artifacts from {dataset_root}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
