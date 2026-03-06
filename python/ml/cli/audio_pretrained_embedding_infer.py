from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np


def _load_waveform(path: Path, *, sample_rate: int, target_seconds: float) -> np.ndarray:
    from ..storage.audio import read_audio_path_ffmpeg

    y, sr, _ = read_audio_path_ffmpeg(path, sample_rate=int(sample_rate), mono=True)
    y = np.asarray(y, dtype=np.float32).reshape(-1)
    n_target = int(round(float(target_seconds) * int(sr)))
    if n_target > 0:
        if len(y) < n_target:
            out = np.zeros((n_target,), dtype=np.float32)
            out[: len(y)] = y
            y = out
        elif len(y) > n_target:
            y = y[:n_target]
    return y.astype(np.float32, copy=False)


def main() -> int:
    p = argparse.ArgumentParser(description="Infer with frozen pretrained-embedding head")
    p.add_argument("--model", required=True, help="Path to frozen_mlp_head.joblib")
    p.add_argument("--audio", required=True, help="Audio path (wav/webm/etc supported via ffmpeg)")
    p.add_argument("--target-seconds", type=float, default=0.0, help="Override target seconds; default from model")
    p.add_argument("--device", default="cuda", choices=["cuda", "cpu"], help="PANN embedding device")
    args = p.parse_args()

    try:
        import joblib  # type: ignore
    except Exception as e:
        raise SystemExit("Missing joblib. Install: pip install joblib") from e

    try:
        from panns_inference import AudioTagging  # type: ignore
    except Exception as e:
        raise SystemExit("Missing panns_inference. Install: pip install panns-inference") from e

    bundle: Dict[str, Any] = joblib.load(str(Path(args.model)))
    scaler = bundle.get("scaler", None)
    clf = bundle.get("classifier", None)
    if scaler is None or clf is None:
        raise SystemExit("Invalid frozen head bundle: missing scaler/classifier")

    backend = str(bundle.get("backend", "")).strip().lower()
    if backend != "panns":
        raise SystemExit(f"Unsupported backend in bundle: {backend!r}")

    model_sr = int(bundle.get("sample_rate", 32000))
    model_target_seconds = float(bundle.get("target_seconds", 10.0))
    target_seconds = float(args.target_seconds) if float(args.target_seconds) > 0 else model_target_seconds

    y = _load_waveform(Path(args.audio), sample_rate=model_sr, target_seconds=target_seconds)

    tagger = AudioTagging(checkpoint_path=None, device=str(args.device))
    _clipwise, embedding = tagger.inference(np.expand_dims(y, axis=0))
    emb = np.asarray(embedding, dtype=np.float32)
    if emb.ndim > 2:
        emb = emb.reshape(emb.shape[0], -1)

    x = scaler.transform(emb)
    pred_idx = int(clf.predict(x)[0])

    y_meta = bundle.get("y_meta", {}) or {}
    classes: List[str] = [str(c) for c in (y_meta.get("classes") or [])]

    if hasattr(clf, "predict_proba"):
        probs = np.asarray(clf.predict_proba(x)[0], dtype=np.float64)
    else:
        probs = np.zeros((int(max(pred_idx + 1, len(classes), 1)),), dtype=np.float64)
        probs[pred_idx] = 1.0

    if not classes:
        classes = [str(i) for i in range(int(len(probs)))]

    probs_named = {classes[i] if i < len(classes) else str(i): float(probs[i]) for i in range(len(probs))}
    pred_label = classes[pred_idx] if pred_idx < len(classes) else str(pred_idx)

    out = {
        "model": str(Path(args.model)),
        "audio": str(Path(args.audio)),
        "backend": backend,
        "task": bundle.get("task", "unknown"),
        "target_col": bundle.get("target_col", "unknown"),
        "sample_rate": int(model_sr),
        "target_seconds": float(target_seconds),
        "prediction_index": int(pred_idx),
        "prediction_label": str(pred_label),
        "probabilities": probs_named,
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
