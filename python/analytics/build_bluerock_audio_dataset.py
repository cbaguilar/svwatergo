#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def _import_ml_audio_mel():
    try:
        from python.ml.features.audio_mel import MelSegmentsConfig, generate_mel_segments  # type: ignore

        return MelSegmentsConfig, generate_mel_segments
    except Exception:
        repo_root = Path(__file__).resolve().parents[2]
        repo_root_str = str(repo_root)
        if repo_root_str not in sys.path:
            sys.path.insert(0, repo_root_str)
        from python.ml.features.audio_mel import MelSegmentsConfig, generate_mel_segments  # type: ignore

        return MelSegmentsConfig, generate_mel_segments


def _import_window_features_pipeline():
    try:
        from python.analytics.window_features.pipeline import generate_window_features_for_intervals_df  # type: ignore

        return generate_window_features_for_intervals_df
    except Exception:
        repo_root = Path(__file__).resolve().parents[2]
        repo_root_str = str(repo_root)
        if repo_root_str not in sys.path:
            sys.path.insert(0, repo_root_str)
        from python.analytics.window_features.pipeline import generate_window_features_for_intervals_df  # type: ignore

        return generate_window_features_for_intervals_df


BLUEROCK_WYZE_CAMERAS = ["Bluerock_Cam_1", "Bluerock_Cam_2", "camera_5"]


@dataclass(frozen=True)
class SourceDay:
    site: str
    audio_source: str
    camera: str
    day: str
    wav_root: Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Build site audio event dataset: convert/segment WAVs, join PLC interval features, "
            "label event classes, generate mel spectrograms, and emit train/test/val splits."
        )
    )
    p.add_argument("--site", default="bluerock", help="Site label (e.g. bluerock, santateresa, pryorfarm)")
    p.add_argument("--raw-root", default="/mnt/d/datasets/svwatergo/raw", help="Root with plc/, rpi_audio/, wyze_dump/")
    p.add_argument("--out-root", default="/mnt/d/datasets/svwatergo/derived", help="Output root")
    p.add_argument("--plc-root", default="", help="PLC root (default: <raw-root>/plc)")
    p.add_argument("--plc-fallback-root", default="", help="Optional fallback PLC root")
    p.add_argument("--rpi-root", default="", help="RPI WAV root (default: <raw-root>/rpi_audio/<site>)")
    p.add_argument("--wyze-root", default="", help="Wyze root (default: <raw-root>/wyze_dump)")
    p.add_argument("--include-rpi", action="store_true", help="Include RPI audio source")
    p.add_argument("--include-wyze", action="store_true", help="Include Wyze sources")
    p.add_argument("--wyze-camera", action="append", default=[], help="Limit to specific Wyze camera name (repeatable)")
    p.add_argument("--date", action="append", default=[], help="Limit to YYYY-MM-DD (repeatable)")

    p.add_argument("--sample-rate", type=int, default=16000)
    p.add_argument("--window-seconds", type=float, default=10.0)
    p.add_argument("--stride-seconds", type=float, default=10.0)
    p.add_argument("--max-event-gap-seconds", type=float, default=60.0, help="Max gap to merge adjacent same-class segments into one event window")
    p.add_argument(
        "--max-event-window-seconds",
        type=float,
        default=200.0,
        help="Max duration of a single event window before forcing a new split group (<=0 disables cap)",
    )
    p.add_argument("--max-gap-stale-s", type=float, default=300.0)
    p.add_argument("--wyze-min-size-bytes", type=int, default=4096)
    p.add_argument("--wyze-convert-workers", type=int, default=4, help="Parallel workers for Wyze day conversion")

    p.add_argument("--split-seed", type=int, default=1337)
    p.add_argument("--train-ratio", type=float, default=0.70)
    p.add_argument("--test-ratio", type=float, default=0.15)
    p.add_argument("--val-ratio", type=float, default=0.15)

    p.add_argument("--mel-n-fft", type=int, default=1024)
    p.add_argument("--mel-win-length", type=int, default=1024)
    p.add_argument("--mel-hop-length", type=int, default=256)
    p.add_argument("--mel-n-mels", type=int, default=64)
    p.add_argument("--mel-fmin", type=float, default=20.0)
    p.add_argument("--mel-fmax", type=float, default=8000.0)
    p.add_argument("--mel-power", type=float, default=2.0)
    p.add_argument("--mel-log-eps", type=float, default=1e-10)
    p.add_argument("--mel-dtype", choices=["float16", "float32"], default="float32")
    p.add_argument("--mel-shard-size", type=int, default=1024)

    p.add_argument(
        "--skip-existing",
        dest="skip_existing",
        action="store_true",
        default=True,
        help="Skip converting/rewriting outputs that already exist (default: enabled)",
    )
    p.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help="Disable skip-existing behavior",
    )
    p.add_argument("--skip-wyze-conversion", action="store_true", help="Assume Wyze WAV conversion manifests already exist")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def _safe_name(s: str) -> str:
    out = "".join(ch if (ch.isalnum() or ch in "._-") else "_" for ch in str(s).strip())
    while "__" in out:
        out = out.replace("__", "_")
    out = out.strip("_")
    return out or "unknown"


