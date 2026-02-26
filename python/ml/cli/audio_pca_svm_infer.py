from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..train.audio_pca_svm import predict_audio_pca_svm


def main() -> int:
    p = argparse.ArgumentParser(description="Run inference with a trained audio PCA+SVM bundle")
    p.add_argument("--model", required=True, help="audio_pca_svm_model.joblib")
    p.add_argument("--wav", default=None, help="Raw wav input (converted to mel using saved mel config)")
    p.add_argument("--webp", default=None, help="Rendered mel spectrogram image (.webp)")
    p.add_argument("--mel-npy", default=None, help="2D mel array saved as .npy")
    p.add_argument("--mel-npz", default=None, help="2D/3D mel array saved as .npz")
    p.add_argument("--mel-npz-key", default="mel")
    p.add_argument("--mel-npz-index", type=int, default=0)
    args = p.parse_args()

    out = predict_audio_pca_svm(
        Path(args.model),
        wav_path=Path(args.wav) if args.wav else None,
        webp_path=Path(args.webp) if args.webp else None,
        mel_npy_path=Path(args.mel_npy) if args.mel_npy else None,
        mel_npz_path=Path(args.mel_npz) if args.mel_npz else None,
        mel_npz_key=str(args.mel_npz_key),
        mel_npz_index=int(args.mel_npz_index),
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
