from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
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


@dataclass(frozen=True)
class MelSegmentsConfig:
    segments_root: Path
    segments_manifest: str
    out_dir: Path
    site: str = "bluerock"
    limit_segments: int = 0
    skip_existing_shards: bool = False
    sample_rate: int = 16000
    mono: bool = True
    target_seconds: float = 4.0
    pad_short: bool = True
    truncate_long: bool = True
    dtype: str = "float32"
    decoder: str = "soundfile"
    n_fft: int = 1024
    win_length: int = 1024
    hop_length: int = 256
    n_mels: int = 64
    fmin: float = 20.0
    fmax: float = 8000.0
    power: float = 2.0
    log_eps: float = 1e-10
    to_db: bool = False
    shard_size: int = 1024
    partition_by: str = "utc_day"


def build_arg_parser() -> argparse.ArgumentParser:
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
    p.add_argument(
        "--decoder",
        default="soundfile",
        choices=["soundfile", "ffmpeg"],
        help="Audio decoder (ffmpeg recommended for webm/opus)",
    )

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
    return p


def config_from_args(args: argparse.Namespace) -> MelSegmentsConfig:
    return MelSegmentsConfig(
        segments_root=Path(args.segments_root),
        segments_manifest=str(args.segments_manifest or ""),
        out_dir=Path(args.out_dir),
        site=str(args.site).strip().lower(),
        limit_segments=int(args.limit_segments or 0),
        skip_existing_shards=bool(args.skip_existing_shards),
        sample_rate=int(args.sample_rate),
        mono=bool(args.mono),
        target_seconds=float(args.target_seconds),
        pad_short=bool(args.pad_short),
        truncate_long=bool(args.truncate_long),
        dtype=str(args.dtype),
        decoder=str(args.decoder),
        n_fft=int(args.n_fft),
        win_length=int(args.win_length),
        hop_length=int(args.hop_length),
        n_mels=int(args.n_mels),
        fmin=float(args.fmin),
        fmax=float(args.fmax),
        power=float(args.power),
        log_eps=float(args.log_eps),
        to_db=bool(args.to_db),
        shard_size=int(args.shard_size),
        partition_by=str(args.partition_by),
    )


