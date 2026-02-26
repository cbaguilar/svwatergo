#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

try:
    import joblib  # type: ignore
except Exception:
    joblib = None

from window_features.pipeline import (
    generate_window_features_for_day,
    write_window_features_outputs,
)
from window_pca.loader import load_many
from window_pca.model import fit_pca, transform_pca
from window_pca.selection import select_pca_columns
from audio_align_plc import align_audio_partition_to_plc_raw


def main() -> None:
    ap = argparse.ArgumentParser(description="SVWaterGo analytics worker")
    ap.add_argument("--job-spec", required=True, help="Path to JSON job spec")
    ap.add_argument("--result", required=True, help="Path to JSON result output")
    args = ap.parse_args()

    t0 = time.time()
    spec = read_json(Path(args.job_spec))
    job_type = str(spec.get("job_type", "")).strip()
    job_id = str(spec.get("job_id", "")).strip()
    artifacts_dir = Path(spec.get("artifacts_dir", "."))
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Any] = {
        "job_id": job_id,
        "job_type": job_type,
        "artifacts_dir": str(artifacts_dir),
        "started_at_unix": t0,
    }

    try:
        if job_type == "feature_engineering":
            feature_req = spec.get("feature_run") or {}
            payload, artifacts = run_feature_job(feature_req, artifacts_dir)
        elif job_type == "pca":
            pca_req = spec.get("pca_run") or {}
            payload, artifacts = run_pca_job(pca_req, artifacts_dir)
        elif job_type == "audio_align_plc":
            align_req = spec.get("audio_align_plc") or {}
            payload, artifacts = run_audio_align_plc_job(align_req, artifacts_dir)
        else:
            raise ValueError(f"unsupported job_type: {job_type}")

        result.update(payload)
        result["artifacts"] = artifacts
        result["status"] = "succeeded"
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        write_json(Path(args.result), result)
        raise
    finally:
        result["duration_sec"] = round(time.time() - t0, 3)
        write_json(Path(args.result), result)


