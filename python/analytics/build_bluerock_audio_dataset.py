#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

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
        from python.analytics.window_features.pipeline import generate_window_features_for_df  # type: ignore
        return generate_window_features_for_df
    except Exception:
        repo_root = Path(__file__).resolve().parents[2]
        repo_root_str = str(repo_root)
        if repo_root_str not in sys.path:
            sys.path.insert(0, repo_root_str)
        from python.analytics.window_features.pipeline import generate_window_features_for_df  # type: ignore
        return generate_window_features_for_df


EPOCH_WAV_RE = re.compile(r"^bluerock_(?P<epoch>\d+(?:\.\d+)?)\.wav$", re.IGNORECASE)

BLUEROCK_WYZE_CAMERAS = {
    "Bluerock_Cam_1",
    "Bluerock_Cam_2",
    "camera_5",
}


@dataclass(frozen=True)
class SourceDay:
    source: str
    day: str
    segments_manifest: Path
    segments_root: Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Build BLUEROCK_AUDIO_DATASET from local rpi_audio + wyze_dump, generate 10s mels, "
            "and join per-slice 10s PLC window features from local daily PLC parquets."
        )
    )
    p.add_argument("--site", default="bluerock", choices=["bluerock"], help="Site to build (currently bluerock)")
    p.add_argument("--raw-root", default="/mnt/d/datasets/svwatergo/raw", help="Root with plc/, rpi_audio/, wyze_dump/")
    p.add_argument("--out-root", default="/mnt/d/datasets/svwatergo/derived", help="Output root")
    p.add_argument("--plc-root", default="", help="PLC root (defaults to <raw-root>/plc)")
    p.add_argument("--plc-fallback-root", default="", help="Optional fallback PLC root (e.g. <raw-root>/s3_data)")
    p.add_argument("--rpi-root", default="", help="RPI audio root (defaults to <raw-root>/rpi_audio/bluerock)")
    p.add_argument("--wyze-root", default="", help="Wyze dump root (defaults to <raw-root>/wyze_dump)")
    p.add_argument("--include-rpi", action="store_true", help="Include rpi_audio source")
    p.add_argument("--include-wyze", action="store_true", help="Include wyze sources")
    p.add_argument("--date", action="append", default=[], help="Limit to YYYY-MM-DD (repeatable)")
    p.add_argument("--sample-rate", type=int, default=16000)
    p.add_argument("--target-seconds", type=float, default=10.0)
    p.add_argument("--window-seconds", type=int, default=10)
    p.add_argument("--stride-seconds", type=int, default=10)
    p.add_argument("--max-gap-stale-s", type=float, default=300.0)
    p.add_argument("--target-state", action="append", default=[], help="Interesting PLC boolean/discrete states (repeatable)")
    p.add_argument("--skip-existing", action="store_true")
    p.add_argument("--skip-wyze-conversion", action="store_true", help="Assume wyze wav manifests already exist")
    p.add_argument("--dry-run", action="store_true", help="Plan only")
    return p.parse_args()


def _safe_name(s: str) -> str:
    out = re.sub(r"[^A-Za-z0-9._-]+", "_", str(s).strip())
    out = re.sub(r"_+", "_", out).strip("_")
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


def _parse_rpi_wav_row(path: Path, *, target_seconds: float) -> Optional[Dict[str, object]]:
    m = EPOCH_WAV_RE.match(path.name)
    if m is None:
        return None
    epoch = float(m.group("epoch"))
    end_ts = pd.to_datetime(epoch, unit="s", utc=True)
    start_ts = end_ts - pd.Timedelta(seconds=float(target_seconds))
    return {
        "site": "bluerock",
        "camera": "rpi_audio",
        "audio_source": "rpi_audio",
        "source_name": path.name,
        "segment_path": str(path),
        "segment_relpath": path.name,
        "segment_start_ts_utc": start_ts.isoformat(),
        "segment_end_ts_utc": end_ts.isoformat(),
        "segment_duration_sec": float(target_seconds),
        "source_path": str(path),
        "source_clip_start_ts_utc": start_ts.isoformat(),
        "source_clip_end_ts_utc": end_ts.isoformat(),
        "segment_index": 0,
    }


