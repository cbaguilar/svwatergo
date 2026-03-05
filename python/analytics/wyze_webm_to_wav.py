#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


WYZE_WEBM_RE = re.compile(
    r"^(?P<camera>.+?)_(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(?:-\d{3,6})?Z)_chunk=(?P<chunk>\d+)\.webm$",
    re.IGNORECASE,
)
WYZE_WEBM_10S_RE = re.compile(
    r"^(?P<camera>.+?)__(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(?:-\d{3,6})?Z)__(?P<seconds>\d+)s\.webm$",
    re.IGNORECASE,
)
WYZE_WEBM_10S_SINGLE_RE = re.compile(
    r"^(?P<camera>.+?)_(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(?:-\d{3,6})?Z)_(?P<seconds>\d+)s\.webm$",
    re.IGNORECASE,
)
WYZE_WEBM_MS_RE = re.compile(
    r"^(?P<camera>.+?)__(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(?:-\d{3,6})?Z)__(?P<millis>\d+)ms\.webm$",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convert Wyze audio WEBM chunks to WAV and rename files using parseable UTC timestamps."
    )
    p.add_argument("--local-root", required=True, help="Root containing Wyze WEBM files (recurses)")
    p.add_argument("--out-dir", required=True, help="Output root for WAV files and manifest")
    p.add_argument("--site", default="bluerock", help="Site label for metadata")
    p.add_argument("--camera", default="", help="Optional camera override for output filenames/metadata")
    p.add_argument(
        "--timestamp-kind",
        choices=["start", "end"],
        default="start",
        help="Whether the WEBM filename timestamp represents clip start or clip end (Wyze dumps usually use start).",
    )
    p.add_argument(
        "--partition-by",
        choices=["utc_day", "none"],
        default="utc_day",
        help="Partition WAV outputs by computed clip start UTC day",
    )
    p.add_argument("--sample-rate", type=int, default=16000, help="Output WAV sample rate")
    p.add_argument("--channels", type=int, default=1, choices=[1, 2], help="Output WAV channels")
    p.add_argument("--min-size-bytes", type=int, default=4096, help="Skip WEBM files smaller than this size (default 4 KB)")
    p.add_argument(
        "--pcm-codec",
        default="pcm_s16le",
        choices=["pcm_s16le", "pcm_s24le", "pcm_f32le"],
        help="FFmpeg WAV audio codec",
    )
    p.add_argument("--skip-existing", action="store_true", help="Skip conversion when output WAV already exists")
    p.add_argument("--dry-run", action="store_true", help="Plan only; do not run ffmpeg")
    p.add_argument(
        "--assume-duration-seconds",
        type=float,
        default=10.0,
        help="Fallback duration used only for dry-run rows when ffprobe has no duration metadata.",
    )
    p.add_argument("--limit-files", type=int, default=0, help="Process at most N WEBM files")
    p.add_argument("--progress-every", type=int, default=200, help="Print progress every N files")
    p.add_argument("--write-csv", action="store_true", help="Also write CSV manifest (default: parquet only)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    in_root = Path(args.local_root)
    out_root = Path(args.out_dir)
    if not in_root.exists():
        raise SystemExit(f"--local-root not found: {in_root}")
    if int(args.sample_rate) <= 0:
        raise SystemExit("--sample-rate must be > 0")

    webms = sorted(in_root.rglob("*.webm"))
    if args.limit_files:
        webms = webms[: int(args.limit_files)]
    if not webms:
        raise SystemExit("No WEBM files found.")

    site = str(args.site).strip().lower()
    print(
        "[start] wyze_webm_to_wav "
        f"files={len(webms)} site={site} timestamp_kind={args.timestamp_kind} "
        f"sample_rate={int(args.sample_rate)} channels={int(args.channels)} "
        f"min_size_bytes={int(args.min_size_bytes)} "
        f"partition_by={args.partition_by} skip_existing={bool(args.skip_existing)} dry_run={bool(args.dry_run)}",
        flush=True,
    )

    rows: List[Dict[str, Any]] = []
    seen = converted = skipped_existing = skipped_parse = skipped_small = failed = 0
    for src in webms:
        seen += 1
        size_bytes = int(src.stat().st_size)
        if size_bytes < int(args.min_size_bytes):
            skipped_small += 1
            print(f"[skip] too small ({size_bytes}B < {int(args.min_size_bytes)}B): {src.name}", flush=True)
            continue
        parsed = parse_wyze_webm_filename(src.name)
        if parsed is None:
            skipped_parse += 1
            print(f"[skip] unparsed wyze filename: {src.name}", flush=True)
            continue
        camera_name, ts_raw, chunk_idx = parsed
        camera_name = str(args.camera).strip() or camera_name

        try:
            ts_nominal = parse_wyze_ts_label(ts_raw)
        except Exception as e:
            skipped_parse += 1
            print(f"[skip] bad timestamp {src.name}: {e}", flush=True)
            continue

        probe_err = ""
        try:
            dur_probe = probe_duration_seconds(src)
        except Exception as e:
            dur_probe = None
            probe_err = str(e)

        if args.dry_run:
            dur_s = float(dur_probe if dur_probe is not None else args.assume_duration_seconds)
            if dur_probe is None:
                print(
                    f"[warn] ffprobe no duration for {src.name}; using --assume-duration-seconds={dur_s}",
                    flush=True,
                )
            clip_start, clip_end = compute_clip_bounds(ts_nominal, dur_s=dur_s, timestamp_kind=str(args.timestamp_kind))
            out_rel = build_output_relpath(
                camera=camera_name,
                clip_start=clip_start,
                clip_end=clip_end,
                chunk_idx=chunk_idx,
                partition_by=str(args.partition_by),
            )
            rows.append(
                build_manifest_row(
                    site=site,
                    camera=camera_name,
                    src=src,
                    chunk_idx=chunk_idx,
                    ts_raw=ts_raw,
                    timestamp_kind=str(args.timestamp_kind),
                    clip_start=clip_start,
                    clip_end=clip_end,
                    dur_s=dur_s,
                    duration_source="ffprobe" if dur_probe is not None else "assumed_dry_run",
                    out_path=(out_root / out_rel),
                    out_rel=out_rel,
                    sample_rate=int(args.sample_rate),
                    channels=int(args.channels),
                    pcm_codec=str(args.pcm_codec),
                    ffprobe_error=probe_err if dur_probe is None else "",
                )
            )
            continue

        if dur_probe is not None:
            dur_s = float(dur_probe)
            clip_start, clip_end = compute_clip_bounds(ts_nominal, dur_s=dur_s, timestamp_kind=str(args.timestamp_kind))
            out_rel = build_output_relpath(
                camera=camera_name,
                clip_start=clip_start,
                clip_end=clip_end,
                chunk_idx=chunk_idx,
                partition_by=str(args.partition_by),
            )
            out_path = out_root / out_rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if args.skip_existing and out_path.exists():
                skipped_existing += 1
                rows.append(
                    build_manifest_row(
                        site=site,
                        camera=camera_name,
                        src=src,
                        chunk_idx=chunk_idx,
                        ts_raw=ts_raw,
                        timestamp_kind=str(args.timestamp_kind),
                        clip_start=clip_start,
                        clip_end=clip_end,
                        dur_s=dur_s,
                        duration_source="ffprobe",
                        out_path=out_path,
                        out_rel=out_rel,
                        sample_rate=int(args.sample_rate),
                        channels=int(args.channels),
                        pcm_codec=str(args.pcm_codec),
                        ffprobe_error="",
                    )
                )
                continue
            try:
                convert_webm_to_wav(
                    src,
                    out_path,
                    sample_rate=int(args.sample_rate),
                    channels=int(args.channels),
                    pcm_codec=str(args.pcm_codec),
                )
                converted += 1
            except Exception as e:
                failed += 1
                print(f"[fail] ffmpeg {src.name}: {e}", flush=True)
                continue
            rows.append(
                build_manifest_row(
                    site=site,
                    camera=camera_name,
                    src=src,
                    chunk_idx=chunk_idx,
                    ts_raw=ts_raw,
                    timestamp_kind=str(args.timestamp_kind),
                    clip_start=clip_start,
                    clip_end=clip_end,
                    dur_s=dur_s,
                    duration_source="ffprobe",
                    out_path=out_path,
                    out_rel=out_rel,
                    sample_rate=int(args.sample_rate),
                    channels=int(args.channels),
                    pcm_codec=str(args.pcm_codec),
                    ffprobe_error="",
                )
            )
        else:
            # No duration in ffprobe metadata (common for some WebM chunks). Convert first,
            # then measure WAV duration and rename using the measured end timestamp.
            tmp_dir = out_root / "_tmp_wav"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / f"{src.stem}.wav"
            try:
                convert_webm_to_wav(
                    src,
                    tmp_path,
                    sample_rate=int(args.sample_rate),
                    channels=int(args.channels),
                    pcm_codec=str(args.pcm_codec),
                )
                dur_s = measure_wav_duration_seconds(tmp_path)
                clip_start, clip_end = compute_clip_bounds(ts_nominal, dur_s=dur_s, timestamp_kind=str(args.timestamp_kind))
                out_rel = build_output_relpath(
                    camera=camera_name,
                    clip_start=clip_start,
                    clip_end=clip_end,
                    chunk_idx=chunk_idx,
                    partition_by=str(args.partition_by),
                )
                out_path = out_root / out_rel
                out_path.parent.mkdir(parents=True, exist_ok=True)
                if args.skip_existing and out_path.exists():
                    skipped_existing += 1
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
                else:
                    tmp_path.replace(out_path)
                    converted += 1
                rows.append(
                    build_manifest_row(
                        site=site,
                        camera=camera_name,
                        src=src,
                        chunk_idx=chunk_idx,
                        ts_raw=ts_raw,
                        timestamp_kind=str(args.timestamp_kind),
                        clip_start=clip_start,
                        clip_end=clip_end,
                        dur_s=dur_s,
                        duration_source="measured_wav",
                        out_path=out_path,
                        out_rel=out_rel,
                        sample_rate=int(args.sample_rate),
                        channels=int(args.channels),
                        pcm_codec=str(args.pcm_codec),
                        ffprobe_error=probe_err,
                    )
                )
            except Exception as e:
                failed += 1
                print(f"[fail] convert/measure {src.name}: {e}", flush=True)
                try:
                    if tmp_path.exists():
                        tmp_path.unlink()
                except Exception:
                    pass
                continue

        if int(args.progress_every) > 0 and (seen % int(args.progress_every) == 0):
            print(
                f"[progress] seen={seen} converted={converted} skip_parse={skipped_parse} "
                f"skip_small={skipped_small} skip_existing={skipped_existing} failed={failed}",
                flush=True,
            )

    manifest_df = pd.DataFrame(rows)
    manifest_base = out_root / "dataset=wyze_webm_wav" / f"site={site}"
    manifest_base.mkdir(parents=True, exist_ok=True)
    manifest_parquet = manifest_base / "wyze_webm_wav_manifest.parquet"
    manifest_csv = manifest_base / "wyze_webm_wav_manifest.csv"
    manifest_meta = manifest_base / "wyze_webm_wav_manifest_metadata.json"
    manifest_df.to_parquet(manifest_parquet, engine="pyarrow", compression="snappy", index=False)
    if args.write_csv:
        manifest_df.to_csv(manifest_csv, index=False)

    meta = {
        "site": site,
        "local_root": str(in_root),
        "out_dir": str(out_root),
        "timestamp_kind": str(args.timestamp_kind),
        "partition_by": str(args.partition_by),
        "sample_rate": int(args.sample_rate),
        "channels": int(args.channels),
        "min_size_bytes": int(args.min_size_bytes),
        "pcm_codec": str(args.pcm_codec),
        "dry_run": bool(args.dry_run),
        "skip_existing": bool(args.skip_existing),
        "n_files_seen": int(seen),
        "n_rows_manifest": int(len(manifest_df)),
        "n_converted": int(converted),
        "n_skipped_existing": int(skipped_existing),
        "n_skipped_parse": int(skipped_parse),
        "n_skipped_small": int(skipped_small),
        "n_failed": int(failed),
        "write_csv": bool(args.write_csv),
    }
    manifest_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        f"[done] seen={seen} converted={converted} skipped_existing={skipped_existing} "
        f"skipped_parse={skipped_parse} skipped_small={skipped_small} failed={failed}",
        flush=True,
    )
    print(f"[OK] wrote {manifest_parquet} rows={len(manifest_df)}")
    if args.write_csv:
        print(f"[OK] wrote {manifest_csv}")
    print(f"[OK] wrote {manifest_meta}")


