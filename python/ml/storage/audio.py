from __future__ import annotations

import io
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