def generate_mel_segments(cfg: MelSegmentsConfig) -> Path:
    seg_root = cfg.segments_root
    out_root = cfg.out_dir
    if not seg_root.exists():
        raise SystemExit(f"--segments-root not found: {seg_root}")
    if cfg.fmax > (cfg.sample_rate / 2.0):
        raise SystemExit("--fmax must be <= sample_rate/2")

    segments_df = load_segments_df(seg_root, cfg.segments_manifest)
    if cfg.limit_segments:
        segments_df = segments_df.iloc[: int(cfg.limit_segments)].copy()
    if segments_df.empty:
        raise SystemExit("No segment WAVs found to process.")

    target_n = int(round(float(cfg.target_seconds) * int(cfg.sample_rate)))
    mel_filter = make_mel_filterbank(
        sr=int(cfg.sample_rate),
        n_fft=int(cfg.n_fft),
        n_mels=int(cfg.n_mels),
        fmin=float(cfg.fmin),
        fmax=float(cfg.fmax),
    )

    site = str(cfg.site).strip().lower()
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
            y, sr, subtype = read_wav_with_meta(seg_path, decoder=cfg.decoder, sample_rate=int(cfg.sample_rate), mono=bool(cfg.mono))
            y = ensure_mono(y) if cfg.mono else np.asarray(y, dtype="float32")
            y_res = resample_if_needed(y, int(sr), int(cfg.sample_rate))
            y_fix, fix_meta = fix_length(
                y_res,
                target_n=target_n,
                pad_short=bool(cfg.pad_short),
                truncate_long=bool(cfg.truncate_long),
            )
            if y_fix is None:
                total_skipped += 1
                continue
            mel = waveform_to_logmel(
                y_fix,
                sr=int(cfg.sample_rate),
                n_fft=int(cfg.n_fft),
                win_length=int(cfg.win_length),
                hop_length=int(cfg.hop_length),
                mel_filter=mel_filter,
                power=float(cfg.power),
                log_eps=float(cfg.log_eps),
                to_db=bool(cfg.to_db),
            )
            mel = mel.astype(cfg.dtype, copy=False)
        except Exception as e:
            total_failed += 1
            print(f"[skip] mel generation failed for {seg_path.name}: {e}", flush=True)
            continue

        part_key = partition_key_for_segment(seg, partition_by=cfg.partition_by)
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
            "audio_output_sample_rate": int(cfg.sample_rate),
            "audio_channels_after_mono": 1 if cfg.mono else int(1 if y_res.ndim == 1 else y_res.shape[1]),
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

        if len(buf) >= int(cfg.shard_size):
            write_shard_and_rows(
                shard_path=shard_path,
                items=buf,
                rows_out=rows,
                skip_existing=bool(cfg.skip_existing_shards),
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
            skip_existing=bool(cfg.skip_existing_shards),
        )

    manifest_df = pd.DataFrame(rows)
    manifest_parquet = out_base / "audio_mel_segments.parquet"
    manifest_csv = out_base / "audio_mel_segments.csv"
    manifest_meta = out_base / "audio_mel_segments_metadata.json"
    manifest_df.to_parquet(manifest_parquet, index=False)
    manifest_df.to_csv(manifest_csv, index=False)

    meta = {
        "segments_root": str(seg_root),
        "segments_manifest": str(cfg.segments_manifest),
        "out_dir": str(out_root),
        "site": site,
        "limit_segments": int(cfg.limit_segments),
        "skip_existing_shards": bool(cfg.skip_existing_shards),
        "sample_rate": int(cfg.sample_rate),
        "mono": bool(cfg.mono),
        "target_seconds": float(cfg.target_seconds),
        "pad_short": bool(cfg.pad_short),
        "truncate_long": bool(cfg.truncate_long),
        "dtype": str(cfg.dtype),
        "decoder": str(cfg.decoder),
        "n_fft": int(cfg.n_fft),
        "win_length": int(cfg.win_length),
        "hop_length": int(cfg.hop_length),
        "n_mels": int(cfg.n_mels),
        "fmin": float(cfg.fmin),
        "fmax": float(cfg.fmax),
        "power": float(cfg.power),
        "log_eps": float(cfg.log_eps),
        "to_db": bool(cfg.to_db),
        "shard_size": int(cfg.shard_size),
        "partition_by": str(cfg.partition_by),
        "rows": int(len(manifest_df)),
    }
    manifest_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"[OK] mel manifest rows={len(manifest_df)} -> {manifest_parquet}", flush=True)
    return manifest_parquet


# === Helpers (extracted) ===

def load_segments_df(segments_root: Path, manifest_path: str) -> pd.DataFrame:
    if manifest_path:
        mpath = Path(manifest_path)
        if mpath.exists():
            return pd.read_parquet(mpath)

    wavs = sorted(segments_root.rglob("*.wav"))
    rows = []
    for w in wavs:
        rel = str(w.relative_to(segments_root))
        start_ts = end_ts = None
        m = SEGMENT_TS_RE.search(w.name)
        if m:
            start_ts = m.group("start")
            end_ts = m.group("end")
        rows.append(
            {
                "segment_path": str(w),
                "segment_relpath": rel,
                "segment_start_ts_utc": start_ts,
                "segment_end_ts_utc": end_ts,
                "segment_duration_sec": None,
                "source_path": None,
                "source_name": None,
                "source_clip_start_ts_utc": None,
                "source_clip_end_ts_utc": None,
                "segment_index": None,
            }
        )
    return pd.DataFrame(rows)


def iter_segments(df: pd.DataFrame) -> Iterable[Dict[str, Any]]:
    for _, row in df.iterrows():
        yield row.to_dict()


def read_wav_with_meta(
    path: Path,
    *,
    decoder: str,
    sample_rate: int,
    mono: bool,
) -> Tuple[np.ndarray, int, str]:
    if decoder == "ffmpeg":
        from ..storage.audio import read_audio_path_ffmpeg

        data, sr, subtype = read_audio_path_ffmpeg(path, sample_rate=sample_rate, mono=mono)
        return np.asarray(data, dtype="float32"), int(sr), str(subtype)
    if sf is not None:
        data, sr = sf.read(path, always_2d=False)
        subtype = sf.info(path).subtype
        return np.asarray(data, dtype="float32"), int(sr), str(subtype)
    if wavfile is None:
        raise RuntimeError("No audio reader available (soundfile or scipy)")
    sr, data = wavfile.read(path)
    return np.asarray(data, dtype="float32"), int(sr), "wavfile"