def parse_wyze_webm_filename(name: str) -> Optional[Tuple[str, str, int]]:
    m = WYZE_WEBM_RE.match(name)
    if m:
        camera = str(m.group("camera"))
        ts_raw = str(m.group("ts"))
        chunk_idx = int(m.group("chunk"))
        return camera, ts_raw, chunk_idx

    # Alternate naming used by browser capture output:
    # camera_5__2026-03-01T23-31-53-598Z__10s.webm
    m2 = WYZE_WEBM_10S_RE.match(name)
    if m2:
        camera = str(m2.group("camera"))
        ts_raw = str(m2.group("ts"))
        # No explicit chunk id in this filename style.
        return camera, ts_raw, 0

    m3 = WYZE_WEBM_MS_RE.match(name)
    if m3:
        camera = str(m3.group("camera"))
        ts_raw = str(m3.group("ts"))
        # No explicit chunk id in this filename style.
        return camera, ts_raw, 0

    # Another observed naming pattern:
    # Pryor_Farms_3_behind_ro__2026-02-28T04-19-26-682Z_10s.webm
    m4 = WYZE_WEBM_10S_SINGLE_RE.match(name)
    if m4:
        camera = str(m4.group("camera"))
        ts_raw = str(m4.group("ts"))
        # No explicit chunk id in this filename style.
        return camera, ts_raw, 0

    # Defensive fallback for variants like:
    #   <camera>__<ts>__10s.webm
    #   <camera>__<ts>__10000ms.webm
    #   <camera>_<ts>_10s.webm
    # where camera can contain underscores and minor producer changes.
    lower = name.lower()
    if lower.endswith(".webm"):
        stem = name[:-5]
        parts = stem.split("__")
        if len(parts) >= 3:
            camera = "__".join(parts[:-2]).strip("_")
            ts_raw = parts[-2].strip()
            tail = parts[-1].strip().lower()
            if _looks_like_wyze_ts(ts_raw) and (tail.endswith("s") or tail.endswith("ms")):
                return camera, ts_raw, 0

        parts = stem.rsplit("_", 2)
        if len(parts) == 3:
            camera, ts_raw, tail = parts
            if _looks_like_wyze_ts(ts_raw) and tail.lower().endswith("s"):
                return camera.strip("_"), ts_raw.strip(), 0
    return None


