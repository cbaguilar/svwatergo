from __future__ import annotations

import io
import subprocess
from pathlib import Path
from typing import Tuple

import numpy as np

try:
    import soundfile as sf  # type: ignore
except Exception:
    sf = None

from .s3 import read_bytes_uri


def read_audio_uri(uri: str) -> Tuple[np.ndarray, int, str]:
    data = read_bytes_uri(uri)
    if sf is None:
        raise RuntimeError("soundfile not available")
    with io.BytesIO(data) as bio:
        y, sr = sf.read(bio, always_2d=False)
        subtype = sf.info(bio).subtype
    return np.asarray(y, dtype="float32"), int(sr), str(subtype)


def read_audio_path(path: Path) -> Tuple[np.ndarray, int, str]:
    if sf is None:
        raise RuntimeError("soundfile not available")
    y, sr = sf.read(path, always_2d=False)
    subtype = sf.info(path).subtype
    return np.asarray(y, dtype="float32"), int(sr), str(subtype)


def read_audio_path_ffmpeg(path: Path, *, sample_rate: int, mono: bool = True) -> Tuple[np.ndarray, int, str]:
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-f",
        "f32le",
        "-ar",
        str(int(sample_rate)),
        "-ac",
        "1" if mono else "2",
        "pipe:1",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, check=False)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install ffmpeg to decode webm.")
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {res.stderr.decode('utf-8', errors='ignore')}")
    y = np.frombuffer(res.stdout, dtype=np.float32)
    return y, int(sample_rate), "ffmpeg"
