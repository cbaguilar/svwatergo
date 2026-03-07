from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ..train.audio_pretrained_embedding_multitask import fit_audio_pretrained_embedding_multitask


def main() -> int:
    p = argparse.ArgumentParser(
        description="Train on frozen PANN embeddings: multiclass, multilabel, or PLC-PCA encoder mode"
    )
    p.add_argument("--dataset", nargs="+", required=True, help="Labeled dataset parquet path(s)")
    p.add_argument("--split-manifest", default="", help="Optional split manifest parquet path")
    p.add_argument("--split-col", default="split")
    p.add_argument("--dataset-id-col", default="sample_id")
    p.add_argument("--split-id-col", default="sample_id")
    p.add_argument("--audio-path-col", default="segment_path")
    p.add_argument("--source-filter-col", default="audio_source")
    p.add_argument("--source-filter-values", default="", help="Optional comma-separated source values to keep")

    p.add_argument("--out-dir", required=True)
    p.add_argument("--task-mode", default="multiclass", choices=["multiclass", "multilabel", "plc_pca_encoder"])
    p.add_argument("--target-col", default="primary_class")
    p.add_argument("--target-cols", default="ropumprun_duty,deliveryrun_duty")
    p.add_argument("--positive-threshold", type=float, default=0.5)
    p.add_argument("--positive-label", default="on")

    p.add_argument("--target-seconds", type=float, default=10.0)
    p.add_argument("--extract-batch-size", type=int, default=16)
    p.add_argument("--extract-num-workers", type=int, default=0)
    p.add_argument("--extract-log-every", type=int, default=0)
    p.add_argument("--random-state", type=int, default=42)

    p.add_argument("--encoder-hidden", default="512,256")
    p.add_argument("--encoder-dropout", type=float, default=0.2)
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--learning-rate", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--eval-every", type=int, default=5)
    p.add_argument("--main-task-weight", type=float, default=1.0)
    p.add_argument("--best-model-metric", default="auto", choices=["auto", "main_task_metric", "plc_pca_r2"])
    p.add_argument("--best-model-split", default="val", choices=["val", "test"])

    p.add_argument("--aux-plc-pca", default="yes", choices=["yes", "no"])
    p.add_argument("--aux-plc-feature-cols", default="")
    p.add_argument("--aux-plc-include-duty-cols", default="no", choices=["yes", "no"])
    p.add_argument("--aux-plc-components", type=int, default=8)
    p.add_argument("--aux-plc-variance-ratio", type=float, default=0.0)
    p.add_argument("--aux-plc-weight", type=float, default=0.3)

    p.add_argument("--pann-pca-components", type=int, default=8)
    p.add_argument("--pann-pca-variance-ratio", type=float, default=0.0)
    p.add_argument("--pann-pca-weight", type=float, default=1.0)

    args = p.parse_args()

    dfs = [pd.read_parquet(pth) for pth in args.dataset]
    df = pd.concat(dfs, axis=0, ignore_index=True, sort=False)
    split_manifest_df = pd.read_parquet(args.split_manifest) if str(args.split_manifest).strip() else None

    res = fit_audio_pretrained_embedding_multitask(
        df,
        Path(args.out_dir),
        task_mode=str(args.task_mode),
        target_col=str(args.target_col),
        target_cols=[c.strip() for c in str(args.target_cols).split(",") if c.strip()],
        positive_threshold=float(args.positive_threshold),
        positive_label=str(args.positive_label),
        split_manifest_df=split_manifest_df,
        split_col=str(args.split_col),
        dataset_id_col=str(args.dataset_id_col),
        split_manifest_id_col=str(args.split_id_col),
        audio_path_col=str(args.audio_path_col),
        source_filter_col=str(args.source_filter_col),
        source_filter_values=[c.strip() for c in str(args.source_filter_values).split(",") if c.strip()],
        random_state=int(args.random_state),
        target_seconds=float(args.target_seconds),
        extract_batch_size=int(args.extract_batch_size),
        extract_num_workers=int(args.extract_num_workers),
        extract_log_every=int(args.extract_log_every),
        encoder_hidden=str(args.encoder_hidden),
        encoder_dropout=float(args.encoder_dropout),
        epochs=int(args.epochs),
        batch_size=int(args.batch_size),
        learning_rate=float(args.learning_rate),
        weight_decay=float(args.weight_decay),
        eval_every=int(args.eval_every),
        main_task_weight=float(args.main_task_weight),
        best_model_metric=str(args.best_model_metric),
        best_model_split=str(args.best_model_split),
        aux_plc_pca=(str(args.aux_plc_pca) == "yes"),
        aux_plc_feature_cols=(
            [c.strip() for c in str(args.aux_plc_feature_cols).split(",") if c.strip()]
            if str(args.aux_plc_feature_cols).strip()
            else None
        ),
        aux_plc_include_duty_cols=(str(args.aux_plc_include_duty_cols) == "yes"),
        aux_plc_components=int(args.aux_plc_components),
        aux_plc_variance_ratio=float(args.aux_plc_variance_ratio),
        aux_plc_weight=float(args.aux_plc_weight),
        pann_pca_components=int(args.pann_pca_components),
        pann_pca_variance_ratio=float(args.pann_pca_variance_ratio),
        pann_pca_weight=float(args.pann_pca_weight),
    )

    print(f"Model   -> {res.model_path}")
    print(f"Metrics -> {res.metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