def _looks_like_wyze_ts(ts_raw: str) -> bool:
    return bool(
        re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(?:-\d{3,6})?Z$",
            str(ts_raw).strip(),
            re.IGNORECASE,
        )
    )


def compute_clip_bounds(ts_nominal: pd.Timestamp, *, dur_s: float, timestamp_kind: str) -> Tuple[pd.Timestamp, pd.Timestamp]:
    if timestamp_kind == "start":
        clip_start = ts_nominal
        clip_end = clip_start + pd.to_timedelta(float(dur_s), unit="s")
    else:
        clip_end = ts_nominal
        clip_start = clip_end - pd.to_timedelta(float(dur_s), unit="s")
    return pd.Timestamp(clip_start), pd.Timestamp(clip_end)


def parse_wyze_ts_label(label: str) -> pd.Timestamp:
    # Supports 2026-02-25T15-07-21-672Z or 2026-02-25T15-07-21-672000Z
    m = re.match(
        r"^(?P<d>\d{4}-\d{2}-\d{2})T(?P<h>\d{2})-(?P<m>\d{2})-(?P<s>\d{2})(?:-(?P<frac>\d{3,6}))?Z$",
        label,
        re.IGNORECASE,
    )
    if not m:
        raise ValueError(f"unsupported Wyze timestamp label: {label}")
    frac = m.group("frac") or "000000"
    frac = (frac + "000000")[:6]
    iso = f"{m.group('d')}T{m.group('h')}:{m.group('m')}:{m.group('s')}.{frac}Z"
    ts = pd.to_datetime(iso, utc=True, errors="raise")
    return pd.Timestamp(ts)


