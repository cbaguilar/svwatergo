from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from ..train.audio_tiny_cnn import fit_audio_tiny_cnn


def main() -> int:
    p = argparse.ArgumentParser(description="Train tiny CNN on labeled audio mel dataset")
    p.add_argument("--dataset", nargs="+", required=True, help="Labeled dataset parquet path(s)")
    p.add_argument("--split-manifest", default="", help="Optional split manifest parquet (uses fixed splits instead of random split)")
    p.add_argument("--split-col", default="split", help="Split column name (default: split)")
    p.add_argument("--dataset-id-col", default="sample_id", help="ID column in --dataset used to join split manifest")
    p.add_argument("--split-id-col", default="sample_id", help="ID column in --split-manifest used to join dataset")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--target-col", default="ropumprun_label", help="Target column for binary/multiclass tasks")
    p.add_argument(
        "--target-cols",
        default="",
        help="Comma-separated target columns for multilabel task (default: overlap_s_producing,overlap_s_delivering)",
    )
    p.add_argument("--task", choices=["binary", "multiclass", "multilabel"], default="binary")
    p.add_argument("--model-arch", choices=["tiny_cnn", "resnet_small"], default="tiny_cnn")
    p.add_argument("--positive-threshold", type=float, default=0.0, help="Positive threshold for numeric multilabel targets")
    p.add_argument("--positive-label", default="on", help="Binary positive class when target is string labels")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--sample", choices=["head", "random"], default="random")
    p.add_argument("--test-size", type=float, default=0.2)
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--epochs", type=int, default=12)
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--learning-rate", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--class-weight", choices=["balanced"], default=None, help="Optional class weighting for CNN loss")

    # Persisted mel settings used for wav inference.
    p.add_argument("--sample-rate", type=int, default=16000)
    p.add_argument("--mono", action="store_true", default=True)
    p.add_argument("--target-seconds", type=float, default=10.0)
    p.add_argument("--n-fft", type=int, default=1024)
    p.add_argument("--win-length", type=int, default=1024)
    p.add_argument("--hop-length", type=int, default=256)
    p.add_argument("--n-mels", type=int, default=64)
    p.add_argument("--fmin", type=float, default=20.0)
    p.add_argument("--fmax", type=float, default=8000.0)
    p.add_argument("--power", type=float, default=2.0)
    p.add_argument("--log-eps", type=float, default=1e-10)
    p.add_argument("--to-db", action="store_true")
    p.add_argument(
        "--mel-normalization",
        default="legacy",
        choices=["legacy", "none", "log_db", "log10", "log1p_zscore", "log10_median_sub"],
    )
    p.add_argument("--cmvn", action="store_true", help="Apply per-clip per-frequency CMVN before training/inference")
    args = p.parse_args()

    dfs = [pd.read_parquet(pth) for pth in args.dataset]
    df = pd.concat(dfs, axis=0, ignore_index=True, sort=False)
    split_manifest_df = pd.read_parquet(args.split_manifest) if str(args.split_manifest).strip() else None

    mel_config = {
        "sample_rate": int(args.sample_rate),
        "mono": bool(args.mono),
        "target_seconds": float(args.target_seconds),
        "n_fft": int(args.n_fft),
        "win_length": int(args.win_length),
        "hop_length": int(args.hop_length),
        "n_mels": int(args.n_mels),
        "fmin": float(args.fmin),
        "fmax": float(args.fmax),
        "power": float(args.power),
        "log_eps": float(args.log_eps),
        "to_db": bool(args.to_db),
        "mel_normalization": str(args.mel_normalization),
        "cmvn": bool(args.cmvn),
    }

    res = fit_audio_tiny_cnn(
        df,
        Path(args.out_dir),
        target_col=str(args.target_col),
        task=str(args.task),
        target_cols=(
            [c.strip() for c in str(args.target_cols).split(",") if c.strip()]
            if str(args.target_cols).strip()
            else None
        ),
        positive_threshold=float(args.positive_threshold),
        positive_label=str(args.positive_label),
        limit=int(args.limit),
        sample_mode=str(args.sample),
        test_size=float(args.test_size),
        random_state=int(args.random_state),
        epochs=int(args.epochs),
        batch_size=int(args.batch_size),
        learning_rate=float(args.learning_rate),
        weight_decay=float(args.weight_decay),
        class_weight=str(args.class_weight) if args.class_weight else None,
        mel_config=mel_config,
        split_manifest_df=split_manifest_df,
        split_col=str(args.split_col),
        dataset_id_col=str(args.dataset_id_col),
        split_manifest_id_col=str(args.split_id_col),
        model_arch=str(args.model_arch),
    )
    print(f"Model      -> {res.model_path}")
    print(f"Metrics    -> {res.metrics_path}")
    print(f"Projection -> {res.projection_path}")
    print(f"Mel config -> {json.dumps(mel_config, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
