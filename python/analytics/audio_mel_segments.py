#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import signal

try:
    import soundfile as sf  # type: ignore
except Exception:
    sf = None

try:
    from scipy.io import wavfile  # type: ignore
except Exception:
    wavfile = None


SEGMENT_TS_RE = re.compile(
    r"start=(?P<start>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(?:\.\d+)?Z)_end=(?P<end>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(?:\.\d+)?Z)",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Batch-generate log-mel spectrogram shards from segmented WAVs."
    )
    p.add_argument("--segments-root", required=True, help="Root containing segmented WAVs (from audio_segment_local.py)")
    p.add_argument("--segments-manifest", default="", help="Optional audio_segments.parquet path (faster/more metadata)")
    p.add_argument("--out-dir", required=True, help="Output root for mel shards + manifest")
    p.add_argument("--site", default="bluerock", help="Site label (used in output metadata)")
    p.add_argument("--limit-segments", type=int, default=0, help="Process at most N segments")
    p.add_argument("--skip-existing-shards", action="store_true", help="Skip shards that already exist (manifest is still rewritten)")

    p.add_argument("--sample-rate", type=int, default=16000, help="Target sample rate (Hz)")
    p.add_argument("--mono", action="store_true", default=True, help="Convert multi-channel audio to mono (default true)")
    p.add_argument("--target-seconds", type=float, default=4.0, help="Pad/truncate waveform length to this duration before mel")
    p.add_argument("--pad-short", action="store_true", default=True, help="Pad segments shorter than target-seconds")
    p.add_argument("--truncate-long", action="store_true", default=True, help="Truncate segments longer than target-seconds")
    p.add_argument("--dtype", default="float32", choices=["float32", "float16"], help="Stored mel dtype inside shards")

    p.add_argument("--n-fft", type=int, default=1024)
    p.add_argument("--win-length", type=int, default=1024)
    p.add_argument("--hop-length", type=int, default=256)
    p.add_argument("--n-mels", type=int, default=64)
    p.add_argument("--fmin", type=float, default=20.0)
    p.add_argument("--fmax", type=float, default=8000.0)
    p.add_argument("--power", type=float, default=2.0, help="Magnitude exponent before mel projection (e.g. 2 for power)")
    p.add_argument("--log-eps", type=float, default=1e-10, help="Epsilon before log10")
    p.add_argument("--to-db", action="store_true", help="Store mel in dB scale (10*log10)")

    p.add_argument("--shard-size", type=int, default=1024, help="Segments per .npz shard")
    p.add_argument(
        "--partition-by",
        default="utc_day",
        choices=["utc_day", "none"],
        help="Partition output by segment_start UTC day",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    seg_root = Path(args.segments_root)
    out_root = Path(args.out_dir)
    if not seg_root.exists():
        raise SystemExit(f"--segments-root not found: {seg_root}")
    if args.fmax > (args.sample_rate / 2.0):
        raise SystemExit("--fmax must be <= sample_rate/2")

    segments_df = load_segments_df(seg_root, args.segments_manifest)
    if args.limit_segments:
        segments_df = segments_df.iloc[: int(args.limit_segments)].copy()
    if segments_df.empty:
        raise SystemExit("No segment WAVs found to process.")

    target_n = int(round(float(args.target_seconds) * int(args.sample_rate)))
    mel_filter = make_mel_filterbank(
        sr=int(args.sample_rate),
        n_fft=int(args.n_fft),
        n_mels=int(args.n_mels),
        fmin=float(args.fmin),
        fmax=float(args.fmax),
    )

    site = str(args.site).strip().lower()
    out_base = out_root / "dataset=audio_mel_segments" / f"site={site}"
    out_base.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    shard_buffers: Dict[str, List[Tuple[Dict[str, Any], np.ndarray]]] = {}
    shard_counters: Dict[str, int] = {}
    total_done = total_skipped = total_failed = 0

    for i, seg in enumerate(iter_segments(segments_df), start=1):
        seg_path = Path(seg["segment_path"])
        if not seg_path.exists():
            total_failed += 1
            print(f"[skip] missing segment file: {seg_path}", flush=True)
            continue
        try:
            y, sr, subtype = read_wav_with_meta(seg_path)
            y = ensure_mono(y) if args.mono else np.asarray(y, dtype="float32")
            y_res = resample_if_needed(y, int(sr), int(args.sample_rate))
            y_fix, fix_meta = fix_length(
                y_res,
                target_n=target_n,
                pad_short=bool(args.pad_short),
                truncate_long=bool(args.truncate_long),
            )
            if y_fix is None:
                total_skipped += 1
                continue
            mel = waveform_to_logmel(
                y_fix,
                sr=int(args.sample_rate),
                n_fft=int(args.n_fft),
                win_length=int(args.win_length),
                hop_length=int(args.hop_length),
                mel_filter=mel_filter,
                power=float(args.power),
                log_eps=float(args.log_eps),
                to_db=bool(args.to_db),
            )
            mel = mel.astype(args.dtype, copy=False)
        except Exception as e:
            total_failed += 1
            print(f"[skip] mel generation failed for {seg_path.name}: {e}", flush=True)
            continue

        part_key = partition_key_for_segment(seg, partition_by=args.partition_by)
        shard_idx = shard_counters.get(part_key, 0)
        shard_rel = build_shard_relpath(site=site, partition_key=part_key, shard_idx=shard_idx)
        shard_path = out_base / shard_rel
        buf = shard_buffers.setdefault(part_key, [])

        row = {
            "site": site,
            "segment_path": str(seg_path),
            "segment_relpath": seg.get("segment_relpath", ""),
            "segment_start_ts_utc": seg.get("segment_start_ts_utc"),
            "segment_end_ts_utc": seg.get("segment_end_ts_utc"),
            "segment_duration_sec": float(seg.get("segment_duration_sec") or 0.0),
            "source_path": seg.get("source_path", ""),
            "source_name": seg.get("source_name", ""),
            "source_clip_start_ts_utc": seg.get("source_clip_start_ts_utc"),
            "source_clip_end_ts_utc": seg.get("source_clip_end_ts_utc"),
            "segment_index": safe_int(seg.get("segment_index"), default=-1),
            "audio_input_sample_rate": int(sr),
            "audio_output_sample_rate": int(args.sample_rate),
            "audio_channels_after_mono": 1 if args.mono else int(1 if y_res.ndim == 1 else y_res.shape[1]),
            "audio_subtype": subtype,
            "wave_n_samples_original": int(np.asarray(y if np.asarray(y).ndim == 1 else y).shape[0]),
            "wave_n_samples_resampled": int(np.asarray(y_res).shape[0]),
            "wave_n_samples_final": int(np.asarray(y_fix).shape[0]),
            "segment_was_padded": bool(fix_meta["padded"]),
            "segment_was_truncated": bool(fix_meta["truncated"]),
            "mel_n_mels": int(mel.shape[0]),
            "mel_n_frames": int(mel.shape[1]),
            "mel_dtype": str(mel.dtype),
            "mel_shard_relpath": str(shard_rel),
            "mel_shard_path": str(shard_path),
        }
        buf.append((row, mel))
        total_done += 1

        if len(buf) >= int(args.shard_size):
            write_shard_and_rows(
                shard_path=shard_path,
                items=buf,
                rows_out=rows,
                skip_existing=bool(args.skip_existing_shards),
            )
            shard_buffers[part_key] = []
            shard_counters[part_key] = shard_idx + 1

        if i % 500 == 0:
            print(
                f"[progress] seen={i} ok={total_done} skipped={total_skipped} failed={total_failed} "
                f"rows={len(rows)} pending_buffers={sum(len(v) for v in shard_buffers.values())}",
                flush=True,
            )

    for part_key, buf in list(shard_buffers.items()):
        if not buf:
            continue
        shard_idx = shard_counters.get(part_key, 0)
        shard_rel = build_shard_relpath(site=site, partition_key=part_key, shard_idx=shard_idx)
        shard_path = out_base / shard_rel
        write_shard_and_rows(
            shard_path=shard_path,
            items=buf,
            rows_out=rows,
            skip_existing=bool(args.skip_existing_shards),
        )
        shard_buffers[part_key] = []
        shard_counters[part_key] = shard_idx + 1

    manifest_df = pd.DataFrame(rows)
    manifest_parquet = out_base / "audio_mel_segments.parquet"
    manifest_csv = out_base / "audio_mel_segments.csv"
    manifest_meta = out_base / "audio_mel_segments_metadata.json"
    if not manifest_df.empty:
        manifest_df.to_parquet(manifest_parquet, engine="pyarrow", compression="snappy", index=False)
        manifest_df.to_csv(manifest_csv, index=False)
    else:
        pd.DataFrame([]).to_parquet(manifest_parquet, engine="pyarrow", compression="snappy", index=False)
        pd.DataFrame([]).to_csv(manifest_csv, index=False)

    meta = {
        "site": site,
        "segments_root": str(seg_root),
        "segments_manifest": str(args.segments_manifest or ""),
        "out_dir": str(out_root),
        "n_segments_input": int(len(segments_df)),
        "n_segments_ok": int(total_done),
        "n_segments_failed": int(total_failed),
        "n_segments_skipped": int(total_skipped),
        "n_manifest_rows": int(len(manifest_df)),
        "partition_by": args.partition_by,
        "sample_rate": int(args.sample_rate),
        "mono": bool(args.mono),
        "target_seconds": float(args.target_seconds),
        "pad_short": bool(args.pad_short),
        "truncate_long": bool(args.truncate_long),
        "n_fft": int(args.n_fft),
        "win_length": int(args.win_length),
        "hop_length": int(args.hop_length),
        "n_mels": int(args.n_mels),
        "fmin": float(args.fmin),
        "fmax": float(args.fmax),
        "power": float(args.power),
        "log_eps": float(args.log_eps),
        "to_db": bool(args.to_db),
        "dtype": str(args.dtype),
        "shard_size": int(args.shard_size),
    }
    manifest_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[OK] mel manifest rows={len(manifest_df)} -> {manifest_parquet}", flush=True)
    print(f"[OK] metadata -> {manifest_meta}", flush=True)


def load_segments_df(segments_root: Path, manifest_path: str) -> pd.DataFrame:
    if manifest_path:
        p = Path(manifest_path)
        if not p.exists():
            raise SystemExit(f"--segments-manifest not found: {p}")
        df = pd.read_parquet(p)
        if "segment_path" not in df.columns:
            raise SystemExit("segments manifest missing segment_path column")
        return df

    rows: List[Dict[str, Any]] = []
    for p in sorted(segments_root.rglob("*.wav")):
        start_ts, end_ts = parse_segment_ts_from_name(p.name)
        rows.append(
            {
                "segment_path": str(p),
                "segment_relpath": str(p.relative_to(segments_root)),
                "segment_start_ts_utc": start_ts.isoformat() if start_ts is not None else None,
                "segment_end_ts_utc": end_ts.isoformat() if end_ts is not None else None,
                "segment_duration_sec": ((end_ts - start_ts).total_seconds() if (start_ts is not None and end_ts is not None) else None),
            }
        )
    return pd.DataFrame(rows)


def iter_segments(df: pd.DataFrame) -> Iterable[Dict[str, Any]]:
    for row in df.to_dict(orient="records"):
        yield row


def parse_segment_ts_from_name(name: str) -> Tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    m = SEGMENT_TS_RE.search(name)
    if not m:
        return None, None
    try:
        start = pd.to_datetime(m.group("start").replace("T", "T").replace("-", ":", 2), utc=True)
    except Exception:
        start = None
    try:
        end = pd.to_datetime(m.group("end").replace("T", "T").replace("-", ":", 2), utc=True)
    except Exception:
        end = None
    # Above replacement is wrong for dates if applied globally; parse via helper below if either failed.
    if start is None or end is None:
        return parse_safe_ts_label(m.group("start")), parse_safe_ts_label(m.group("end"))
    return start, end


def parse_safe_ts_label(label: str) -> Optional[pd.Timestamp]:
    try:
        # Label format from audio_segment_local.safe_ts_label: YYYY-MM-DDTHH-MM-SS.ffffffZ
        date_part, time_part = label.split("T", 1)
        hh, mm, rest = time_part.split("-", 2)
        ss_and_tz = rest
        normalized = f"{date_part}T{hh}:{mm}:{ss_and_tz}"
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


def ensure_mono(y: np.ndarray) -> np.ndarray:
    a = np.asarray(y, dtype="float32")
    if a.ndim == 1:
        return a
    return a.mean(axis=1, dtype="float32")


def resample_if_needed(y: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return np.asarray(y, dtype="float32")
    n_out = max(1, int(round(float(len(y)) * float(sr_out) / float(sr_in))))
    yr = signal.resample(y, n_out)
    return np.asarray(yr, dtype="float32")


def fix_length(
    y: np.ndarray,
    *,
    target_n: int,
    pad_short: bool,
    truncate_long: bool,
) -> Tuple[Optional[np.ndarray], Dict[str, bool]]:
    a = np.asarray(y, dtype="float32")
    n = int(a.shape[0])
    meta = {"padded": False, "truncated": False}
    if n == target_n:
        return a, meta
    if n < target_n:
        if not pad_short:
            return None, meta
        out = np.zeros((target_n,), dtype="float32")
        out[:n] = a
        meta["padded"] = True
        return out, meta
    if not truncate_long:
        return None, meta
    meta["truncated"] = True
    return a[:target_n], meta


def hz_to_mel(f_hz: np.ndarray) -> np.ndarray:
    return 2595.0 * np.log10(1.0 + (f_hz / 700.0))


def mel_to_hz(mel: np.ndarray) -> np.ndarray:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def make_mel_filterbank(*, sr: int, n_fft: int, n_mels: int, fmin: float, fmax: float) -> np.ndarray:
    n_freqs = (n_fft // 2) + 1
    fmax = min(fmax, sr / 2.0)
    mel_edges = np.linspace(hz_to_mel(np.array([fmin]))[0], hz_to_mel(np.array([fmax]))[0], n_mels + 2)
    hz_edges = mel_to_hz(mel_edges)
    bins = np.floor((n_fft + 1) * hz_edges / sr).astype(int)
    bins = np.clip(bins, 0, n_freqs - 1)
    fb = np.zeros((n_mels, n_freqs), dtype="float32")
    for m in range(1, n_mels + 1):
        left = bins[m - 1]
        center = bins[m]
        right = bins[m + 1]
        if center <= left:
            center = min(left + 1, n_freqs - 1)
        if right <= center:
            right = min(center + 1, n_freqs)
        for k in range(left, center):
            fb[m - 1, k] = (k - left) / float(max(center - left, 1))
        for k in range(center, right):
            fb[m - 1, k] = (right - k) / float(max(right - center, 1))
    # Slaney-style area normalization improves comparability.
    enorm = 2.0 / np.maximum(hz_edges[2 : n_mels + 2] - hz_edges[:n_mels], 1e-12)
    fb *= enorm[:, np.newaxis].astype("float32")
    return fb


def waveform_to_logmel(
    y: np.ndarray,
    *,
    sr: int,
    n_fft: int,
    win_length: int,
    hop_length: int,
    mel_filter: np.ndarray,
    power: float,
    log_eps: float,
    to_db: bool,
) -> np.ndarray:
    _, _, zxx = signal.stft(
        y,
        fs=sr,
        window="hann",
        nperseg=win_length,
        noverlap=win_length - hop_length,
        nfft=n_fft,
        boundary=None,
        padded=False,
    )
    mag = np.abs(zxx).astype("float32")
    spec = mag ** power if power != 1.0 else mag
    mel = np.matmul(mel_filter, spec)
    mel = np.maximum(mel, float(log_eps))
    if to_db:
        mel = (10.0 * np.log10(mel)).astype("float32")
    else:
        mel = np.log10(mel).astype("float32")
    return mel


def partition_key_for_segment(seg: Dict[str, Any], *, partition_by: str) -> str:
    if partition_by == "none":
        return ""
    ts = seg.get("segment_start_ts_utc")
    if isinstance(ts, str) and ts:
        try:
            return str(pd.to_datetime(ts, utc=True).strftime("%Y-%m-%d"))
        except Exception:
            pass
    return "unknown-date"


def build_shard_relpath(*, site: str, partition_key: str, shard_idx: int) -> Path:
    fname = f"mel_shard_{shard_idx:05d}.npz"
    if partition_key:
        return Path(f"date={partition_key}") / fname
    return Path(fname)


def write_shard_and_rows(
    *,
    shard_path: Path,
    items: List[Tuple[Dict[str, Any], np.ndarray]],
    rows_out: List[Dict[str, Any]],
    skip_existing: bool,
) -> None:
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    if skip_existing and shard_path.exists():
        for local_idx, (row, mel) in enumerate(items):
            row["mel_shard_local_index"] = int(local_idx)
            row["mel_saved"] = False
            row["mel_skipped_existing_shard"] = True
            row["mel_shape"] = f"{mel.shape[0]}x{mel.shape[1]}"
            rows_out.append(row)
        print(f"[skip] shard exists: {shard_path}", flush=True)
        return

    mels = np.stack([mel for _, mel in items], axis=0)
    np.savez_compressed(shard_path, mel=mels)
    for local_idx, (row, mel) in enumerate(items):
        row["mel_shard_local_index"] = int(local_idx)
        row["mel_saved"] = True
        row["mel_skipped_existing_shard"] = False
        row["mel_shape"] = f"{mel.shape[0]}x{mel.shape[1]}"
        rows_out.append(row)
    print(f"[write] {shard_path} segments={len(items)} shape={mels.shape}", flush=True)


def safe_int(v: Any, *, default: int) -> int:
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return default
        return int(v)
    except Exception:
        return default


if __name__ == "__main__":
    main()