def ensure_mono(y: np.ndarray) -> np.ndarray:
    y = np.asarray(y)
    if y.ndim == 1:
        return y.astype("float32", copy=False)
    return y.mean(axis=1).astype("float32", copy=False)


def resample_if_needed(y: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return y
    n = int(round(len(y) * (sr_out / sr_in)))
    return signal.resample(y, n).astype("float32", copy=False)


def fix_length(
    y: np.ndarray,
    *,
    target_n: int,
    pad_short: bool,
    truncate_long: bool,
) -> Tuple[Optional[np.ndarray], Dict[str, bool]]:
    y = np.asarray(y, dtype="float32")
    padded = truncated = False
    if y.shape[0] < target_n:
        if not pad_short:
            return None, {"padded": False, "truncated": False}
        pad_n = target_n - y.shape[0]
        y = np.pad(y, (0, pad_n), mode="constant")
        padded = True
    if y.shape[0] > target_n:
        if not truncate_long:
            return None, {"padded": padded, "truncated": False}
        y = y[:target_n]
        truncated = True
    return y, {"padded": padded, "truncated": truncated}


def hz_to_mel(f_hz: np.ndarray) -> np.ndarray:
    return 2595.0 * np.log10(1.0 + (f_hz / 700.0))


def mel_to_hz(mel: np.ndarray) -> np.ndarray:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def make_mel_filterbank(*, sr: int, n_fft: int, n_mels: int, fmin: float, fmax: float) -> np.ndarray:
    mel_edges = np.linspace(hz_to_mel(np.array([fmin]))[0], hz_to_mel(np.array([fmax]))[0], n_mels + 2)
    hz_edges = mel_to_hz(mel_edges)
    n_freqs = int(n_fft // 2 + 1)
    fb = np.zeros((n_mels, n_freqs), dtype="float32")
    for m in range(1, n_mels + 1):
        f_left, f_center, f_right = hz_edges[m - 1], hz_edges[m], hz_edges[m + 1]
        left_bin = int(math.floor((n_fft + 1) * f_left / sr))
        center_bin = int(math.floor((n_fft + 1) * f_center / sr))
        right_bin = int(math.floor((n_fft + 1) * f_right / sr))
        for k in range(left_bin, center_bin):
            if 0 <= k < n_freqs:
                fb[m - 1, k] = (k - left_bin) / max(center_bin - left_bin, 1e-12)
        for k in range(center_bin, right_bin):
            if 0 <= k < n_freqs:
                fb[m - 1, k] = (right_bin - k) / max(right_bin - center_bin, 1e-12)
    enorm = 2.0 / np.maximum(hz_edges[2 : n_mels + 2] - hz_edges[:n_mels], 1e-12)
    fb *= enorm[:, np.newaxis]
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
    if y.ndim != 1:
        y = y.reshape(-1)
    freqs, times, spec = signal.spectrogram(
        y,
        fs=sr,
        nperseg=win_length,
        noverlap=win_length - hop_length,
        nfft=n_fft,
        scaling="spectrum",
        mode="magnitude",
    )
    if power != 1.0:
        spec = spec ** power
    mel = np.matmul(mel_filter, spec)
    mel = np.maximum(mel, float(log_eps))
    if to_db:
        mel = (10.0 * np.log10(mel)).astype("float32")
    else:
        mel = np.log10(mel).astype("float32")
    return mel


def partition_key_for_segment(seg: Dict[str, Any], *, partition_by: str) -> str:
    if partition_by == "none":
        return "all"
    ts = seg.get("segment_start_ts_utc") or ""
    if isinstance(ts, str) and ts:
        return ts.split("T", 1)[0]
    return "unknown"


def build_shard_relpath(*, site: str, partition_key: str, shard_idx: int) -> Path:
    if partition_key == "all":
        return Path(f"mel_shard_{shard_idx:05d}.npz")
    return Path(f"date={partition_key}") / f"mel_shard_{shard_idx:05d}.npz"


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
        print(f"[skip] shard exists: {shard_path} segments={len(items)}", flush=True)
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


def safe_int(val: Any, *, default: int) -> int:
    try:
        return int(val)
    except Exception:
        return default