def run_feature_job(req: Dict[str, Any], artifacts_dir: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    site = str(req.get("site", "")).strip().lower()
    if not site:
        raise ValueError("feature_run.site is required")

    day = str(req.get("day", "")).strip()
    if not day:
        raise ValueError("feature_run.day is required (single-day support for now)")

    data_source = str(req.get("data_source", "s3") or "s3").strip().lower()
    if data_source not in ("s3", ""):
        raise ValueError(f"feature data_source={data_source!r} not implemented yet (use s3)")

    s3_bucket = str(req.get("s3_bucket", "")).strip()
    s3_prefix = str(req.get("s3_prefix", "")).strip()
    if not s3_bucket or not s3_prefix:
        raise ValueError("feature_run.s3_bucket and s3_prefix are required for s3 data_source")

    window_seconds = int(req.get("window_seconds") or 60)
    stride_seconds = req.get("stride_seconds")
    stride_seconds = int(stride_seconds) if stride_seconds not in (None, "") else None
    max_gap_stale_s = float(req.get("max_gap_stale_s") or 300.0)
    timestamp_col = req.get("timestamp_col")
    timestamp_col = str(timestamp_col).strip() if timestamp_col else None

    feat, meta, report = generate_window_features_for_day(
        site=site,
        day=day,
        s3_bucket=s3_bucket,
        s3_prefix=s3_prefix,
        timestamp_col=timestamp_col,
        window_seconds=window_seconds,
        stride_seconds=stride_seconds,
        max_gap_stale_s=max_gap_stale_s,
    )

    out_root = artifacts_dir / "feature_outputs"
    out_parquet, out_csv, out_meta = write_window_features_outputs(
        feat,
        meta,
        out_dir=out_root,
        window_seconds=window_seconds,
        stride_seconds=stride_seconds,
        site=site,
        day=day,
    )

    payload = {
        "summary": {
            "site": site,
            "day": day,
            "n_rows": int(len(feat)),
            "n_cols": int(len(feat.columns)),
            "window_seconds": window_seconds,
            "stride_seconds": int(window_seconds if stride_seconds is None else stride_seconds),
        },
        "feature_meta": meta,
        "feature_report": report,
    }
    arts = [
        artifact_dict(out_parquet, "application/x-parquet"),
        artifact_dict(out_csv, "text/csv"),
        artifact_dict(out_meta, "application/json"),
    ]
    return payload, arts


def run_pca_job(req: Dict[str, Any], artifacts_dir: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    site = str(req.get("site", "") or "").strip().lower()

    df_all, load_meta = load_many(
        input_file=empty_to_none(req.get("input_uri")),
        input_list=None,
        local_root=empty_to_none(req.get("local_root")),
        s3_bucket=empty_to_none(req.get("s3_bucket")),
        s3_prefix=empty_to_none(req.get("s3_prefix")),
        site=empty_to_none(site),
        day=empty_to_none(req.get("day")),
        date_from=empty_to_none(req.get("date_from")),
        date_to=empty_to_none(req.get("date_to")),
        window_s=int(req.get("window_seconds")) if req.get("window_seconds") else None,
        stride_s=int(req.get("stride_seconds")) if req.get("stride_seconds") else None,
        s3_key_template=empty_to_none(req.get("s3_key_template")),
        verbose=False,
    )

    include_regex = list(req.get("include_regex") or [])
    exclude_regex = list(req.get("exclude_regex") or [])
    drop_cols = list(req.get("drop_cols") or [])
    cols = select_pca_columns(
        df_all,
        include_regex=include_regex,
        exclude_regex=exclude_regex,
        always_exclude=drop_cols,
    )
    if not cols:
        raise ValueError("no PCA columns selected")

    df_fit = df_all
    if bool(req.get("drop_unknown")) and "state_unknown" in df_fit.columns:
        df_fit = df_fit[pd.to_numeric(df_fit["state_unknown"], errors="coerce").fillna(0).astype(int) == 0].copy()
    if "n_rows" in df_fit.columns:
        df_fit = df_fit[pd.to_numeric(df_fit["n_rows"], errors="coerce").fillna(0).astype(int) > 0].copy()
    if len(df_fit) < 2:
        raise ValueError("not enough rows to fit PCA")

    n_components = int(req.get("n_components") or 8)
    standardize = True if req.get("standardize") is None else bool(req.get("standardize"))
    fill_value = float(req.get("fill_value") if req.get("fill_value") is not None else 0.0)
    clip_abs = req.get("clip_abs")
    clip_abs = float(clip_abs) if clip_abs is not None else None
    controls_weight = req.get("controls_weight")
    controls_weight = float(controls_weight) if controls_weight is not None else 1.0

    bundle = fit_pca(
        df_fit,
        cols,
        n_components=n_components,
        whiten=bool(req.get("whiten")),
        standardize=standardize,
        fill_value=fill_value,
        clip_abs=clip_abs,
        controls_weight=controls_weight,
        control_regex=list(req.get("control_regex") or []) or None,
    )

    df_proj, z = transform_pca(
        df_all.copy(),
        bundle,
        fill_value=fill_value,
        clip_abs=clip_abs,
    )

    pca_dir = artifacts_dir / "pca_outputs"
    pca_dir.mkdir(parents=True, exist_ok=True)
    proj_path = pca_dir / "projection.parquet"
    meta_path = pca_dir / "pca_metadata.json"
    model_path = pca_dir / "model.joblib"

    df_proj.to_parquet(proj_path, engine="pyarrow", compression="snappy", index=False)
    meta = {
        "site": site,
        "n_input_rows": int(len(df_all)),
        "n_fit_rows": int(len(df_fit)),
        "n_columns_selected": int(len(cols)),
        "selected_columns": cols,
        "load_meta": load_meta,
        "n_components": int(bundle.pca.n_components_),
        "explained_variance_ratio": [float(x) for x in bundle.pca.explained_variance_ratio_.tolist()],
        "controls_weight": float(bundle.controls_weight),
        "controls_regex": list(bundle.controls_regex),
        "feature_ranges": bundle.feature_ranges,
    }
    write_json(meta_path, meta)

    if joblib is not None:
        joblib.dump(bundle, model_path)

    summary = {
        "n_rows": int(len(df_proj)),
        "n_cols": int(len(df_proj.columns)),
        "n_components": int(z.shape[1]),
        "explained_variance_ratio_sum": float(bundle.pca.explained_variance_ratio_.sum()),
    }

    payload = {"summary": summary, "pca_meta": meta}
    arts = [
        artifact_dict(proj_path, "application/x-parquet"),
        artifact_dict(meta_path, "application/json"),
    ]
    if model_path.exists():
        arts.append(artifact_dict(model_path, "application/octet-stream"))
    return payload, arts


def run_audio_align_plc_job(req: Dict[str, Any], artifacts_dir: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    site = str(req.get("site", "")).strip().lower()
    date_utc = str(req.get("date", "")).strip()
    if not site or not date_utc:
        raise ValueError("audio_align_plc requires site and date")

    audio_bucket = str(req.get("audio_bucket", "")).strip()
    audio_prefix = str(req.get("audio_prefix", "")).strip()
    plc_bucket = str(req.get("plc_bucket", "")).strip()
    plc_prefix = str(req.get("plc_prefix", "")).strip()
    if not audio_bucket or not audio_prefix or not plc_bucket or not plc_prefix:
        raise ValueError("audio_align_plc requires audio_bucket/audio_prefix/plc_bucket/plc_prefix")

    keep_plc_cols = list(req.get("plc_cols") or [])
    out_s3_bucket = str(req.get("out_s3_bucket", "")).strip() or None
    out_s3_prefix = str(req.get("out_s3_prefix", "")).strip() or None

    res = align_audio_partition_to_plc_raw(
        site=site,
        date_utc=date_utc,
        audio_bucket=audio_bucket,
        audio_prefix=audio_prefix,
        plc_bucket=plc_bucket,
        plc_prefix=plc_prefix,
        timestamp_col=(str(req.get("timestamp_col")).strip() if req.get("timestamp_col") else None),
        alignment_offset_ms=float(req.get("alignment_offset_ms") or 0.0),
        keep_plc_cols=keep_plc_cols if keep_plc_cols else None,
        out_dir=str(artifacts_dir),
        out_s3_bucket=out_s3_bucket,
        out_s3_prefix=out_s3_prefix,
    )

    arts = list(res.get("artifacts") or [])
    for up in res.get("uploads") or []:
        arts.append(
            {
                "name": Path(str(up.get("key", ""))).name,
                "path": str(up.get("s3_uri", "")),
                "content_type": str(up.get("content_type", "application/octet-stream")),
                "size_bytes": int(up.get("size_bytes", 0) or 0),
            }
        )
    return res, arts


def artifact_dict(path: Path, content_type: str) -> Dict[str, Any]:
    st = path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "size_bytes": int(st.st_size),
        "content_type": content_type,
    }


def empty_to_none(v: Any) -> Any:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[worker] error: {e}", file=sys.stderr)
        sys.exit(1)
