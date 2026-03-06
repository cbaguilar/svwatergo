from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ..train.audio_pretrained_embeddings import fit_audio_pretrained_embedding_experiment


def main() -> int:
    p = argparse.ArgumentParser(description="Run pretrained-audio embedding experiment (frozen head + partial fine-tune)")
    p.add_argument("--dataset", nargs="+", required=True, help="Labeled dataset parquet path(s)")
    p.add_argument("--split-manifest", default="", help="Optional split manifest parquet path")
    p.add_argument("--split-col", default="split")
    p.add_argument("--dataset-id-col", default="sample_id")
    p.add_argument("--split-id-col", default="sample_id")
    p.add_argument("--audio-path-col", default="segment_path")

    p.add_argument("--out-dir", required=True)
    p.add_argument("--backend", choices=["panns"], default="panns")
    p.add_argument("--task", choices=["binary", "multiclass"], default="multiclass")
    p.add_argument("--target-col", default="primary_class")
    p.add_argument("--positive-label", default="on")

    p.add_argument("--target-seconds", type=float, default=10.0)
    p.add_argument("--extract-batch-size", type=int, default=16)
    p.add_argument("--extract-num-workers", type=int, default=0)
    p.add_argument("--extract-log-every", type=int, default=0)
    p.add_argument("--random-state", type=int, default=42)

    p.add_argument("--frozen-hidden-sizes", default="256,128")
    p.add_argument("--frozen-max-iter", type=int, default=200)
    p.add_argument("--frozen-alpha", type=float, default=1e-4)

    p.add_argument("--run-partial-finetune", default="yes", choices=["yes", "no"])
    p.add_argument("--finetune-epochs", type=int, default=5)
    p.add_argument("--finetune-batch-size", type=int, default=8)
    p.add_argument("--finetune-num-workers", type=int, default=0)
    p.add_argument("--finetune-lr-head", type=float, default=1e-3)
    p.add_argument("--finetune-lr-backbone", type=float, default=1e-5)
    p.add_argument("--finetune-unfreeze-modules", type=int, default=1)
    p.add_argument("--finetune-amp", default="yes", choices=["yes", "no"])

    args = p.parse_args()

    dfs = [pd.read_parquet(pth) for pth in args.dataset]
    df = pd.concat(dfs, axis=0, ignore_index=True, sort=False)
    split_manifest_df = pd.read_parquet(args.split_manifest) if str(args.split_manifest).strip() else None

    res = fit_audio_pretrained_embedding_experiment(
        df,
        Path(args.out_dir),
        backend_name=str(args.backend),
        target_col=str(args.target_col),
        task=str(args.task),
        positive_label=str(args.positive_label),
        split_manifest_df=split_manifest_df,
        split_col=str(args.split_col),
        dataset_id_col=str(args.dataset_id_col),
        split_manifest_id_col=str(args.split_id_col),
        audio_path_col=str(args.audio_path_col),
        random_state=int(args.random_state),
        target_seconds=float(args.target_seconds),
        extract_batch_size=int(args.extract_batch_size),
        extract_num_workers=int(args.extract_num_workers),
        extract_log_every=int(args.extract_log_every),
        frozen_hidden_sizes=str(args.frozen_hidden_sizes),
        frozen_max_iter=int(args.frozen_max_iter),
        frozen_alpha=float(args.frozen_alpha),
        run_partial_finetune=(str(args.run_partial_finetune) == "yes"),
        finetune_epochs=int(args.finetune_epochs),
        finetune_batch_size=int(args.finetune_batch_size),
        finetune_num_workers=int(args.finetune_num_workers),
        finetune_lr_head=float(args.finetune_lr_head),
        finetune_lr_backbone=float(args.finetune_lr_backbone),
        finetune_unfreeze_modules=int(args.finetune_unfreeze_modules),
        finetune_amp=(str(args.finetune_amp) == "yes"),
    )

    print(f"Metrics       -> {res.metrics_path}")
    print(f"Frozen head   -> {res.frozen_head_path}")
    print(f"Finetuned head-> {res.finetuned_head_path if res.finetuned_head_path else 'skipped'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
