#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

try:
    import joblib  # type: ignore
except Exception:
    joblib = None

def _ensure_repo_on_syspath() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


_ensure_repo_on_syspath()

from window_features.pipeline import (
    generate_window_features_for_day,
    write_window_features_outputs,
)
from window_pca.loader import load_many
from window_pca.model import fit_pca, transform_pca
from window_pca.selection import select_pca_columns
from audio_align_plc import align_audio_partition_to_plc_raw
from python.ml.storage.s3 import split_s3_uri, get_s3_bytes
from python.ml.train.audio_pca_svm import (
    load_audio_pca_svm_bundle,
    predict_audio_pca_svm,
    predict_audio_pca_svm_from_bundle,
)
from python.ml.train.audio_tiny_cnn import (
    load_audio_tiny_cnn_bundle,
    predict_audio_tiny_cnn,
    predict_audio_tiny_cnn_from_bundle,
)


_PREDICTOR_CACHE: Dict[str, Tuple[threading.Lock, Any]] = {}
_PREDICTOR_CACHE_GUARD = threading.Lock()


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
        elif job_type == "audio_inference":
            infer_req = spec.get("audio_inference") or {}
            payload, artifacts = run_audio_inference_job(infer_req, artifacts_dir)
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


def run_audio_inference_job(req: Dict[str, Any], artifacts_dir: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    model = req.get("model") or {}
    model_id = str(model.get("model_id", "")).strip()
    model_version = str(model.get("version", "")).strip()
    model_kind = str(model.get("model_kind", "auto")).strip().lower() or "auto"
    model_path = _resolve_audio_model_path(model)
    if not model_path.exists():
        raise ValueError(f"audio_inference model not found: {model_path}")
    if model_kind == "auto":
        model_kind = "tiny_cnn" if model_path.suffix.lower() in (".pt", ".pth") else "pca_svm"
    predict_one = _build_audio_predictor(model_path=model_path, model_kind=model_kind)

    outputs = req.get("outputs") or {}
    want_predictions = bool(outputs.get("predictions", True))
    want_embeddings = bool(outputs.get("embeddings", False))
    want_metadata = bool(outputs.get("metadata", True))

    inputs = list(req.get("inputs") or [])
    if not inputs:
        raise ValueError("audio_inference.inputs is required")

    rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    input_cache_dir = artifacts_dir / "input_cache"
    input_cache_dir.mkdir(parents=True, exist_ok=True)
    normalized_audio_dir = artifacts_dir / "normalized_audio"
    normalized_audio_dir.mkdir(parents=True, exist_ok=True)

    for i, item in enumerate(inputs):
        input_id = str(item.get("input_id", "")).strip() or f"input_{i:04d}"
        src_type = str(item.get("type", "")).strip().lower()
        t_item0 = time.time()
        row: Dict[str, Any] = {
            "input_id": input_id,
            "type": src_type,
            "model_id": model_id,
            "model_version": model_version,
            "model_path": str(model_path),
            "model_kind": model_kind,
            "status": "ok",
            "error": "",
        }

        wav_path: Path | None = None
        if src_type == "local_path":
            p = Path(str(item.get("path", "")).strip())
            row["resolved_uri"] = str(p)
            if not str(p):
                row["status"] = "error"
                row["error"] = "missing local path"
            elif not p.exists():
                row["status"] = "error"
                row["error"] = "local path not found"
            elif not p.is_file():
                row["status"] = "error"
                row["error"] = "local path is not a file"
            else:
                wav_path = p
        elif src_type == "staged_ref":
            staged_ref = str(item.get("staged_ref", "")).strip()
            row["resolved_uri"] = staged_ref
            if not staged_ref:
                row["status"] = "error"
                row["error"] = "missing staged_ref"
            else:
                p = Path(staged_ref)
                if not p.is_absolute():
                    p = (artifacts_dir / "staged" / staged_ref).resolve()
                if not p.exists() or not p.is_file():
                    row["status"] = "error"
                    row["error"] = "staged_ref path not found"
                else:
                    wav_path = p
        elif src_type == "s3_uri":
            uri = str(item.get("uri", "")).strip()
            row["resolved_uri"] = uri
            if not uri.startswith("s3://"):
                row["status"] = "error"
                row["error"] = "bad s3 uri"
            else:
                try:
                    b, k = split_s3_uri(uri)
                    ext = Path(k).suffix or ".wav"
                    dig = hashlib.sha1(uri.encode("utf-8")).hexdigest()[:16]
                    lp = input_cache_dir / f"{input_id}_{dig}{ext}"
                    if not lp.exists():
                        lp.write_bytes(get_s3_bytes(b, k))
                    wav_path = lp
                except Exception as e:
                    row["status"] = "error"
                    row["error"] = f"s3 fetch failed: {e}"
        elif src_type == "upload":
            staged_ref = str(item.get("staged_ref", "")).strip()
            row["resolved_uri"] = staged_ref
            if not staged_ref:
                row["status"] = "error"
                row["error"] = "upload requires staged_ref"
            else:
                p = Path(staged_ref)
                if not p.is_absolute():
                    p = (artifacts_dir / "staged" / staged_ref).resolve()
                if not p.exists() or not p.is_file():
                    row["status"] = "error"
                    row["error"] = "upload staged_ref path not found"
                else:
                    wav_path = p
        else:
            row["status"] = "error"
            row["error"] = f"unsupported input type: {src_type}"

        if row["status"] == "ok" and wav_path is not None:
            try:
                wav_path = _normalize_audio_for_inference(wav_path=wav_path, out_dir=normalized_audio_dir)
                pred = _run_audio_inference_one(
                    model_path=model_path,
                    model_kind=model_kind,
                    wav_path=wav_path,
                    predict_one=predict_one,
                )
                if want_predictions:
                    row["predictions"] = pred
                if want_embeddings:
                    row["embedding"] = _extract_embedding(pred)
                if want_metadata:
                    st = wav_path.stat()
                    row["metadata"] = {
                        "size_bytes": int(st.st_size),
                        "path": str(wav_path),
                        "mel_shape_used": pred.get("mel_shape_used"),
                    }
            except Exception as e:
                row["status"] = "error"
                row["error"] = f"inference failed: {e}"

        row["timing_ms"] = int(round((time.time() - t_item0) * 1000.0))
        if row["status"] != "ok":
            errors.append({"input_id": input_id, "error": row["error"]})
        rows.append(row)

    out_csv = artifacts_dir / "audio_inference_results.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    out_json = artifacts_dir / "audio_inference_results.json"
    write_json(out_json, {"results": rows, "errors": errors})

    payload = {
        "summary": {
            "model_id": model_id,
            "model_version": model_version,
            "model_path": str(model_path),
            "model_kind": model_kind,
            "n_inputs": int(len(rows)),
            "n_ok": int(sum(1 for r in rows if r.get("status") == "ok")),
            "n_error": int(sum(1 for r in rows if r.get("status") != "ok")),
        },
        "results": rows,
        "errors": errors,
    }
    arts = [
        artifact_dict(out_csv, "text/csv"),
        artifact_dict(out_json, "application/json"),
    ]
    return payload, arts


def _resolve_audio_model_path(model: Dict[str, Any]) -> Path:
    explicit = str(model.get("model_path", "") or model.get("model_uri", "")).strip()
    if explicit:
        return Path(explicit)
    model_id = str(model.get("model_id", "")).strip()
    if not model_id:
        raise ValueError("audio_inference.model.model_id or model_path/model_uri required")
    reg_path = str(os.environ.get("ANALYTICS_AUDIO_MODEL_REGISTRY", "")).strip()
    if not reg_path:
        raise ValueError("model_path/model_uri not provided and ANALYTICS_AUDIO_MODEL_REGISTRY not set")
    reg = read_json(Path(reg_path))
    models = reg.get("models") if isinstance(reg, dict) else None
    if not isinstance(models, dict):
        raise ValueError("invalid model registry format: missing models object")
    item = models.get(model_id)
    if isinstance(item, str):
        return Path(item)
    if isinstance(item, dict):
        p = str(item.get("model_path", "") or item.get("model_uri", "")).strip()
        if p:
            return Path(p)
    raise ValueError(f"model_id not found in registry: {model_id}")


def _run_audio_inference_one(
    *,
    model_path: Path,
    model_kind: str,
    wav_path: Path,
    predict_one: Any = None,
) -> Dict[str, Any]:
    if predict_one is not None:
        return predict_one(wav_path)
    kind = str(model_kind).strip().lower()
    if kind == "tiny_cnn":
        return predict_audio_tiny_cnn(model_path=model_path, wav_path=wav_path)
    if kind == "pca_svm":
        return predict_audio_pca_svm(model_path=model_path, wav_path=wav_path)
    raise ValueError(f"unsupported model_kind: {model_kind}")


def _build_audio_predictor(*, model_path: Path, model_kind: str):
    kind = str(model_kind).strip().lower()
    key = f"{kind}|{str(model_path.resolve())}|{int(model_path.stat().st_mtime_ns)}"
    with _PREDICTOR_CACHE_GUARD:
        hit = _PREDICTOR_CACHE.get(key)
        if hit is not None:
            lock, fn = hit
            return _locked_predictor(fn, lock)
        if kind == "tiny_cnn":
            bundle = load_audio_tiny_cnn_bundle(model_path)
            fn = lambda wav_path: predict_audio_tiny_cnn_from_bundle(bundle=bundle, wav_path=wav_path)
        elif kind == "pca_svm":
            bundle = load_audio_pca_svm_bundle(model_path)
            fn = lambda wav_path: predict_audio_pca_svm_from_bundle(bundle=bundle, wav_path=wav_path)
        else:
            raise ValueError(f"unsupported model_kind: {model_kind}")
        lock = threading.Lock()
        _PREDICTOR_CACHE[key] = (lock, fn)
        return _locked_predictor(fn, lock)


def _locked_predictor(fn, lock: threading.Lock):
    def _predict(wav_path: Path) -> Dict[str, Any]:
        with lock:
            return fn(wav_path)

    return _predict


def _extract_embedding(pred: Dict[str, Any]) -> Dict[str, Any]:
    if "pca_projection" in pred and isinstance(pred.get("pca_projection"), list):
        vec = [float(v) for v in (pred.get("pca_projection") or [])]
        return {"dim": int(len(vec)), "vector": vec}
    return {"dim": 0, "vector": []}


def _normalize_audio_for_inference(*, wav_path: Path, out_dir: Path) -> Path:
    # Tiny-CNN/PCA-SVM paths expect WAV-like decoding. For webm/other containers,
    # normalize once to mono PCM WAV using ffmpeg.
    sfx = wav_path.suffix.lower()
    if sfx in (".wav", ".wave"):
        return wav_path
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(f"{str(wav_path)}::{int(wav_path.stat().st_mtime_ns)}".encode("utf-8")).hexdigest()[:16]
    out_wav = out_dir / f"{wav_path.stem}_{digest}.wav"
    if out_wav.exists() and out_wav.stat().st_size > 0:
        return out_wav
    _convert_to_wav_ffmpeg(src=wav_path, dst=out_wav, sample_rate=16000, channels=1, pcm_codec="pcm_s16le")
    return out_wav


def _convert_to_wav_ffmpeg(
    *,
    src: Path,
    dst: Path,
    sample_rate: int,
    channels: int,
    pcm_codec: str,
) -> None:
    # Mirrors existing conversion logic in analytics/wyze_webm_to_wav.py.
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-ac",
        str(int(channels)),
        "-ar",
        str(int(sample_rate)),
        "-acodec",
        str(pcm_codec),
        str(dst),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install ffmpeg.")
    if res.returncode != 0:
        raise RuntimeError((res.stderr or "").strip() or f"ffmpeg exit={res.returncode}")


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