def build_rpi_manifests(
    *,
    rpi_root: Path,
    out_root: Path,
    target_seconds: float,
    date_filter: Optional[set[str]],
    dry_run: bool,
) -> List[SourceDay]:
    if not rpi_root.exists():
        print(f"[skip] rpi root not found: {rpi_root}", flush=True)
        return []

    by_day: Dict[str, List[Dict[str, object]]] = {}
    wavs = sorted(rpi_root.glob("*.wav"))
    for wav in wavs:
        row = _parse_rpi_wav_row(wav, target_seconds=target_seconds)
        if row is None:
            continue
        day = pd.to_datetime(row["segment_start_ts_utc"], utc=True).strftime("%Y-%m-%d")
        if date_filter and day not in date_filter:
            continue
        by_day.setdefault(day, []).append(row)

    out: List[SourceDay] = []
    for day, rows in sorted(by_day.items()):
        manifest = out_root / "intermediate" / "segments" / "source=rpi_audio" / f"date={day}" / "segments_manifest.parquet"
        if dry_run:
            print(f"[plan] rpi day={day} rows={len(rows)} manifest={manifest}", flush=True)
        else:
            manifest.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(rows).to_parquet(manifest, index=False)
            print(f"[ok] rpi manifest day={day} rows={len(rows)} -> {manifest}", flush=True)
        out.append(SourceDay(source="rpi_audio", day=day, segments_manifest=manifest, segments_root=rpi_root))
    return out


def _camera_to_site(camera: str) -> Optional[str]:
    if camera in BLUEROCK_WYZE_CAMERAS:
        return "bluerock"
    if camera.startswith("Pryor_"):
        return "pryorfarm"
    if camera.startswith("Santa_Teresa"):
        return "santateresa"
    return None


def convert_wyze_to_wav_for_day(
    *,
    repo_root: Path,
    local_root: Path,
    out_dir: Path,
    camera: str,
    site: str,
    sample_rate: int,
    skip_existing: bool,
    dry_run: bool,
) -> Path:
    script = repo_root / "python" / "analytics" / "wyze_webm_to_wav.py"
    cmd = [
        sys.executable,
        str(script),
        "--local-root",
        str(local_root),
        "--out-dir",
        str(out_dir),
        "--site",
        str(site),
        "--camera",
        str(camera),
        "--timestamp-kind",
        "start",
        "--sample-rate",
        str(int(sample_rate)),
        "--channels",
        "1",
        "--min-size-bytes",
        "1024",
    ]
    if skip_existing:
        cmd.append("--skip-existing")
    if dry_run:
        print("[plan] " + " ".join(cmd), flush=True)
    else:
        print("[run] " + " ".join(cmd), flush=True)
        subprocess.run(cmd, check=True)
    return out_dir / "dataset=wyze_webm_wav" / f"site={site}" / "wyze_webm_wav_manifest.parquet"


def build_wyze_manifests(
    *,
    repo_root: Path,
    wyze_root: Path,
    out_root: Path,
    site: str,
    sample_rate: int,
    skip_existing: bool,
    skip_conversion: bool,
    date_filter: Optional[set[str]],
    dry_run: bool,
) -> List[SourceDay]:
    if not wyze_root.exists():
        print(f"[skip] wyze root not found: {wyze_root}", flush=True)
        return []

    out: List[SourceDay] = []
    for cam_dir in sorted(wyze_root.glob("camera=*")):
        if not cam_dir.is_dir():
            continue
        camera = cam_dir.name.split("=", 1)[1]
        cam_site = _camera_to_site(camera)
        if cam_site != site:
            continue
        src_name = f"wyze_{_safe_name(camera)}"
        for day_dir in sorted(cam_dir.glob("date=*")):
            if not day_dir.is_dir():
                continue
            day = day_dir.name.split("=", 1)[1]
            if date_filter and day not in date_filter:
                continue
            wav_out = out_root / "intermediate" / "wyze_wav" / f"source={src_name}" / f"date={day}"
            manifest = wav_out / "dataset=wyze_webm_wav" / f"site={site}" / "wyze_webm_wav_manifest.parquet"
            if skip_conversion:
                if not manifest.exists():
                    print(f"[skip] wyze manifest missing (skip-conversion set): {manifest}", flush=True)
                    continue
            else:
                manifest = convert_wyze_to_wav_for_day(
                    repo_root=repo_root,
                    local_root=day_dir,
                    out_dir=wav_out,
                    camera=camera,
                    site=site,
                    sample_rate=sample_rate,
                    skip_existing=skip_existing,
                    dry_run=dry_run,
                )
            out.append(SourceDay(source=src_name, day=day, segments_manifest=manifest, segments_root=wav_out))
    return out


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