def probe_duration_seconds(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise RuntimeError("ffprobe not found. Install ffmpeg.")
    if res.returncode != 0:
        raise RuntimeError((res.stderr or "").strip() or f"ffprobe exit={res.returncode}")
    try:
        val = float((res.stdout or "").strip())
    except Exception as e:
        raise RuntimeError(f"could not parse ffprobe duration: {res.stdout!r}") from e
    if not (val > 0):
        raise RuntimeError(f"non-positive duration from ffprobe: {val}")
    return float(val)


def measure_wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        n = int(wf.getnframes())
        sr = int(wf.getframerate())
    if sr <= 0:
        raise RuntimeError(f"bad wav sample rate: {sr}")
    if n <= 0:
        raise RuntimeError(f"bad wav frame count: {n}")
    return float(n) / float(sr)


def convert_webm_to_wav(
    src: Path,
    dst: Path,
    *,
    sample_rate: int,
    channels: int,
    pcm_codec: str,
) -> None:
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


def build_manifest_row(
    *,
    site: str,
    camera: str,
    src: Path,
    chunk_idx: int,
    ts_raw: str,
    timestamp_kind: str,
    clip_start: pd.Timestamp,
    clip_end: pd.Timestamp,
    dur_s: float,
    duration_source: str,
    out_path: Path,
    out_rel: Path,
    sample_rate: int,
    channels: int,
    pcm_codec: str,
    ffprobe_error: str,
) -> Dict[str, Any]:
    # Include "segment_*" compatibility columns so downstream mel generation can
    # treat each converted WAV as a pre-windowed segment (e.g. 10s Wyze chunks).
    return {
        "site": site,
        "camera": camera,
        "source_webm_path": str(src),
        "source_webm_name": src.name,
        "source_webm_chunk_index": int(chunk_idx),
        "source_filename_ts_raw": ts_raw,
        "source_filename_timestamp_kind": str(timestamp_kind),
        "clip_start_ts_utc": clip_start.isoformat(),
        "clip_end_ts_utc": clip_end.isoformat(),
        "clip_duration_sec": float(dur_s),
        "clip_duration_source": str(duration_source),
        "ffprobe_duration_error": str(ffprobe_error or ""),
        "wav_path": str(out_path),
        "wav_relpath": str(out_rel),
        # Compatibility for audio_mel_segments.py / python.ml.features.audio_mel
        "segment_path": str(out_path),
        "segment_relpath": str(out_rel),
        "segment_start_ts_utc": clip_start.isoformat(),
        "segment_end_ts_utc": clip_end.isoformat(),
        "segment_duration_sec": float(dur_s),
        "source_path": str(src),
        "source_name": src.name,
        "source_clip_start_ts_utc": clip_start.isoformat(),
        "source_clip_end_ts_utc": clip_end.isoformat(),
        "segment_index": 0,
        "out_sample_rate": int(sample_rate),
        "out_channels": int(channels),
        "out_pcm_codec": str(pcm_codec),
    }


def build_output_relpath(
    *,
    camera: str,
    clip_start: pd.Timestamp,
    clip_end: pd.Timestamp,
    chunk_idx: int,
    partition_by: str,
) -> Path:
    end_label = safe_ts_label(clip_end)
    fname = f"{camera}_{end_label}_chunk={int(chunk_idx):06d}.wav"
    if partition_by == "utc_day":
        day = pd.Timestamp(clip_start).tz_convert("UTC").strftime("%Y-%m-%d")
        return Path(f"camera={camera}") / f"date={day}" / fname
    return Path(fname)


def safe_ts_label(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H-%M-%S.%fZ")


if __name__ == "__main__":
    main()