def _resolve_paths(args: argparse.Namespace) -> Dict[str, Path]:
    raw_root = Path(args.raw_root)
    out_root = Path(args.out_root)
    plc_root = Path(args.plc_root) if args.plc_root else (raw_root / "plc")
    plc_fallback_root = Path(args.plc_fallback_root) if args.plc_fallback_root else (raw_root / "s3_data")
    rpi_root = Path(args.rpi_root) if args.rpi_root else (raw_root / "rpi_audio" / args.site)
    wyze_root = Path(args.wyze_root) if args.wyze_root else (raw_root / "wyze_dump")
    return {
        "raw_root": raw_root,
        "out_root": out_root,
        "plc_root": plc_root,
        "plc_fallback_root": plc_fallback_root,
        "rpi_root": rpi_root,
        "wyze_root": wyze_root,
    }


def _parse_rpi_end_ts(path: Path) -> Optional[pd.Timestamp]:
    name = path.name
    if not name.endswith(".wav"):
        return None
    try:
        stem = name[: -len(".wav")]
        token = stem.rsplit("_", 1)[-1]
        epoch = float(token)
        return pd.to_datetime(epoch, unit="s", utc=True)
    except Exception:
        return None


def _run(cmd: List[str], *, dry_run: bool) -> None:
    if dry_run:
        print("[plan] " + " ".join(cmd), flush=True)
        return
    print("[run] " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def _build_rpi_stage(
    *,
    site: str,
    rpi_root: Path,
    out_root: Path,
    date_filter: Optional[set[str]],
    dry_run: bool,
) -> List[SourceDay]:
    if not rpi_root.exists():
        print(f"[skip] rpi root missing: {rpi_root}", flush=True)
        return []

    by_day: Dict[str, List[Path]] = {}
    for wav in sorted(rpi_root.glob("*.wav")):
        end_ts = _parse_rpi_end_ts(wav)
        if end_ts is None:
            continue
        day = end_ts.tz_convert("UTC").strftime("%Y-%m-%d")
        if date_filter and day not in date_filter:
            continue
        by_day.setdefault(day, []).append(wav)

    out: List[SourceDay] = []
    for day, paths in sorted(by_day.items()):
        stage = out_root / "intermediate" / "rpi_staging" / f"site={site}" / "source=rpi_audio" / f"date={day}"
        if not dry_run:
            stage.mkdir(parents=True, exist_ok=True)
            for src in paths:
                dst = stage / src.name
                if not dst.exists():
                    dst.symlink_to(src)
        out.append(SourceDay(site=site, audio_source="rpi_audio", camera="rpi_audio", day=day, wav_root=stage))
    return out


def _site_default_wyze_cameras(site: str) -> List[str]:
    site_l = site.strip().lower()
    if site_l == "bluerock":
        return BLUEROCK_WYZE_CAMERAS[:]
    return []


def _convert_wyze_day(
    *,
    repo_root: Path,
    day_root: Path,
    out_dir: Path,
    site: str,
    camera: str,
    sample_rate: int,
    min_size_bytes: int,
    skip_existing: bool,
    dry_run: bool,
) -> None:
    cmd = [
        sys.executable,
        str(repo_root / "python" / "analytics" / "wyze_webm_to_wav.py"),
        "--local-root",
        str(day_root),
        "--out-dir",
        str(out_dir),
        "--site",
        site,
        "--camera",
        camera,
        "--timestamp-kind",
        "start",
        "--sample-rate",
        str(int(sample_rate)),
        "--channels",
        "1",
        "--min-size-bytes",
        str(int(min_size_bytes)),
    ]
    if skip_existing:
        cmd.append("--skip-existing")
    _run(cmd, dry_run=dry_run)


def _build_wyze_stage(
    *,
    repo_root: Path,
    site: str,
    wyze_root: Path,
    out_root: Path,
    sample_rate: int,
    min_size_bytes: int,
    date_filter: Optional[set[str]],
    camera_filter: Optional[set[str]],
    skip_existing: bool,
    skip_conversion: bool,
    convert_workers: int,
    dry_run: bool,
) -> List[SourceDay]:
    if not wyze_root.exists():
        print(f"[skip] wyze root missing: {wyze_root}", flush=True)
        return []

    selected = camera_filter if camera_filter else set(_site_default_wyze_cameras(site))
    if not selected:
        # fallback to all camera=* folders if no configured list
        selected = {p.name.split("=", 1)[1] for p in wyze_root.glob("camera=*") if p.is_dir()}

    out: List[SourceDay] = []
    pending_jobs: List[Tuple[str, str, str, Path, Path]] = []
    for camera in sorted(selected):
        cam_dir = wyze_root / f"camera={camera}"
        if not cam_dir.exists():
            print(f"[skip] wyze camera dir missing: {cam_dir}", flush=True)
            continue
        src_name = f"wyze_{_safe_name(camera)}"
        for day_dir in sorted(cam_dir.glob("date=*")):
            if not day_dir.is_dir():
                continue
            day = day_dir.name.split("=", 1)[1]
            if date_filter and day not in date_filter:
                continue
            wav_out = out_root / "intermediate" / "wyze_wav" / f"site={site}" / f"source={src_name}" / f"date={day}"
            manifest = wav_out / "dataset=wyze_webm_wav" / f"site={site}" / "wyze_webm_wav_manifest.parquet"
            if skip_conversion:
                if not manifest.exists():
                    print(f"[skip] expected wyze manifest missing with --skip-wyze-conversion: {manifest}", flush=True)
                    continue
                out.append(SourceDay(site=site, audio_source=src_name, camera=camera, day=day, wav_root=wav_out))
            else:
                pending_jobs.append((src_name, camera, day, day_dir, wav_out))

    if pending_jobs:
        workers = max(1, int(convert_workers))
        if workers == 1:
            for src_name, camera, day, day_dir, wav_out in pending_jobs:
                _convert_wyze_day(
                    repo_root=repo_root,
                    day_root=day_dir,
                    out_dir=wav_out,
                    site=site,
                    camera=camera,
                    sample_rate=sample_rate,
                    min_size_bytes=min_size_bytes,
                    skip_existing=skip_existing,
                    dry_run=dry_run,
                )
                out.append(SourceDay(site=site, audio_source=src_name, camera=camera, day=day, wav_root=wav_out))
        else:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                fut_map = {
                    ex.submit(
                        _convert_wyze_day,
                        repo_root=repo_root,
                        day_root=day_dir,
                        out_dir=wav_out,
                        site=site,
                        camera=camera,
                        sample_rate=sample_rate,
                        min_size_bytes=min_size_bytes,
                        skip_existing=skip_existing,
                        dry_run=dry_run,
                    ): (src_name, camera, day, wav_out)
                    for (src_name, camera, day, day_dir, wav_out) in pending_jobs
                }
                for fut in as_completed(fut_map):
                    src_name, camera, day, wav_out = fut_map[fut]
                    fut.result()
                    out.append(SourceDay(site=site, audio_source=src_name, camera=camera, day=day, wav_root=wav_out))
    return sorted(out, key=lambda x: (x.audio_source, x.day))


def _segment_source_day(
    *,
    repo_root: Path,
    sd: SourceDay,
    out_root: Path,
    site: str,
    window_seconds: float,
    stride_seconds: float,
    skip_existing: bool,
    dry_run: bool,
) -> Path:
    seg_out = out_root / "intermediate" / "segments" / f"site={site}" / f"source={sd.audio_source}" / f"date={sd.day}"
    cmd = [
        sys.executable,
        str(repo_root / "python" / "analytics" / "audio_segment_local.py"),
        "--local-root",
        str(sd.wav_root),
        "--out-dir",
        str(seg_out),
        "--site",
        site,
        "--segment-seconds",
        str(float(window_seconds)),
        "--stride-seconds",
        str(float(stride_seconds)),
        "--min-tail-seconds",
        "0.01",
    ]
    if skip_existing:
        cmd.append("--skip-existing")
    _run(cmd, dry_run=dry_run)
    return seg_out / "dataset=audio_segments" / f"site={site}" / "audio_segments.parquet"


def _read_plc_day(plc_roots: Sequence[Path], *, site: str, day: str) -> Optional[pd.DataFrame]:
    for root in plc_roots:
        cands = [
            root / f"site={site}" / f"date={day}" / "data.parquet",
            root / site / day / "data.parquet",
        ]
        for p in cands:
            if p.exists():
                return pd.read_parquet(p)
    return None


def _window_features_for_segments(
    *,
    generate_window_features_for_intervals_df,
    plc_roots: Sequence[Path],
    site: str,
    day: str,
    seg_df: pd.DataFrame,
    max_gap_stale_s: float,
) -> Optional[pd.DataFrame]:
    plc_df = _read_plc_day(plc_roots, site=site, day=day)
    if plc_df is None:
        print(f"[skip] missing plc day parquet site={site} day={day}", flush=True)
        return None
    feat, _meta, _report = generate_window_features_for_intervals_df(
        site=site,
        day=day,
        df=plc_df,
        interval_start=seg_df["segment_start_ts_utc"],
        interval_end=seg_df["segment_end_ts_utc"],
        source="local",
        timestamp_col=None,
        max_gap_stale_s=float(max_gap_stale_s),
    )
    return feat


def _ts_ns(series: pd.Series) -> np.ndarray:
    return pd.to_datetime(series, utc=True, errors="coerce").astype("int64", copy=False).to_numpy()


def _step_hold_true_and_known_s(
    *,
    ts_ns: np.ndarray,
    vals: np.ndarray,
    w0_ns: int,
    w1_ns: int,
    true_fn,
) -> Tuple[float, float]:
    if w1_ns <= w0_ns:
        return 0.0, 0.0

    i0 = int(np.searchsorted(ts_ns, w0_ns, side="left"))
    i1 = int(np.searchsorted(ts_ns, w1_ns, side="left"))

    cur_t = w0_ns
    cur_v: Optional[float] = None
    if i0 > 0:
        pv = vals[i0 - 1]
        cur_v = float(pv) if np.isfinite(pv) else None

    true_ns = 0
    known_ns = 0

    for j in range(i0, i1):
        t = int(ts_ns[j])
        if t > w1_ns:
            t = w1_ns
        if t > cur_t:
            dt = t - cur_t
            if cur_v is not None:
                known_ns += dt
                if true_fn(cur_v):
                    true_ns += dt
            cur_t = t
        if cur_t >= w1_ns:
            break
        vj = vals[j]
        cur_v = float(vj) if np.isfinite(vj) else None

    if cur_t < w1_ns:
        dt = w1_ns - cur_t
        if cur_v is not None:
            known_ns += dt
            if true_fn(cur_v):
                true_ns += dt

    return float(true_ns) / 1e9, float(known_ns) / 1e9


def _label_segments_with_plc_overlap(
    *,
    plc_df: pd.DataFrame,
    seg_df: pd.DataFrame,
) -> pd.DataFrame:
    if plc_df.empty:
        out = seg_df.copy()
        out["overlap_s_producing"] = 0.0
        out["overlap_s_delivering"] = 0.0
        out["overlap_s_flushing"] = 0.0
        out["overlap_s_quiet"] = 0.0
        out["quiet_full"] = False
        out["primary_class"] = "unknown"
        out["states_seen"] = "unknown"
        out["is_transition_segment"] = False
        out["transition_count"] = 0
        return out

    plc = plc_df.copy()
    plc["plctime"] = pd.to_datetime(plc["plctime"], utc=True, errors="coerce")
    plc = plc[plc["plctime"].notna()].sort_values("plctime")

    ts_ns = plc["plctime"].astype("int64", copy=False).to_numpy()
    ro_vals = pd.to_numeric(plc.get("ropumprun", pd.Series(np.nan, index=plc.index)), errors="coerce").to_numpy(dtype=float)
    de_vals = pd.to_numeric(plc.get("deliveryrun", pd.Series(np.nan, index=plc.index)), errors="coerce").to_numpy(dtype=float)
    st_vals = pd.to_numeric(plc.get("state", pd.Series(np.nan, index=plc.index)), errors="coerce").to_numpy(dtype=float)

    out = seg_df.copy()
    starts_ns = _ts_ns(out["segment_start_ts_utc"])
    ends_ns = _ts_ns(out["segment_end_ts_utc"])

    cls: List[str] = []
    overlap_prod: List[float] = []
    overlap_del: List[float] = []
    overlap_flush: List[float] = []
    overlap_quiet: List[float] = []
    quiet_fulls: List[bool] = []
    states_seen: List[str] = []
    transitions: List[int] = []

    for w0_ns, w1_ns in zip(starts_ns, ends_ns):
        if not np.isfinite(w0_ns) or not np.isfinite(w1_ns) or int(w1_ns) <= int(w0_ns):
            overlap_prod.append(0.0)
            overlap_del.append(0.0)
            overlap_flush.append(0.0)
            overlap_quiet.append(0.0)
            quiet_fulls.append(False)
            cls.append("unknown")
            states_seen.append("unknown")
            transitions.append(0)
            continue

        w0 = int(w0_ns)
        w1 = int(w1_ns)
        window_s = float(w1 - w0) / 1e9

        ro_on_s, ro_known_s = _step_hold_true_and_known_s(
            ts_ns=ts_ns,
            vals=ro_vals,
            w0_ns=w0,
            w1_ns=w1,
            true_fn=lambda v: v >= 0.5,
        )
        de_on_s, de_known_s = _step_hold_true_and_known_s(
            ts_ns=ts_ns,
            vals=de_vals,
            w0_ns=w0,
            w1_ns=w1,
            true_fn=lambda v: v >= 0.5,
        )
        fl_on_s, _fl_known_s = _step_hold_true_and_known_s(
            ts_ns=ts_ns,
            vals=st_vals,
            w0_ns=w0,
            w1_ns=w1,
            true_fn=lambda v: int(round(v)) in {4, 5},
        )

        quiet_full = (ro_known_s >= window_s and de_known_s >= window_s and ro_on_s <= 0.0 and de_on_s <= 0.0)

        has_prod = ro_on_s > 0.0
        has_del = de_on_s > 0.0
        has_flush = fl_on_s > 0.0

        if has_flush:
            label = "flushing"
        elif has_del:
            label = "delivering"
        elif has_prod:
            label = "producing"
        elif quiet_full:
            label = "quiet"
        else:
            label = "unknown"

        seen = []
        if has_flush:
            seen.append("flushing")
        if has_del:
            seen.append("delivering")
        if has_prod:
            seen.append("producing")
        if quiet_full:
            seen.append("quiet")
        if not seen:
            seen.append("unknown")

        overlap_prod.append(float(ro_on_s))
        overlap_del.append(float(de_on_s))
        overlap_flush.append(float(fl_on_s))
        overlap_quiet.append(float(window_s if quiet_full else 0.0))
        quiet_fulls.append(bool(quiet_full))
        cls.append(label)
        states_seen.append("|".join(seen))
        transitions.append(len(seen) - 1 if len(seen) > 1 else 0)

    out["overlap_s_producing"] = overlap_prod
    out["overlap_s_delivering"] = overlap_del
    out["overlap_s_flushing"] = overlap_flush
    out["overlap_s_quiet"] = overlap_quiet
    out["quiet_full"] = quiet_fulls
    out["primary_class"] = cls
    out["states_seen"] = states_seen
    out["is_transition_segment"] = [v > 0 for v in transitions]
    out["transition_count"] = transitions

    # prefer PLC transition count when available
    plc_state_trans_col = "state__transitions"
    if plc_state_trans_col in out.columns:
        out["transition_count"] = pd.to_numeric(out[plc_state_trans_col], errors="coerce").fillna(out["transition_count"]).astype(int)
        out["is_transition_segment"] = out["transition_count"] > 0

    return out


def _attach_event_windows(
    df: pd.DataFrame,
    *,
    max_gap_seconds: float,
    max_window_seconds: float,
) -> pd.DataFrame:
    out = df.copy()
    out["segment_start_ts_utc"] = pd.to_datetime(out["segment_start_ts_utc"], utc=True, errors="coerce")
    out = out.sort_values(["audio_source", "day_utc", "segment_start_ts_utc", "sample_id"]).reset_index(drop=True)

    event_ids: List[str] = []
    last_key: Optional[Tuple[str, str]] = None
    last_class = ""
    last_end: Optional[pd.Timestamp] = None
    window_start: Optional[pd.Timestamp] = None
    idx = -1
    max_window_s = float(max_window_seconds)

    for row in out.itertuples(index=False):
        key = (str(row.audio_source), str(row.day_utc))
        klass = str(row.primary_class)
        start = pd.Timestamp(row.segment_start_ts_utc)
        end = pd.Timestamp(row.segment_end_ts_utc)

        new_window = False
        if key != last_key:
            new_window = True
        elif klass != last_class:
            new_window = True
        elif last_end is None:
            new_window = True
        else:
            gap_s = float((start - last_end).total_seconds())
            if gap_s > float(max_gap_seconds):
                new_window = True
            elif max_window_s > 0 and window_start is not None:
                window_duration_s = float((end - window_start).total_seconds())
                if window_duration_s > max_window_s:
                    new_window = True

        if new_window:
            idx += 1
            window_start = start

        event_ids.append(f"{row.site}/{row.day_utc}/{klass}/{idx:06d}")
        last_key = key
        last_class = klass
        last_end = end

    out["event_window_id"] = event_ids
    return out


def _stable_group_sort_key(key: str, seed: int) -> str:
    return hashlib.sha1(f"{seed}|{key}".encode("utf-8")).hexdigest()


def _split_assign_source_day_event(
    df: pd.DataFrame,
    *,
    seed: int,
    train_ratio: float,
    test_ratio: float,
    val_ratio: float,
) -> pd.DataFrame:
    if df.empty:
        out = df.copy()
        out["split"] = pd.Series([], dtype="string")
        return out

    out = df.copy()
    # Split by event periods (event_window_id), intentionally ignoring source.
    out["split_group_id"] = out["event_window_id"].astype(str)

    grp = (
        out.groupby(["split_group_id"], as_index=False)
        .agg(
            n_rows=("split_group_id", "size"),
            primary_class=("primary_class", "first"),
        )
    )

    # Greedy by large groups first, deterministic tie-break by hash
    grp["_hash"] = grp["split_group_id"].map(lambda s: _stable_group_sort_key(str(s), seed))
    grp = grp.sort_values(["n_rows", "_hash"], ascending=[False, True]).reset_index(drop=True)

    total = int(grp["n_rows"].sum())
    target = {
        "train": max(0, int(round(train_ratio * total))),
        "test": max(0, int(round(test_ratio * total))),
        "val": max(0, int(round(val_ratio * total))),
    }

    current = {"train": 0, "test": 0, "val": 0}
    group_to_split: Dict[str, str] = {}
    class_levels = sorted(grp["primary_class"].astype(str).unique().tolist())
    class_current_rows: Dict[str, Dict[str, int]] = {k: {"train": 0, "test": 0, "val": 0} for k in class_levels}
    class_current_windows: Dict[str, Dict[str, int]] = {k: {"train": 0, "test": 0, "val": 0} for k in class_levels}
    class_target_rows: Dict[str, Dict[str, int]] = {}
    class_target_windows: Dict[str, Dict[str, int]] = {}
    for klass in class_levels:
        c_rows_total = int(grp.loc[grp["primary_class"].astype(str) == klass, "n_rows"].sum())
        c_win_total = int((grp["primary_class"].astype(str) == klass).sum())
        class_target_rows[klass] = {
            "train": max(0, int(round(train_ratio * c_rows_total))),
            "test": max(0, int(round(test_ratio * c_rows_total))),
            "val": max(0, int(round(val_ratio * c_rows_total))),
        }
        class_target_windows[klass] = {
            "train": max(0, int(round(train_ratio * c_win_total))),
            "test": max(0, int(round(test_ratio * c_win_total))),
            "val": max(0, int(round(val_ratio * c_win_total))),
        }

    def _cost_for(
        *,
        klass: str,
        n: int,
        split: str,
        class_window_weight: float = 14.0,
        class_row_weight: float = 2.0,
        global_weight: float = 1.0,
    ) -> float:
        cw_proj = class_current_windows[klass][split] + 1
        cw_over = max(0, cw_proj - class_target_windows[klass][split])
        cw_def = max(0, class_target_windows[klass][split] - cw_proj)
        cw_cost = (cw_over * 2) + cw_def

        cr_proj = class_current_rows[klass][split] + int(n)
        cr_over = max(0, cr_proj - class_target_rows[klass][split])
        cr_def = max(0, class_target_rows[klass][split] - cr_proj)
        cr_cost = (cr_over * 2) + cr_def

        g_proj = current[split] + int(n)
        g_over = max(0, g_proj - target[split])
        g_def = max(0, target[split] - g_proj)
        g_cost = (g_over * 2) + g_def
        return (class_window_weight * cw_cost) + (class_row_weight * cr_cost) + (global_weight * g_cost)

    def _assign_group(gid: str, klass: str, n: int, allowed: Optional[Sequence[str]] = None) -> None:
        if gid in group_to_split:
            return
        choices = list(allowed) if allowed else ["train", "test", "val"]
        best_split = min(choices, key=lambda sp: _cost_for(klass=klass, n=n, split=sp))
        group_to_split[gid] = best_split
        current[best_split] += int(n)
        class_current_rows[klass][best_split] += int(n)
        class_current_windows[klass][best_split] += 1

    # Per-class assignment for stratified class balance across splits.
    for klass in class_levels:
        class_rows = grp[grp["primary_class"].astype(str) == klass].copy()
        if class_rows.empty:
            continue
        # Window-count balancing should not always prioritize largest windows first.
        class_rows = class_rows.sort_values(["_hash"], ascending=[True]).reset_index(drop=True)

        # Coverage seed pass.
        n_groups = int(len(class_rows))
        if n_groups >= 3:
            seed_splits: List[str] = ["train", "test", "val"]
        elif n_groups == 2:
            seed_splits = ["train", "test"]
        else:
            seed_splits = ["train"]
        for i in range(min(len(seed_splits), len(class_rows))):
            row = class_rows.iloc[i]
            _assign_group(
                gid=str(row["split_group_id"]),
                klass=klass,
                n=int(row["n_rows"]),
                allowed=[seed_splits[i]],
            )

        # Balance remaining rows within class.
        for i in range(len(seed_splits), len(class_rows)):
            row = class_rows.iloc[i]
            _assign_group(
                gid=str(row["split_group_id"]),
                klass=klass,
                n=int(row["n_rows"]),
                allowed=None,
            )

    # Safety pass: assign any leftover groups.
    for row in grp.itertuples(index=False):
        gid = str(row.split_group_id)
        if gid in group_to_split:
            continue
        _assign_group(gid=gid, klass=str(row.primary_class), n=int(row.n_rows), allowed=None)

    out["split"] = out["split_group_id"].map(group_to_split).astype("string")
    out["split_seed"] = int(seed)
    out["split_target_train"] = float(train_ratio)
    out["split_target_test"] = float(test_ratio)
    out["split_target_val"] = float(val_ratio)
    return out


def _build_stats(df: pd.DataFrame) -> Dict[str, Any]:
    stats: Dict[str, Any] = {}
    stats["n_rows"] = int(len(df))
    stats["n_sources"] = int(df["audio_source"].nunique()) if "audio_source" in df.columns else 0
    stats["n_days"] = int(df["day_utc"].nunique()) if "day_utc" in df.columns else 0

    by_class = (
        df.groupby(["split", "primary_class"], dropna=False)
        .size()
        .reset_index(name="n_samples")
        .sort_values(["split", "n_samples"], ascending=[True, False])
    )
    stats["by_split_class"] = by_class.to_dict(orient="records")

    by_source = (
        df.groupby(["split", "audio_source"], dropna=False)
        .size()
        .reset_index(name="n_samples")
        .sort_values(["split", "n_samples"], ascending=[True, False])
    )
    stats["by_split_source"] = by_source.to_dict(orient="records")

    return stats


def main() -> None:
    args = parse_args()
    site = str(args.site).strip().lower()
    paths = _resolve_paths(args)

    include_rpi = bool(args.include_rpi)
    include_wyze = bool(args.include_wyze)
    if not include_rpi and not include_wyze:
        include_rpi = True
        include_wyze = True

    date_filter = set(args.date) if args.date else None
    camera_filter = set(args.wyze_camera) if args.wyze_camera else None

    if abs(float(args.train_ratio) + float(args.test_ratio) + float(args.val_ratio) - 1.0) > 1e-6:
        raise SystemExit("--train-ratio + --test-ratio + --val-ratio must equal 1.0")

    repo_root = Path(__file__).resolve().parents[2]
    out_root = paths["out_root"]
    out_dataset_root = out_root / "dataset=audio_event_dataset" / f"site={site}" / f"window_s={int(args.window_seconds)}"

    MelSegmentsConfig, generate_mel_segments = _import_ml_audio_mel()
    generate_window_features_for_intervals_df = _import_window_features_pipeline()

    source_days: List[SourceDay] = []
    if include_rpi:
        source_days.extend(
            _build_rpi_stage(
                site=site,
                rpi_root=paths["rpi_root"],
                out_root=out_root,
                date_filter=date_filter,
                dry_run=bool(args.dry_run),
            )
        )
    if include_wyze:
        source_days.extend(
            _build_wyze_stage(
                repo_root=repo_root,
                site=site,
                wyze_root=paths["wyze_root"],
                out_root=out_root,
                sample_rate=int(args.sample_rate),
                min_size_bytes=int(args.wyze_min_size_bytes),
                date_filter=date_filter,
                camera_filter=camera_filter,
                skip_existing=bool(args.skip_existing),
                skip_conversion=bool(args.skip_wyze_conversion),
                convert_workers=int(args.wyze_convert_workers),
                dry_run=bool(args.dry_run),
            )
        )

    if not source_days:
        raise SystemExit("No source/day inputs found.")

    seg_rows: List[pd.DataFrame] = []
    for sd in sorted(source_days, key=lambda x: (x.audio_source, x.day)):
        seg_manifest = _segment_source_day(
            repo_root=repo_root,
            sd=sd,
            out_root=out_root,
            site=site,
            window_seconds=float(args.window_seconds),
            stride_seconds=float(args.stride_seconds),
            skip_existing=bool(args.skip_existing),
            dry_run=bool(args.dry_run),
        )
        if args.dry_run:
            continue
        if not seg_manifest.exists():
            print(f"[skip] segment manifest missing: {seg_manifest}", flush=True)
            continue

        seg_df = pd.read_parquet(seg_manifest)
        if seg_df.empty:
            continue
        seg_df["site"] = sd.site
        seg_df["audio_source"] = sd.audio_source
        seg_df["camera"] = sd.camera
        seg_df["day_utc"] = sd.day
        seg_rows.append(seg_df)

    if args.dry_run:
        print("[done] dry-run complete", flush=True)
        return

    if not seg_rows:
        raise SystemExit("No segments produced.")

    segments_df = pd.concat(seg_rows, ignore_index=True)
    segments_df["segment_start_ts_utc"] = pd.to_datetime(segments_df["segment_start_ts_utc"], utc=True, errors="coerce")
    segments_df["segment_end_ts_utc"] = pd.to_datetime(segments_df["segment_end_ts_utc"], utc=True, errors="coerce")
    segments_df = segments_df[segments_df["segment_start_ts_utc"].notna() & segments_df["segment_end_ts_utc"].notna()].copy()

    segments_df = segments_df.sort_values(["audio_source", "segment_start_ts_utc", "segment_path"]).reset_index(drop=True)
    segments_df["sample_id"] = [
        hashlib.sha1(f"{r.audio_source}|{r.segment_path}|{r.segment_start_ts_utc}|{r.segment_end_ts_utc}".encode("utf-8")).hexdigest()
        for r in segments_df.itertuples(index=False)
    ]

    # Mel generation for all valid segments
    mel_input_manifest = out_root / "intermediate" / "segments" / f"site={site}" / "segments_all.parquet"
    mel_input_manifest.parent.mkdir(parents=True, exist_ok=True)
    segments_df.to_parquet(mel_input_manifest, index=False)

    mel_out = out_root / "intermediate" / "mels" / f"site={site}" / f"window_s={int(args.window_seconds)}"
    mel_manifest = mel_out / "dataset=audio_mel_segments" / f"site={site}" / "audio_mel_segments.parquet"
    if not (args.skip_existing and mel_manifest.exists()):
        cfg = MelSegmentsConfig(
            segments_root=out_root,
            segments_manifest=str(mel_input_manifest),
            out_dir=mel_out,
            site=site,
            sample_rate=int(args.sample_rate),
            target_seconds=float(args.window_seconds),
            shard_size=int(args.mel_shard_size),
            partition_by="utc_day",
            skip_existing_shards=bool(args.skip_existing),
            n_fft=int(args.mel_n_fft),
            win_length=int(args.mel_win_length),
            hop_length=int(args.mel_hop_length),
            n_mels=int(args.mel_n_mels),
            fmin=float(args.mel_fmin),
            fmax=float(args.mel_fmax),
            power=float(args.mel_power),
            log_eps=float(args.mel_log_eps),
            dtype=str(args.mel_dtype),
        )
        generate_mel_segments(cfg)

    if not mel_manifest.exists():
        raise SystemExit(f"Mel manifest missing: {mel_manifest}")

    mel_df = pd.read_parquet(mel_manifest)
    mel_df["segment_start_ts_utc"] = pd.to_datetime(mel_df["segment_start_ts_utc"], utc=True, errors="coerce")
    mel_df["segment_end_ts_utc"] = pd.to_datetime(mel_df["segment_end_ts_utc"], utc=True, errors="coerce")

    merged = segments_df.merge(
        mel_df[
            [
                "segment_path",
                "segment_start_ts_utc",
                "segment_end_ts_utc",
                "mel_shard_path",
                "mel_shard_relpath",
                "mel_shard_local_index",
                "mel_n_mels",
                "mel_n_frames",
                "mel_dtype",
            ]
        ],
        on=["segment_path", "segment_start_ts_utc", "segment_end_ts_utc"],
        how="left",
    )

    merged["has_mel"] = merged["mel_shard_path"].notna()
    missing_mels = int((~merged["has_mel"]).sum())
    if missing_mels > 0:
        raise SystemExit(f"Missing mel outputs for {missing_mels} segments.")

    # PLC interval features + labeling
    plc_roots = [paths["plc_root"]]
    if paths["plc_fallback_root"] not in plc_roots:
        plc_roots.append(paths["plc_fallback_root"])

    out_rows: List[pd.DataFrame] = []
    for day, day_df in merged.groupby("day_utc", sort=True):
        feat_df = _window_features_for_segments(
            generate_window_features_for_intervals_df=generate_window_features_for_intervals_df,
            plc_roots=plc_roots,
            site=site,
            day=str(day),
            seg_df=day_df,
            max_gap_stale_s=float(args.max_gap_stale_s),
        )
        if feat_df is None:
            continue

        feat_df = feat_df.reset_index(drop=True)
        left = day_df.reset_index(drop=True)
        overlap_cols = set(left.columns).intersection(set(feat_df.columns))
        if overlap_cols:
            feat_df = feat_df.rename(columns={c: f"plc_{c}" for c in overlap_cols})

        joined = pd.concat([left, feat_df], axis=1)

        plc_day_df = _read_plc_day(plc_roots, site=site, day=str(day))
        if plc_day_df is None:
            continue
        labeled = _label_segments_with_plc_overlap(plc_df=plc_day_df, seg_df=joined)
        out_rows.append(labeled)

    if not out_rows:
        raise SystemExit("No rows after PLC join/labeling.")

    samples = pd.concat(out_rows, ignore_index=True)
    samples = _attach_event_windows(
        samples,
        max_gap_seconds=float(args.max_event_gap_seconds),
        max_window_seconds=float(args.max_event_window_seconds),
    )
    samples = _split_assign_source_day_event(
        samples,
        seed=int(args.split_seed),
        train_ratio=float(args.train_ratio),
        test_ratio=float(args.test_ratio),
        val_ratio=float(args.val_ratio),
    )

    # Persist outputs
    out_dataset_root.mkdir(parents=True, exist_ok=True)
    samples_path = out_dataset_root / "samples.parquet"
    split_manifest_path = out_dataset_root / "split_manifest.parquet"
    stats_path = out_dataset_root / "class_stats.json"
    report_path = out_dataset_root / "build_report.json"

    samples.to_parquet(samples_path, index=False)

    split_cols = [
        "sample_id",
        "site",
        "audio_source",
        "camera",
        "day_utc",
        "segment_start_ts_utc",
        "segment_end_ts_utc",
        "primary_class",
        "event_window_id",
        "split_group_id",
        "split",
        "split_seed",
    ]
    split_manifest = samples[[c for c in split_cols if c in samples.columns]].copy()
    split_manifest.to_parquet(split_manifest_path, index=False)

    stats = _build_stats(samples)
    stats_path.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = {
        "site": site,
        "window_seconds": float(args.window_seconds),
        "stride_seconds": float(args.stride_seconds),
        "sample_rate": int(args.sample_rate),
        "wyze_min_size_bytes": int(args.wyze_min_size_bytes),
        "n_sources": int(samples["audio_source"].nunique()),
        "n_days": int(samples["day_utc"].nunique()),
        "n_samples": int(len(samples)),
        "n_missing_mels": int(missing_mels),
        "outputs": {
            "samples_parquet": str(samples_path),
            "split_manifest_parquet": str(split_manifest_path),
            "class_stats_json": str(stats_path),
        },
        "mel_config": {
            "sample_rate": int(args.sample_rate),
            "n_fft": int(args.mel_n_fft),
            "win_length": int(args.mel_win_length),
            "hop_length": int(args.mel_hop_length),
            "n_mels": int(args.mel_n_mels),
            "fmin": float(args.mel_fmin),
            "fmax": float(args.mel_fmax),
            "power": float(args.mel_power),
            "log_eps": float(args.mel_log_eps),
            "dtype": str(args.mel_dtype),
        },
        "split": {
            "seed": int(args.split_seed),
            "train_ratio": float(args.train_ratio),
            "test_ratio": float(args.test_ratio),
            "val_ratio": float(args.val_ratio),
            "max_event_gap_seconds": float(args.max_event_gap_seconds),
            "max_event_window_seconds": float(args.max_event_window_seconds),
            "actual": {
                k: float(v)
                for k, v in (
                    samples["split"].value_counts(normalize=True).sort_index().to_dict().items()
                )
            },
        },
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"[ok] wrote {samples_path} rows={len(samples)}", flush=True)
    print(f"[ok] wrote {split_manifest_path}", flush=True)
    print(f"[ok] wrote {stats_path}", flush=True)
    print(f"[ok] wrote {report_path}", flush=True)


if __name__ == "__main__":
    main()
