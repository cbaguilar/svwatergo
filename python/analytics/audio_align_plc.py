#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from window_features.io import default_s3_data_key, read_parquet_bytes_to_df, s3_get_bytes
from window_features.specs import PIPELINES

try:
    import boto3  # type: ignore
except Exception:
    boto3 = None

PARTITIONED_AUDIO_KEY_RE = re.compile(
    r"start=(?P<start>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(?:\.\d+)?Z)"
    r"_end=(?P<end>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(?:\.\d+)?Z)\.wav$",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Align audio clips (from audio manifest) to raw PLC datapoints in clip window using S3 parquet exports."
    )
    p.add_argument("--manifest", required=True, help="Path to audio_manifest.parquet or .csv")
    p.add_argument("--s3-bucket", required=True, help="PLC export S3 bucket")
    p.add_argument("--s3-prefix", required=True, help="PLC export prefix, e.g. exports/postgres/plc")
    p.add_argument("--site", default=None, help="Site override (default from manifest)")
    p.add_argument("--timestamp-col", default=None, help="PLC timestamp column override (default from site spec)")
    p.add_argument("--alignment-offset-ms", type=float, default=0.0, help="Offset added to audio timestamps before join")
    p.add_argument("--out-dir", default="./data", help="Output base directory")
    p.add_argument("--dataset-rows", default="audio_clip_plc_rows", help="Output dataset name for raw aligned rows")
    p.add_argument("--dataset-summary", default="audio_clip_match_summary", help="Output dataset name for per-clip summary")
    p.add_argument(
        "--plc-cols",
        default=None,
        help="Optional comma-separated PLC columns to keep (default: all columns from source parquet)",
    )
    p.add_argument("--limit-clips", type=int, default=0, help="Optional max manifest clips to process")
    p.add_argument("--include-empty", action="store_true", help="Include clips with zero matches in summary (default true)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    manifest = read_manifest(Path(args.manifest))
    if args.limit_clips:
        manifest = manifest.head(int(args.limit_clips)).copy()
    if len(manifest) == 0:
        raise SystemExit("No clips to align.")

    site = (args.site or str(manifest.iloc[0]["site"])).strip().lower()
    ts_col = args.timestamp_col or PIPELINES.get(site).ts_col if site in PIPELINES else (args.timestamp_col or "plctime")
    if ts_col is None:
        ts_col = "plctime"

    offset = pd.to_timedelta(float(args.alignment_offset_ms), unit="ms")
    manifest = prepare_manifest(manifest, offset=offset)

    plc_days = required_plc_days(manifest)
    print(f"[align] site={site} clips={len(manifest)} plc_days={len(plc_days)} ts_col={ts_col} offset_ms={args.alignment_offset_ms}")
    plc_df, load_meta = load_plc_days_from_s3(
        bucket=args.s3_bucket,
        prefix=args.s3_prefix,
        site=site,
        days=plc_days,
        timestamp_col=ts_col,
    )
    if len(plc_df) == 0:
        raise SystemExit("Loaded zero PLC rows for required days.")

    keep_plc_cols = None
    if args.plc_cols:
        keep_plc_cols = [c.strip() for c in str(args.plc_cols).split(",") if c.strip()]

    rows_df, summary_df = align_manifest_to_plc(
        manifest=manifest,
        plc_df=plc_df,
        timestamp_col=ts_col,
        keep_plc_cols=keep_plc_cols,
    )

    out_rows, out_summary, out_meta = write_outputs(
        out_dir=Path(args.out_dir),
        rows_df=rows_df,
        summary_df=summary_df,
        dataset_rows=args.dataset_rows,
        dataset_summary=args.dataset_summary,
        site=site,
        timestamp_col=ts_col,
        alignment_offset_ms=float(args.alignment_offset_ms),
        manifest_path=str(Path(args.manifest)),
        plc_load_meta=load_meta,
    )
    print(f"[OK] rows -> {out_rows} n={len(rows_df)}")
    print(f"[OK] summary -> {out_summary} n={len(summary_df)}")
    print(f"[OK] metadata -> {out_meta}")


def align_audio_partition_to_plc_raw(
    *,
    site: str,
    date_utc: str,
    audio_bucket: str,
    audio_prefix: str,
    plc_bucket: str,
    plc_prefix: str,
    timestamp_col: Optional[str] = None,
    alignment_offset_ms: float = 0.0,
    keep_plc_cols: Optional[List[str]] = None,
    out_dir: str = "./data",
    out_s3_bucket: Optional[str] = None,
    out_s3_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    site = str(site).strip().lower()
    if not site:
        raise ValueError("site is required")
    date_utc = str(date_utc).strip()
    if not date_utc:
        raise ValueError("date_utc is required")

    manifest = build_manifest_from_partitioned_audio_s3(
        bucket=audio_bucket,
        prefix=audio_prefix,
        site=site,
    )
    if len(manifest) == 0:
        raise ValueError("no audio clips found in partition")

    ts_col = timestamp_col or (PIPELINES.get(site).ts_col if site in PIPELINES else "plctime")
    offset = pd.to_timedelta(float(alignment_offset_ms), unit="ms")
    manifest = prepare_manifest(manifest, offset=offset)
    manifest = manifest[manifest["audio_day_utc_start"] == date_utc].copy()
    if len(manifest) == 0:
        raise ValueError(f"no clips remain for UTC date {date_utc} after parsing")

    plc_days = required_plc_days(manifest)
    plc_df, load_meta = load_plc_days_from_s3(
        bucket=plc_bucket,
        prefix=plc_prefix,
        site=site,
        days=plc_days,
        timestamp_col=ts_col,
    )
    if len(plc_df) == 0:
        raise ValueError("loaded zero PLC rows for required days")

    rows_df, summary_df = align_manifest_to_plc(
        manifest=manifest,
        plc_df=plc_df,
        timestamp_col=ts_col,
        keep_plc_cols=keep_plc_cols,
    )

    out_rows, out_summary, out_meta = write_outputs_partitioned(
        out_dir=Path(out_dir),
        rows_df=rows_df,
        summary_df=summary_df,
        site=site,
        date_utc=date_utc,
        timestamp_col=ts_col,
        alignment_offset_ms=float(alignment_offset_ms),
        audio_source={"bucket": audio_bucket, "prefix": audio_prefix},
        plc_load_meta=load_meta,
    )

    artifacts = [
        {"name": out_rows.name, "path": str(out_rows), "content_type": "application/x-parquet", "size_bytes": int(out_rows.stat().st_size)},
        {"name": out_summary.name, "path": str(out_summary), "content_type": "application/x-parquet", "size_bytes": int(out_summary.stat().st_size)},
        {"name": out_meta.name, "path": str(out_meta), "content_type": "application/json", "size_bytes": int(out_meta.stat().st_size)},
    ]

    uploads: List[Dict[str, Any]] = []
    if out_s3_bucket and out_s3_prefix:
        uploads = upload_alignment_partition_to_s3(
            out_s3_bucket=out_s3_bucket,
            out_s3_prefix=out_s3_prefix,
            site=site,
            date_utc=date_utc,
            rows_path=out_rows,
            summary_path=out_summary,
            meta_path=out_meta,
        )

    return {
        "summary": {
            "site": site,
            "date": date_utc,
            "n_audio_clips": int(len(summary_df)),
            "n_aligned_rows": int(len(rows_df)),
            "n_clips_with_matches": int(summary_df["has_plc_data"].fillna(False).sum()) if len(summary_df) else 0,
        },
        "artifacts": artifacts,
        "uploads": uploads,
        "plc_load_meta": load_meta,
        "audio_source": {"bucket": audio_bucket, "prefix": audio_prefix},
    }


def build_manifest_from_partitioned_audio_s3(*, bucket: str, prefix: str, site: str) -> pd.DataFrame:
    if boto3 is None:
        raise RuntimeError("boto3 not available")
    s3 = boto3.client("s3")
    rows: List[Dict[str, Any]] = []
    token: Optional[str] = None
    while True:
        kw: Dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        for obj in resp.get("Contents", []):
            key = str(obj.get("Key", ""))
            if not key.lower().endswith(".wav"):
                continue
            parsed = parse_start_end_from_partitioned_key(key)
            if not parsed:
                continue
            start_ts, end_ts = parsed
            rows.append(
                {
                    "site": site,
                    "bucket": bucket,
                    "key": key,
                    "start_ts_utc": start_ts.isoformat(),
                    "end_ts_utc": end_ts.isoformat(),
                    "start_unix": float(start_ts.timestamp()),
                    "end_unix": float(end_ts.timestamp()),
                    "clip_seconds": float((end_ts - start_ts).total_seconds()),
                }
            )
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return pd.DataFrame(rows)


def parse_start_end_from_partitioned_key(key: str) -> Optional[Tuple[pd.Timestamp, pd.Timestamp]]:
    m = PARTITIONED_AUDIO_KEY_RE.search(str(key))
    if not m:
        return None
    start_raw = m.group("start").replace("-", ":", 2).replace("-", ":", 1)  # noop-ish placeholder
    # convert HH-MM-SS to HH:MM:SS while preserving date and fractional seconds
    start_norm = normalize_compact_utc_label(m.group("start"))
    end_norm = normalize_compact_utc_label(m.group("end"))
    try:
        s = pd.to_datetime(start_norm, utc=True)
        e = pd.to_datetime(end_norm, utc=True)
        return s, e
    except Exception:
        return None


def normalize_compact_utc_label(s: str) -> str:
    # "2025-07-04T14-32-57.775598Z" -> "2025-07-04T14:32:57.775598Z"
    if "T" not in s:
        return s
    d, t = s.split("T", 1)
    if t.endswith("Z"):
        t = t[:-1]
        suffix = "Z"
    else:
        suffix = ""
    parts = t.split("-")
    if len(parts) >= 3:
        t = ":".join(parts[:3]) + ("-" + "-".join(parts[3:]) if len(parts) > 3 else "")
    return d + "T" + t + suffix


def read_manifest(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    required = {"site", "key", "bucket", "start_ts_utc", "end_ts_utc", "start_unix", "end_unix"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"Manifest missing required columns: {sorted(missing)}")
    return df


def prepare_manifest(df: pd.DataFrame, *, offset: pd.Timedelta) -> pd.DataFrame:
    out = df.copy()
    out["audio_start_ts_utc"] = pd.to_datetime(out["start_ts_utc"], utc=True, errors="coerce") + offset
    out["audio_end_ts_utc"] = pd.to_datetime(out["end_ts_utc"], utc=True, errors="coerce") + offset
    out = out[out["audio_start_ts_utc"].notna() & out["audio_end_ts_utc"].notna()].copy()
    out = out.sort_values(["audio_end_ts_utc", "key"], kind="mergesort").reset_index(drop=True)
    out["clip_id"] = out.apply(
        lambda r: f"{str(r['site']).lower()}::{Path(str(r['key'])).name}", axis=1
    )
    out["audio_day_utc_start"] = out["audio_start_ts_utc"].dt.strftime("%Y-%m-%d")
    out["audio_day_utc_end"] = out["audio_end_ts_utc"].dt.strftime("%Y-%m-%d")
    return out


def required_plc_days(manifest: pd.DataFrame) -> List[str]:
    days = set(manifest["audio_day_utc_start"].dropna().astype(str).tolist())
    days.update(manifest["audio_day_utc_end"].dropna().astype(str).tolist())
    return sorted(days)


def load_plc_days_from_s3(
    *,
    bucket: str,
    prefix: str,
    site: str,
    days: Sequence[str],
    timestamp_col: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    dfs: List[pd.DataFrame] = []
    loaded: List[str] = []
    failed: List[Dict[str, str]] = []
    for day in days:
        key = default_s3_data_key(prefix, site, day, parquet_filename="data.parquet")
        try:
            df = read_parquet_bytes_to_df(s3_get_bytes(bucket, key))
            df["__plc_source_day"] = day
            dfs.append(df)
            loaded.append(f"s3://{bucket}/{key}")
            print(f"[plc] loaded {day} rows={len(df)} cols={len(df.columns)}")
        except Exception as e:
            failed.append({"day": day, "key": key, "error": str(e)})
            print(f"[plc] skip {day}: {e}")
    if not dfs:
        return pd.DataFrame(), {
            "bucket": bucket,
            "prefix": prefix,
            "site": site,
            "days_requested": list(days),
            "days_loaded": [],
            "days_failed": failed,
        }
    out = pd.concat(dfs, ignore_index=True, sort=False)
    out[timestamp_col] = pd.to_datetime(out[timestamp_col], utc=True, errors="coerce")
    out = out[out[timestamp_col].notna()].sort_values(timestamp_col, kind="mergesort").reset_index(drop=True)
    meta = {
        "bucket": bucket,
        "prefix": prefix,
        "site": site,
        "days_requested": list(days),
        "sources_loaded": loaded,
        "days_failed": failed,
        "n_rows_loaded": int(len(out)),
        "n_cols_loaded": int(len(out.columns)),
        "timestamp_col": timestamp_col,
    }
    return out, meta


def align_manifest_to_plc(
    *,
    manifest: pd.DataFrame,
    plc_df: pd.DataFrame,
    timestamp_col: str,
    keep_plc_cols: Optional[List[str]],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    plc_cols = list(plc_df.columns)
    if keep_plc_cols:
        plc_cols = [c for c in keep_plc_cols if c in plc_df.columns]
        if timestamp_col not in plc_cols:
            plc_cols.append(timestamp_col)
    plc_cols = [c for c in plc_cols if c != "__plc_source_day"] + (["__plc_source_day"] if "__plc_source_day" in plc_df.columns else [])

    plc_sorted = plc_df[plc_cols].copy()
    plc_ts = pd.to_datetime(plc_sorted[timestamp_col], utc=True, errors="coerce")
    plc_sorted = plc_sorted[plc_ts.notna()].copy()
    plc_ts = pd.to_datetime(plc_sorted[timestamp_col], utc=True)
    plc_ns = plc_ts.view("int64").to_numpy()

    aligned_rows_parts: List[pd.DataFrame] = []
    summary_rows: List[Dict[str, Any]] = []

    for clip in manifest.itertuples(index=False):
        start_ts = pd.Timestamp(getattr(clip, "audio_start_ts_utc"))
        end_ts = pd.Timestamp(getattr(clip, "audio_end_ts_utc"))
        start_ns = int(start_ts.value)
        end_ns = int(end_ts.value)
        i0 = int(np.searchsorted(plc_ns, start_ns, side="left"))
        i1 = int(np.searchsorted(plc_ns, end_ns, side="right"))

        n_match = max(0, i1 - i0)
        summary: Dict[str, Any] = {
            "clip_id": getattr(clip, "clip_id"),
            "site": getattr(clip, "site"),
            "audio_s3_key": getattr(clip, "key"),
            "audio_s3_uri": f"s3://{getattr(clip, 'bucket')}/{getattr(clip, 'key')}",
            "audio_start_ts_utc": start_ts,
            "audio_end_ts_utc": end_ts,
            "audio_start_unix": float(getattr(clip, "start_unix")),
            "audio_end_unix": float(getattr(clip, "end_unix")),
            "alignment_offset_ms_used": float((start_ts - pd.Timestamp(getattr(clip, 'start_ts_utc'))).total_seconds() * 1000.0),
            "n_plc_rows_in_window": int(n_match),
            "has_plc_data": bool(n_match > 0),
        }

        if n_match > 0:
            matched = plc_sorted.iloc[i0:i1].copy()
            matched = matched.reset_index(drop=True)
            matched["clip_id"] = getattr(clip, "clip_id")
            matched["audio_site"] = getattr(clip, "site")
            matched["audio_s3_key"] = getattr(clip, "key")
            matched["audio_s3_uri"] = f"s3://{getattr(clip, 'bucket')}/{getattr(clip, 'key')}"
            matched["audio_start_ts_utc"] = start_ts
            matched["audio_end_ts_utc"] = end_ts
            matched["audio_start_unix"] = float(getattr(clip, "start_unix"))
            matched["audio_end_unix"] = float(getattr(clip, "end_unix"))
            matched["clip_seconds_measured"] = float(getattr(clip, "clip_seconds")) if hasattr(clip, "clip_seconds") else np.nan
            matched["alignment_offset_ms_used"] = summary["alignment_offset_ms_used"]
            matched["plc_ts"] = pd.to_datetime(matched[timestamp_col], utc=True, errors="coerce")
            matched["relative_t_sec"] = (
                (matched["plc_ts"].view("int64") - int(start_ts.value)).astype("float64") / 1e9
            )
            aligned_rows_parts.append(matched)

            summary["first_plc_ts"] = pd.to_datetime(matched["plc_ts"].iloc[0], utc=True)
            summary["last_plc_ts"] = pd.to_datetime(matched["plc_ts"].iloc[-1], utc=True)
            summary["first_relative_t_sec"] = float(matched["relative_t_sec"].iloc[0])
            summary["last_relative_t_sec"] = float(matched["relative_t_sec"].iloc[-1])
        else:
            summary["first_plc_ts"] = pd.NaT
            summary["last_plc_ts"] = pd.NaT
            summary["first_relative_t_sec"] = np.nan
            summary["last_relative_t_sec"] = np.nan

        summary_rows.append(summary)

    if aligned_rows_parts:
        rows_df = pd.concat(aligned_rows_parts, ignore_index=True, sort=False)
    else:
        rows_df = pd.DataFrame()
    summary_df = pd.DataFrame(summary_rows)
    return rows_df, summary_df


def write_outputs(
    *,
    out_dir: Path,
    rows_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    dataset_rows: str,
    dataset_summary: str,
    site: str,
    timestamp_col: str,
    alignment_offset_ms: float,
    manifest_path: str,
    plc_load_meta: Dict[str, Any],
) -> Tuple[Path, Path, Path]:
    rows_base = out_dir / f"dataset={dataset_rows}" / f"site={site}"
    summary_base = out_dir / f"dataset={dataset_summary}" / f"site={site}"
    rows_base.mkdir(parents=True, exist_ok=True)
    summary_base.mkdir(parents=True, exist_ok=True)

    rows_path = rows_base / "audio_clip_plc_rows.parquet"
    summary_path = summary_base / "audio_clip_match_summary.parquet"
    meta_path = summary_base / "audio_clip_match_summary_metadata.json"

    rows_df.to_parquet(rows_path, engine="pyarrow", compression="snappy", index=False)
    summary_df.to_parquet(summary_path, engine="pyarrow", compression="snappy", index=False)

    meta = {
        "site": site,
        "timestamp_col": timestamp_col,
        "alignment_offset_ms": alignment_offset_ms,
        "manifest_path": manifest_path,
        "n_audio_clips": int(len(summary_df)),
        "n_aligned_rows": int(len(rows_df)),
        "n_clips_with_matches": int(summary_df["has_plc_data"].fillna(False).sum()) if len(summary_df) else 0,
        "rows_columns": list(rows_df.columns),
        "summary_columns": list(summary_df.columns),
        "plc_load_meta": plc_load_meta,
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    return rows_path, summary_path, meta_path


def write_outputs_partitioned(
    *,
    out_dir: Path,
    rows_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    site: str,
    date_utc: str,
    timestamp_col: str,
    alignment_offset_ms: float,
    audio_source: Dict[str, Any],
    plc_load_meta: Dict[str, Any],
) -> Tuple[Path, Path, Path]:
    rows_base = out_dir / "dataset=audio_clip_plc_rows" / f"site={site}" / f"date={date_utc}"
    summary_base = out_dir / "dataset=audio_clip_match_summary" / f"site={site}" / f"date={date_utc}"
    rows_base.mkdir(parents=True, exist_ok=True)
    summary_base.mkdir(parents=True, exist_ok=True)

    rows_path = rows_base / "audio_clip_plc_rows.parquet"
    summary_path = summary_base / "audio_clip_match_summary.parquet"
    meta_path = summary_base / "audio_clip_match_summary_metadata.json"

    rows_df.to_parquet(rows_path, engine="pyarrow", compression="snappy", index=False)
    summary_df.to_parquet(summary_path, engine="pyarrow", compression="snappy", index=False)

    meta = {
        "site": site,
        "date_utc": date_utc,
        "timezone_partition": "UTC",
        "timestamp_col": timestamp_col,
        "alignment_offset_ms": alignment_offset_ms,
        "audio_source": audio_source,
        "n_audio_clips": int(len(summary_df)),
        "n_aligned_rows": int(len(rows_df)),
        "n_clips_with_matches": int(summary_df["has_plc_data"].fillna(False).sum()) if len(summary_df) else 0,
        "rows_columns": list(rows_df.columns),
        "summary_columns": list(summary_df.columns),
        "plc_load_meta": plc_load_meta,
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return rows_path, summary_path, meta_path


def upload_alignment_partition_to_s3(
    *,
    out_s3_bucket: str,
    out_s3_prefix: str,
    site: str,
    date_utc: str,
    rows_path: Path,
    summary_path: Path,
    meta_path: Path,
) -> List[Dict[str, Any]]:
    if boto3 is None:
        raise RuntimeError("boto3 not available")
    s3 = boto3.client("s3")
    base = f"{out_s3_prefix.strip('/')}"
    mapping = [
        (rows_path, f"{base}/dataset=audio_clip_plc_rows/site={site}/date={date_utc}/{rows_path.name}", "application/x-parquet"),
        (summary_path, f"{base}/dataset=audio_clip_match_summary/site={site}/date={date_utc}/{summary_path.name}", "application/x-parquet"),
        (meta_path, f"{base}/dataset=audio_clip_match_summary/site={site}/date={date_utc}/{meta_path.name}", "application/json"),
    ]
    out: List[Dict[str, Any]] = []
    for local_path, key, content_type in mapping:
        s3.upload_file(str(local_path), out_s3_bucket, key, ExtraArgs={"ContentType": content_type})
        out.append(
            {
                "bucket": out_s3_bucket,
                "key": key,
                "s3_uri": f"s3://{out_s3_bucket}/{key}",
                "content_type": content_type,
                "size_bytes": int(local_path.stat().st_size),
            }
        )
    return out


if __name__ == "__main__":
    main()
