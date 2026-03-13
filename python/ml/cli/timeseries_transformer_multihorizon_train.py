from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ..train.timeseries_transformer import fit_timeseries_transformer_multihorizon
from ..utils.parquet_discovery import discover_date_partitioned_parquets


def main() -> int:
    p = argparse.ArgumentParser(description="Train multi-horizon Transformer for parquet time-series forecasting")
    p.add_argument("--dataset", nargs="*", default=None, help="Input parquet path(s)")
    p.add_argument("--dataset-root", default="", help="Optional root with date partitions (date=YYYY-MM-DD)")
    p.add_argument("--dataset-filename", default="data.parquet", help="Filename inside each date partition")
    p.add_argument("--date-from", default="", help="Inclusive lower date bound for --dataset-root (YYYY-MM-DD)")
    p.add_argument("--date-to", default="", help="Inclusive upper date bound for --dataset-root (YYYY-MM-DD)")

    p.add_argument("--out-dir", required=True, help="Output directory")
    p.add_argument("--timestamp-col", required=True, help="Timestamp column")
    p.add_argument("--group-col", default="", help="Optional grouping column")
    p.add_argument("--feature-cols", default="", help="Optional comma-separated feature columns")
    p.add_argument("--exclude-cols", default="", help="Optional comma-separated columns to exclude after feature selection")
    p.add_argument("--reg-target-cols", default="", help="Optional comma-separated regression target columns")
    p.add_argument("--binary-target-cols", default="", help="Optional comma-separated binary target columns")
    p.add_argument("--state-target-col", default="", help="Optional state target column")
    p.add_argument("--feature-preset", default="auto", choices=["auto", "raw", "window"], help="Feature selection preset")
    p.add_argument("--site", default="", help="Required with --feature-preset raw/window")

    p.add_argument("--horizons", default="1m,1h,6h,24h", help="Comma-separated horizons")
    p.add_argument("--horizon-weights", default="", help="Comma-separated positive weights (same order as horizons)")
    p.add_argument("--lookback", type=int, default=256)
    p.add_argument("--stride", type=int, default=1)
    p.add_argument("--max-gap-seconds", type=float, default=0.0)
    p.add_argument("--target-mode", choices=["mean", "last"], default="last")

    p.add_argument("--train-frac", type=float, default=0.7)
    p.add_argument("--val-frac", type=float, default=0.15)
    p.add_argument("--random-state", type=int, default=42)

    p.add_argument("--epochs", type=int, default=10)
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--learning-rate", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--grad-clip", type=float, default=1.0)

    p.add_argument("--d-model", type=int, default=128)
    p.add_argument("--nhead", type=int, default=4)
    p.add_argument("--num-layers", type=int, default=2)
    p.add_argument("--ff-dim", type=int, default=256)
    p.add_argument("--dropout", type=float, default=0.1)

    p.add_argument("--dataloader-num-workers", type=int, default=8)
    p.add_argument("--device", default="auto", help="auto, cpu, or cuda")
    p.add_argument("--time-cyc-features", default="yes", choices=["yes", "no"], help="Add sin/cos hour-of-day and day-of-week features")
    p.add_argument("--resume-from", default="", help="Optional checkpoint path to resume from")
    p.add_argument("--save-every-epochs", type=int, default=1)
    p.add_argument("--keep-epoch-checkpoints", default="yes", choices=["yes", "no"])
    p.add_argument("--regression-task-weight", type=float, default=1.0)
    p.add_argument("--binary-task-weight", type=float, default=1.0)
    p.add_argument("--state-task-weight", type=float, default=1.0)

    args = p.parse_args()

    dataset_paths = [str(x) for x in (args.dataset or []) if str(x).strip()]
    if str(args.dataset_root).strip():
        found = discover_date_partitioned_parquets(
            Path(args.dataset_root),
            filename=str(args.dataset_filename),
            date_from=str(args.date_from),
            date_to=str(args.date_to),
        )
        dataset_paths.extend(str(pth) for pth in found)
    if not dataset_paths:
        raise SystemExit("No datasets resolved. Provide --dataset and/or --dataset-root")

    seen = set()
    unique_paths = []
    for pth in dataset_paths:
        if pth not in seen:
            unique_paths.append(pth)
            seen.add(pth)

    print(f"Resolved {len(unique_paths)} parquet file(s)")
    dfs = [pd.read_parquet(pth) for pth in unique_paths]
    df = pd.concat(dfs, axis=0, ignore_index=True, sort=False)

    feature_cols = [c.strip() for c in str(args.feature_cols).split(",") if c.strip()]
    exclude_cols = [c.strip() for c in str(args.exclude_cols).split(",") if c.strip()]
    reg_target_cols = [c.strip() for c in str(args.reg_target_cols).split(",") if c.strip()]
    binary_target_cols = [c.strip() for c in str(args.binary_target_cols).split(",") if c.strip()]
    horizons = [h.strip() for h in str(args.horizons).split(",") if h.strip()]
    horizon_weights = [float(x.strip()) for x in str(args.horizon_weights).split(",") if x.strip()]

    res = fit_timeseries_transformer_multihorizon(
        df,
        Path(args.out_dir),
        timestamp_col=str(args.timestamp_col),
        feature_cols=(feature_cols if feature_cols else None),
        exclude_cols=(exclude_cols if exclude_cols else None),
        reg_target_cols=(reg_target_cols if reg_target_cols else None),
        binary_target_cols=(binary_target_cols if binary_target_cols else None),
        state_target_col=str(args.state_target_col),
        feature_preset=str(args.feature_preset),
        site=str(args.site),
        group_col=str(args.group_col),
        horizons=horizons,
        horizon_weights=(horizon_weights if horizon_weights else None),
        lookback=int(args.lookback),
        stride=int(args.stride),
        max_gap_seconds=float(args.max_gap_seconds),
        target_mode=str(args.target_mode),
        train_frac=float(args.train_frac),
        val_frac=float(args.val_frac),
        random_state=int(args.random_state),
        batch_size=int(args.batch_size),
        epochs=int(args.epochs),
        learning_rate=float(args.learning_rate),
        weight_decay=float(args.weight_decay),
        d_model=int(args.d_model),
        nhead=int(args.nhead),
        num_layers=int(args.num_layers),
        ff_dim=int(args.ff_dim),
        dropout=float(args.dropout),
        grad_clip=float(args.grad_clip),
        dataloader_num_workers=int(args.dataloader_num_workers),
        device=str(args.device),
        time_cyc_features=(str(args.time_cyc_features) == "yes"),
        resume_from=(Path(args.resume_from) if str(args.resume_from).strip() else None),
        save_every_epochs=int(args.save_every_epochs),
        keep_epoch_checkpoints=(str(args.keep_epoch_checkpoints) == "yes"),
        regression_task_weight=float(args.regression_task_weight),
        binary_task_weight=float(args.binary_task_weight),
        state_task_weight=float(args.state_task_weight),
    )

    print(f"Model   -> {res.model_path}")
    print(f"Metrics -> {res.metrics_path}")
    print(f"Config  -> {res.config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
