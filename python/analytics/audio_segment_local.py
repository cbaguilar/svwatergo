#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import soundfile as sf  # type: ignore
except Exception:
    sf = None

try:
    from scipy.io import wavfile  # type: ignore
except Exception:
    wavfile = None


# Epoch fallback should stay strict (immediately before .wav) so filenames like
# ..._chunk=000123.wav do not get misread as epoch timestamps.
FILENAME_EPOCH_RE = re.compile(r"(\d+(?:\.\d+)?)(?=\.wav$)", re.IGNORECASE)
FILENAME_ISO_RE = re.compile(
    # Allow timestamp anywhere in the basename (not only immediately before .wav),
    # e.g. camera_5_2026-02-25T15-07-31.632000Z_chunk=000001.wav
    r"(?P<iso>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}-\d{2}))",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Chop local 10s WAV clips into shorter windows and emit a segment manifest."
    )
    p.add_argument("--local-root", required=True, help="Input root containing source WAVs")
    p.add_argument("--out-dir", required=True, help="Output root for segmented WAVs + manifest")
    p.add_argument(
        "--manifest-out-dir",
        default="",
        help="Optional separate root for manifest outputs (defaults to --out-dir)",
    )
    p.add_argument("--site", default="bluerock", help="Site label used in output metadata/filenames")
    p.add_argument("--segment-seconds", type=float, default=3.0, help="Segment length (e.g. 3 or 4)")
    p.add_argument("--stride-seconds", type=float, default=1.0, help="Stride between segment starts")
    p.add_argument(
        "--drop-short-tail",
        action="store_true",
        help="Drop final partial segment shorter than segment-seconds (default: keep if >= min-tail-seconds)",
    )
    p.add_argument(
        "--min-tail-seconds",
        type=float,
        default=1.5,
        help="If not dropping short tails, keep final partial segment if at least this long",
    )
    p.add_argument("--limit-clips", type=int, default=0, help="Process at most N source clips")
    p.add_argument("--skip-existing", action="store_true", help="Skip writing segment WAV if destination exists")
    p.add_argument("--dry-run", action="store_true", help="Print plan only; do not write segments")
    p.add_argument(
        "--progress-every",
        type=int,
        default=200,
        help="Print progress every N source clips (default: 200)",
    )
    p.add_argument(
        "--partition-by",
        default="utc_day",
        choices=["utc_day", "none"],
        help="Partition output folders by segment start UTC day",
    )
    p.add_argument("--write-csv", action="store_true", help="Also write CSV manifest (default: parquet only)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    in_root = Path(args.local_root)
    out_root = Path(args.out_dir)
    manifest_root = Path(args.manifest_out_dir) if str(args.manifest_out_dir).strip() else out_root
    if not in_root.exists():
        raise SystemExit(f"--local-root not found: {in_root}")
    if args.segment_seconds <= 0 or args.stride_seconds <= 0:
        raise SystemExit("--segment-seconds and --stride-seconds must be > 0")

    source_paths = sorted(in_root.rglob("*.wav"))
    if args.limit_clips:
        source_paths = source_paths[: int(args.limit_clips)]
    if not source_paths:
        raise SystemExit("No WAV files found.")

    print(
        "[start] audio_segment_local "
        f"clips={len(source_paths)} site={str(args.site).strip().lower()} "
        f"segment_seconds={float(args.segment_seconds)} stride_seconds={float(args.stride_seconds)} "
        f"skip_existing={bool(args.skip_existing)} dry_run={bool(args.dry_run)} "
        f"out_dir={out_root} manifest_out_dir={manifest_root}",
        flush=True,
    )

    rows: List[Dict[str, Any]] = []
    clips_seen = clips_skipped = segments_written = segments_skipped = segments_write_failed = 0
    for src in source_paths:
        clips_seen += 1
        end_ts = parse_end_ts_from_name(src.name)
        if end_ts is None:
            clips_skipped += 1
            print(f"[skip] unparsed filename timestamp: {src.name}")
            continue
        try:
            y, sr, subtype = read_wav_with_meta(src)
        except Exception as e:
            clips_skipped += 1
            print(f"[skip] read failed {src}: {e}")
            continue
        if y.ndim == 1:
            n_channels = 1
        else:
            n_channels = int(y.shape[1])
        duration_s = float(y.shape[0]) / float(sr)
        clip_start_ts = end_ts - pd.to_timedelta(duration_s, unit="s")
        segs = segment_plan(
            n_samples=int(y.shape[0]),
            sample_rate=int(sr),
            segment_seconds=float(args.segment_seconds),
            stride_seconds=float(args.stride_seconds),
            drop_short_tail=bool(args.drop_short_tail),
            min_tail_seconds=float(args.min_tail_seconds),
        )
        if not segs:
            clips_skipped += 1
            print(f"[skip] no segments planned for {src.name} duration={duration_s:.3f}s")
            continue

        for seg_idx, (i0, i1) in enumerate(segs):
            seg_y = y[i0:i1]
            seg_duration = float(i1 - i0) / float(sr)
            seg_start_ts = clip_start_ts + pd.to_timedelta(float(i0) / float(sr), unit="s")
            seg_end_ts = clip_start_ts + pd.to_timedelta(float(i1) / float(sr), unit="s")
            out_rel = build_segment_relpath(
                site=str(args.site).strip().lower(),
                seg_start_ts=seg_start_ts,
                seg_end_ts=seg_end_ts,
                partition_by=args.partition_by,
                seg_idx=seg_idx,
            )
            out_path = out_root / out_rel

            row = {
                "site": str(args.site).strip().lower(),
                "source_path": str(src),
                "source_name": src.name,
                "source_clip_end_ts_utc": end_ts.isoformat(),
                "source_clip_start_ts_utc": clip_start_ts.isoformat(),
                "source_clip_duration_sec": duration_s,
                "source_sample_rate": int(sr),
                "source_channels": int(n_channels),
                "source_subtype": subtype,
                "segment_index": int(seg_idx),
                "segment_start_ts_utc": seg_start_ts.isoformat(),
                "segment_end_ts_utc": seg_end_ts.isoformat(),
                "segment_duration_sec": seg_duration,
                "segment_sample_i0": int(i0),
                "segment_sample_i1": int(i1),
                "segment_n_samples": int(i1 - i0),
                "segment_path": str(out_path),
                "segment_relpath": str(out_rel),
            }
            rows.append(row)

            if args.dry_run:
                continue
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if args.skip_existing and out_path.exists():
                segments_skipped += 1
                continue
            try:
                write_wav(out_path, seg_y, int(sr), subtype=subtype)
                segments_written += 1
            except Exception as e:
                segments_write_failed += 1
                print(f"[skip] write failed {out_path}: {e}", flush=True)
                continue

        if int(args.progress_every) > 0 and (clips_seen % int(args.progress_every) == 0):
            print(
                f"[progress] clips_seen={clips_seen} clips_skipped={clips_skipped} "
                f"segments_rows={len(rows)} segments_written={segments_written} "
                f"segments_skipped={segments_skipped} segments_write_failed={segments_write_failed}",
                flush=True,
            )

    manifest_df = pd.DataFrame(rows)
    manifest_base = manifest_root / f"dataset=audio_segments" / f"site={str(args.site).strip().lower()}"
    manifest_base.mkdir(parents=True, exist_ok=True)
    manifest_parquet = manifest_base / "audio_segments.parquet"
    manifest_csv = manifest_base / "audio_segments.csv"
    manifest_meta = manifest_base / "audio_segments_metadata.json"
    manifest_df.to_parquet(manifest_parquet, engine="pyarrow", compression="snappy", index=False)
    if args.write_csv:
        manifest_df.to_csv(manifest_csv, index=False)
    meta = {
        "site": str(args.site).strip().lower(),
        "local_root": str(in_root),
        "out_dir": str(out_root),
        "manifest_out_dir": str(manifest_root),
        "segment_seconds": float(args.segment_seconds),
        "stride_seconds": float(args.stride_seconds),
        "drop_short_tail": bool(args.drop_short_tail),
        "min_tail_seconds": float(args.min_tail_seconds),
        "partition_by": args.partition_by,
        "dry_run": bool(args.dry_run),
        "skip_existing": bool(args.skip_existing),
        "n_source_clips_seen": int(clips_seen),
        "n_source_clips_skipped": int(clips_skipped),
        "n_segments_rows": int(len(manifest_df)),
        "n_segments_written": int(segments_written),
        "n_segments_skipped_existing": int(segments_skipped),
        "n_segments_write_failed": int(segments_write_failed),
        "write_csv": bool(args.write_csv),
    }
    manifest_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"[done] clips_seen={clips_seen} clips_skipped={clips_skipped} "
        f"segments_rows={len(manifest_df)} segments_written={segments_written} "
        f"segments_skipped={segments_skipped} segments_write_failed={segments_write_failed}",
        flush=True,
    )
    print(f"[OK] wrote {manifest_parquet} rows={len(manifest_df)}")
    if args.write_csv:
        print(f"[OK] wrote {manifest_csv}")
    print(f"[OK] wrote {manifest_meta}")