def _window_features_for_day(
    *,
    generate_window_features_for_df,
    plc_roots: Sequence[Path],
    site: str,
    day: str,
    window_seconds: int,
    stride_seconds: int,
    max_gap_stale_s: float,
) -> Optional[pd.DataFrame]:
    plc_df = _read_plc_day(plc_roots, site=site, day=day)
    if plc_df is None:
        print(f"[skip] plc day parquet not found for site={site} day={day}", flush=True)
        return None
    feat, _meta, _report = generate_window_features_for_df(
        site=site,
        day=day,
        df=plc_df,
        source="local",
        timestamp_col=None,
        window_seconds=int(window_seconds),
        stride_seconds=int(stride_seconds),
        max_gap_stale_s=float(max_gap_stale_s),
    )
    feat = feat.sort_values("window_start_ts").reset_index(drop=True)
    feat["window_start_ts"] = pd.to_datetime(feat["window_start_ts"], utc=True, errors="coerce")
    feat["window_end_ts"] = pd.to_datetime(feat["window_end_ts"], utc=True, errors="coerce")
    return feat


def _join_mel_with_window_features(mel_df: pd.DataFrame, win_df: pd.DataFrame) -> pd.DataFrame:
    df = mel_df.copy()
    df["segment_start_ts_utc"] = pd.to_datetime(df["segment_start_ts_utc"], utc=True, errors="coerce")
    df["segment_end_ts_utc"] = pd.to_datetime(df["segment_end_ts_utc"], utc=True, errors="coerce")
    df = df[df["segment_start_ts_utc"].notna() & df["segment_end_ts_utc"].notna()].copy()
    df["segment_mid_ts_utc"] = df["segment_start_ts_utc"] + ((df["segment_end_ts_utc"] - df["segment_start_ts_utc"]) / 2)
    df["__rowid"] = range(len(df))

    right = win_df.sort_values("window_start_ts").copy()
    left = df.sort_values("segment_mid_ts_utc").copy()

    merged = pd.merge_asof(
        left,
        right,
        left_on="segment_mid_ts_utc",
        right_on="window_start_ts",
        direction="backward",
    )

    ok = merged["window_start_ts"].notna() & merged["window_end_ts"].notna() & (merged["segment_mid_ts_utc"] < merged["window_end_ts"])
    merged["window_match_found"] = ok.astype("int8")

    win_cols = [c for c in right.columns if c not in ("site", "day")]
    for c in win_cols:
        merged.loc[~ok, c] = pd.NA

    merged = merged.sort_values("__rowid").drop(columns=["__rowid"]).reset_index(drop=True)
    return merged


def _attach_target_aliases(df: pd.DataFrame, target_states: Sequence[str]) -> pd.DataFrame:
    out = df.copy()
    for st in target_states:
        base = str(st).strip().lower()
        if not base:
            continue
        c_last = f"{base}__last"
        c_duty = f"{base}__duty"
        c_trans = f"{base}__transitions"

        if c_last in out.columns:
            out[f"target_{base}_class"] = pd.to_numeric(out[c_last], errors="coerce").round().astype("Int64")
        if c_duty in out.columns:
            out[f"target_{base}_duty"] = pd.to_numeric(out[c_duty], errors="coerce")
        if c_trans in out.columns:
            out[f"target_{base}_transitions"] = pd.to_numeric(out[c_trans], errors="coerce").astype("Int64")
    return out


def _default_target_states() -> List[str]:
    return [
        "ropumprun",
        "feedpumprun",
        "deliveryrun",
        "wellpumprun",
        "runflush",
        "flushrun",
        "alarm",
        "lockout",
        "rostandby",
        "state",
    ]


