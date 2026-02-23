from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from .io import (
    default_s3_data_key,
    read_parquet_bytes_to_df,
    s3_get_bytes,
    write_json_local,
    write_parquet_local,
    ensure_parent_dir,
)
from .postprocess import apply_flow_gates_to_features, add_continuous_window_derivatives
from .specs import PIPELINES, SitePipelineSpec, apply_site_spec
from .window import analyze_interarrival, compute_window_features_for_day


def build_output_paths(
    out_dir: Path,
    *,
    window_seconds: int,
    stride_seconds: Optional[int],
    site: str,
    day: str,
) -> Tuple[Path, Path, Path]:
    stride_seconds = window_seconds if stride_seconds is None else int(stride_seconds)
    base = out_dir / "dataset=window_features" / f"window_s={int(window_seconds)}"
    if int(stride_seconds) != int(window_seconds):
        base = base / f"stride_s={int(stride_seconds)}"
    base = base / f"site={site}" / f"date={day}"
    return (
        base / "window_features.parquet",
        base / "window_features.csv",
        base / "window_features_metadata.json",
    )


def generate_window_features_for_day(
    *,
    site: str,
    day: str,
    s3_bucket: str,
    s3_prefix: str,
    timestamp_col: Optional[str] = None,
    window_seconds: int = 60,
    stride_seconds: Optional[int] = None,
    max_gap_stale_s: float = 300.0,
) -> Tuple[pd.DataFrame, Dict[str, object], Dict[str, object]]:
    spec = PIPELINES.get(site)
    if spec is None:
        raise ValueError(f"Unknown site: {site} (known: {sorted(PIPELINES)})")

    ts_col = timestamp_col or spec.ts_col

    data_key = default_s3_data_key(s3_prefix, site, day)
    df = read_parquet_bytes_to_df(s3_get_bytes(s3_bucket, data_key))

    df, groups, report = apply_site_spec(df, spec)
    _, stats = analyze_interarrival(df, ts_col)

    feat = compute_window_features_for_day(
        df,
        site=site,
        day=day,
        ts_col=ts_col,
        groups=groups,
        window_seconds=window_seconds,
        stride_seconds=stride_seconds,
        max_gap_for_stale_s=max_gap_stale_s,
    )

    if spec.flow_gates:
        feat = apply_flow_gates_to_features(
            feat,
            gates=spec.flow_gates,
            feature_suffixes=["__last", "__mean_tw"],
        )

    feat = add_continuous_window_derivatives(
        feat,
        groups,
        base_suffix="__mean_tw",
        out_suffix="__d1",
        fill_value=0.0,
        sort_col="window_start_ts",
    )

    if spec.flow_gates:
        feat = apply_flow_gates_to_features(
            feat,
            gates=spec.flow_gates,
            feature_suffixes=["__d1"],
        )

    meta = {
        "site": site,
        "day": day,
        "window_seconds": int(window_seconds),
        "stride_seconds": int(window_seconds if stride_seconds is None else stride_seconds),
        "source": f"s3://{s3_bucket}/{data_key}",
        "timestamp_col": ts_col,
        "n_windows": int(len(feat)),
        "n_nonempty_windows": int((feat["n_rows"] > 0).sum()),
        "column_groups": {
            "continuous": groups.continuous,
            "boolean": groups.boolean,
            "discrete": groups.discrete,
        },
        "stale_gap_sec": max_gap_stale_s,
        "flow_gates": [asdict(g) for g in (spec.flow_gates or [])],
        "interarrival_stats": stats,
        "site_spec": spec.site,
    }

    return feat, meta, report


def write_window_features_outputs(
    feat: pd.DataFrame,
    meta: Dict[str, object],
    *,
    out_dir: Path,
    window_seconds: int,
    stride_seconds: Optional[int],
    site: str,
    day: str,
    compression: str = "snappy",
) -> Tuple[Path, Path, Path]:
    out_parquet, out_csv, out_meta = build_output_paths(
        out_dir, window_seconds=window_seconds, stride_seconds=stride_seconds, site=site, day=day
    )

    write_parquet_local(feat, out_parquet, compression=compression)
    ensure_parent_dir(out_csv)
    feat.to_csv(out_csv, index=False)
    write_json_local(meta, out_meta)

    return out_parquet, out_csv, out_meta