def parse_end_ts_from_name(name: str) -> Optional[pd.Timestamp]:
    m_iso = FILENAME_ISO_RE.search(name)
    if m_iso:
        return parse_hyphenated_iso_label(m_iso.group("iso"))
    m_epoch = FILENAME_EPOCH_RE.search(name)
    if m_epoch:
        try:
            return pd.to_datetime(float(m_epoch.group(1)), unit="s", utc=True)
        except Exception:
            return None
    return None


def parse_hyphenated_iso_label(label: str) -> Optional[pd.Timestamp]:
    try:
        # Supports legacy local filenames like:
        # 2025-07-02T04-16-14.249304+00-00
        # 2025-07-02T04-16-14.249304Z
        date_part, time_part = label.split("T", 1)
        hh, mm, rest = time_part.split("-", 2)
        normalized = f"{date_part}T{hh}:{mm}:{rest}"
        if re.search(r"[+-]\d{2}-\d{2}$", normalized):
            normalized = normalized[:-6] + normalized[-6:-3] + ":" + normalized[-2:]
        return pd.to_datetime(normalized, utc=True)
    except Exception:
        return None


def read_wav_with_meta(path: Path) -> Tuple[np.ndarray, int, str]:
    if sf is not None:
        info = sf.info(str(path))
        y, sr = sf.read(str(path), dtype="float32", always_2d=False)
        return np.asarray(y, dtype="float32"), int(sr), str(getattr(info, "subtype", "") or "")

    if wavfile is None:
        raise RuntimeError("Need soundfile or scipy installed to read WAVs")
    sr, y = wavfile.read(str(path))
    subtype = str(np.asarray(y).dtype)
    y = np.asarray(y)
    if y.dtype.kind in ("i", "u"):
        y = int_to_float32(y)
    else:
        y = y.astype("float32", copy=False)
    return y, int(sr), subtype