def main() -> None:
    args = parse_args()
    paths = _resolve_paths(args)

    include_rpi = bool(args.include_rpi)
    include_wyze = bool(args.include_wyze)
    if not include_rpi and not include_wyze:
        include_rpi = True
        include_wyze = True

    date_filter = set(args.date) if args.date else None

    MelSegmentsConfig, generate_mel_segments = _import_ml_audio_mel()
    generate_window_features_for_df = _import_window_features_pipeline()

    repo_root = Path(__file__).resolve().parents[2]
    out_root = paths["out_root"]
    plc_root = paths["plc_root"]
    plc_fallback_root = paths["plc_fallback_root"]
    plc_roots = [plc_root]
    if plc_fallback_root not in plc_roots:
        plc_roots.append(plc_fallback_root)

    source_days: List[SourceDay] = []
    if include_rpi:
        source_days.extend(
            build_rpi_manifests(
                rpi_root=paths["rpi_root"],
                out_root=out_root,
                target_seconds=float(args.target_seconds),
                date_filter=date_filter,
                dry_run=bool(args.dry_run),
            )
        )
    if include_wyze:
        source_days.extend(
            build_wyze_manifests(
                repo_root=repo_root,
                wyze_root=paths["wyze_root"],
                out_root=out_root,
                site=args.site,
                sample_rate=int(args.sample_rate),
                skip_existing=bool(args.skip_existing),
                skip_conversion=bool(args.skip_wyze_conversion),
                date_filter=date_filter,
                dry_run=bool(args.dry_run),
            )
        )

    if not source_days:
        raise SystemExit("No source/day manifests found to process.")

    target_states = list(args.target_state) if args.target_state else _default_target_states()
    win_cache: Dict[str, pd.DataFrame] = {}
    out_index_rows: List[Dict[str, object]] = []

    for sd in sorted(source_days, key=lambda x: (x.day, x.source)):
        if not sd.segments_manifest.exists():
            print(f"[skip] missing segment manifest: {sd.segments_manifest}", flush=True)
            continue

        if sd.day not in win_cache:
            win_df = _window_features_for_day(
                generate_window_features_for_df=generate_window_features_for_df,
                plc_roots=plc_roots,
                site=args.site,
                day=sd.day,
                window_seconds=int(args.window_seconds),
                stride_seconds=int(args.stride_seconds),
                max_gap_stale_s=float(args.max_gap_stale_s),
            )
            if win_df is None:
                continue
            win_cache[sd.day] = win_df
        else:
            win_df = win_cache[sd.day]

        mel_out = out_root / "intermediate" / "mels" / f"source={sd.source}" / f"date={sd.day}"
        mel_manifest = mel_out / "dataset=audio_mel_segments" / f"site={args.site}" / "audio_mel_segments.parquet"

        if args.dry_run:
            print(f"[plan] mel source={sd.source} day={sd.day} from={sd.segments_manifest} -> {mel_manifest}", flush=True)
        else:
            if not (args.skip_existing and mel_manifest.exists()):
                cfg = MelSegmentsConfig(
                    segments_root=sd.segments_root,
                    segments_manifest=str(sd.segments_manifest),
                    out_dir=mel_out,
                    site=args.site,
                    sample_rate=int(args.sample_rate),
                    target_seconds=float(args.target_seconds),
                    shard_size=1024,
                    partition_by="utc_day",
                    skip_existing_shards=bool(args.skip_existing),
                )
                generate_mel_segments(cfg)
            mel_df = pd.read_parquet(mel_manifest)
            mel_df["audio_source"] = sd.source
            mel_df["audio_day"] = sd.day

            joined = _join_mel_with_window_features(mel_df, win_df)
            joined = _attach_target_aliases(joined, target_states)

            out_parquet = (
                out_root
                / "dataset=bluerock_audio_dataset"
                / f"window_s={int(args.window_seconds)}"
                / "site=bluerock"
                / f"audio_source={sd.source}"
                / f"date={sd.day}"
                / "audio_dataset.parquet"
            )
            out_parquet.parent.mkdir(parents=True, exist_ok=True)
            joined.to_parquet(out_parquet, index=False)

            meta_path = out_parquet.with_name("audio_dataset_metadata.json")
            meta = {
                "site": args.site,
                "audio_source": sd.source,
                "day": sd.day,
                "window_seconds": int(args.window_seconds),
                "stride_seconds": int(args.stride_seconds),
                "target_seconds": float(args.target_seconds),
                "sample_rate": int(args.sample_rate),
                "target_states": target_states,
                "segments_manifest": str(sd.segments_manifest),
                "mel_manifest": str(mel_manifest),
                "n_rows": int(len(joined)),
                "n_window_matched": int(joined["window_match_found"].sum()) if "window_match_found" in joined.columns else 0,
            }
            meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"[ok] dataset source={sd.source} day={sd.day} rows={len(joined)} -> {out_parquet}", flush=True)

            out_index_rows.append(
                {
                    "site": args.site,
                    "audio_source": sd.source,
                    "day": sd.day,
                    "dataset_parquet": str(out_parquet),
                    "metadata_json": str(meta_path),
                    "rows": int(len(joined)),
                }
            )

    if args.dry_run:
        print("[done] dry-run complete", flush=True)
        return

    if out_index_rows:
        index_path = out_root / "dataset=bluerock_audio_dataset" / "dataset_index.parquet"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(out_index_rows).sort_values(["day", "audio_source"]).to_parquet(index_path, index=False)
        print(f"[ok] dataset index -> {index_path}", flush=True)
    else:
        print("[warn] no dataset partitions written", flush=True)


if __name__ == "__main__":
    main()
