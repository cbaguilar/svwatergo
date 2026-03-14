from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from ..train.audio_pca_svm import fit_audio_pca_svm


def main() -> int:
    p = argparse.ArgumentParser(description="Train PCA+SVM on labeled audio mel dataset")
    p.add_argument("--dataset", nargs="+", required=True, help="Labeled dataset parquet path(s)")
    p.add_argument("--split-manifest", default="", help="Optional split manifest parquet (uses fixed splits instead of random split)")
    p.add_argument("--split-col", default="split", help="Split column name (default: split)")
    p.add_argument("--split-stratify-col", default="", help="Optional dataset column to stratify random split assignment")
    p.add_argument("--dataset-id-col", default="sample_id", help="ID column in --dataset used to join split manifest")
    p.add_argument("--split-id-col", default="sample_id", help="ID column in --split-manifest used to join dataset")
    p.add_argument("--drop-state-unknown-train", default="yes", choices=["yes", "no"])
    p.add_argument("--state-unknown-col", default="state_unknown")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--target-col", default="ropumprun_label", help="Target column (default ropumprun_label)")
    p.add_argument("--task", choices=["binary", "multiclass"], default="binary")
    p.add_argument("--positive-label", default="on", help="Binary positive class when target is string labels")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--sample", choices=["head", "random"], default="random")
    p.add_argument("--n-components", type=int, default=8)
    p.add_argument("--test-size", type=float, default=0.2)
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--svm-kernel", default="rbf", choices=["linear", "rbf", "poly", "sigmoid"])
    p.add_argument("--svm-c", type=float, default=1.0)
    p.add_argument("--svm-gamma", default="scale")
    p.add_argument("--svm-class-weight", choices=["balanced"], default=None, help="Optional class weighting for SVM")
    p.add_argument("--oversample-class-col", default="primary_class", help="Class column used to pick rows for train-only oversampling")
    p.add_argument(
        "--oversample-classes",
        default="",
        help="Comma-separated class labels to oversample in training set (e.g. not_producing|delivering,producing|delivering)",
    )
    p.add_argument("--oversample-multiplier", type=int, default=1, help="Integer multiplier for selected oversampled classes (1 disables)")
    p.add_argument("--no-standardize", action="store_true")

    # Persisted mel settings used for wav inference; defaults match current mel generator.
    p.add_argument("--sample-rate", type=int, default=16000)
    p.add_argument("--mono", action="store_true", default=True)
    p.add_argument("--target-seconds", type=float, default=4.0)
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
    }

    res = fit_audio_pca_svm(
        df,
        Path(args.out_dir),
        target_col=str(args.target_col),
        task=str(args.task),
        positive_label=str(args.positive_label),
        limit=int(args.limit),
        sample_mode=str(args.sample),
        n_components=int(args.n_components),
        standardize=not bool(args.no_standardize),
        test_size=float(args.test_size),
        random_state=int(args.random_state),
        svm_kernel=str(args.svm_kernel),
        svm_c=float(args.svm_c),
        svm_gamma=str(args.svm_gamma),
        svm_class_weight=str(args.svm_class_weight) if args.svm_class_weight else None,
        mel_config=mel_config,
        split_manifest_df=split_manifest_df,
        split_col=str(args.split_col),
        dataset_id_col=str(args.dataset_id_col),
        split_manifest_id_col=str(args.split_id_col),
        drop_state_unknown_train=(str(args.drop_state_unknown_train) == "yes"),
        state_unknown_col=str(args.state_unknown_col),
        split_stratify_col=str(args.split_stratify_col),
        oversample_class_col=str(args.oversample_class_col),
        oversample_classes=(
            [c.strip() for c in str(args.oversample_classes).split(",") if c.strip()]
            if str(args.oversample_classes).strip()
            else None
        ),
        oversample_multiplier=int(args.oversample_multiplier),
    )
    print(f"Model      -> {res.model_path}")
    print(f"Metrics    -> {res.metrics_path}")
    print(f"Projection -> {res.projection_path}")
    print(f"Mel config -> {json.dumps(mel_config, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