def int_to_float32(x: np.ndarray) -> np.ndarray:
    info = np.iinfo(x.dtype)
    denom = float(max(abs(info.min), info.max))
    return (x.astype("float32") / denom).astype("float32", copy=False)


def segment_plan(
    *,
    n_samples: int,
    sample_rate: int,
    segment_seconds: float,
    stride_seconds: float,
    drop_short_tail: bool,
    min_tail_seconds: float,
) -> List[Tuple[int, int]]:
    seg_n = max(1, int(round(segment_seconds * sample_rate)))
    stride_n = max(1, int(round(stride_seconds * sample_rate)))
    if n_samples <= 0:
        return []
    out: List[Tuple[int, int]] = []
    i0 = 0
    while i0 < n_samples:
        i1 = i0 + seg_n
        if i1 <= n_samples:
            out.append((i0, i1))
            i0 += stride_n
            continue
        tail_n = n_samples - i0
        tail_s = float(tail_n) / float(sample_rate)
        if drop_short_tail:
            break
        if tail_s >= float(min_tail_seconds):
            out.append((i0, n_samples))
        break
    return out


def build_segment_relpath(
    *,
    site: str,
    seg_start_ts: pd.Timestamp,
    seg_end_ts: pd.Timestamp,
    partition_by: str,
    seg_idx: int,
) -> Path:
    start_label = safe_ts_label(seg_start_ts)
    end_label = safe_ts_label(seg_end_ts)
    fname = f"{site}_start={start_label}_end={end_label}_seg={seg_idx:02d}.wav"
    if partition_by == "utc_day":
        day = seg_start_ts.strftime("%Y-%m-%d")
        return Path(f"site={site}") / f"date={day}" / fname
    return Path(fname)


def safe_ts_label(ts: pd.Timestamp) -> str:
    s = ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return s.replace(":", "-")


def write_wav(path: Path, y: np.ndarray, sample_rate: int, *, subtype: str = "") -> None:
    if sf is not None:
        kwargs: Dict[str, Any] = {}
        if subtype and subtype.upper() in {"PCM_16", "PCM_24", "PCM_32", "FLOAT", "DOUBLE"}:
            kwargs["subtype"] = subtype
        sf.write(str(path), y, sample_rate, **kwargs)
        return
    if wavfile is None:
        raise RuntimeError("Need soundfile or scipy installed to write WAVs")
    # scipy wavfile.write supports float32 and int16, etc.
    wavfile.write(str(path), sample_rate, np.asarray(y))


if __name__ == "__main__":
    main()
