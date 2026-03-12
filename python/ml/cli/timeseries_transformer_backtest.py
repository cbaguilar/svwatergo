from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

from ..train.timeseries_transformer import (
    backtest_timeseries_transformer,
)
from ..utils.parquet_discovery import discover_date_partitioned_parquets


def _resolve_model_path(checkpoint_root: Path, horizon: str) -> Path:
    candidates = [
        checkpoint_root / f"horizon_{horizon}" / "timeseries_transformer.pt",
        checkpoint_root / horizon / "timeseries_transformer.pt",
        checkpoint_root / "timeseries_transformer.pt",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"No model checkpoint found for horizon={horizon} under {checkpoint_root}. "
        f"Tried: {', '.join(str(p) for p in candidates)}"
    )


def _downsample_idx(n: int, max_points: int) -> np.ndarray:
    if n <= max_points:
        return np.arange(n, dtype=np.int64)
    return np.linspace(0, n - 1, max_points, dtype=np.int64)


def _make_plot(
    pred_df: pd.DataFrame,
    feature_cols: List[str],
    *,
    out_png: Path,
    title: str,
    max_points: int,
    max_features: int,
) -> None:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as e:
        raise SystemExit("Missing matplotlib. Install: pip install matplotlib") from e

    chosen = feature_cols[: max(1, int(max_features))]
    idx = _downsample_idx(len(pred_df), max(1, int(max_points)))
    d = pred_df.iloc[idx].copy()

    t = pd.to_datetime(d["timestamp"], errors="coerce", utc=True)
    n = len(chosen)
    fig, axes = plt.subplots(n, 1, figsize=(15, 3.2 * n), sharex=True)
    if n == 1:
        axes = [axes]

    for ax, c in zip(axes, chosen):
        yt = pd.to_numeric(d[f"true_{c}"], errors="coerce")
        yp = pd.to_numeric(d[f"pred_{c}"], errors="coerce")
        ax.plot(t, yt, label=f"true:{c}", color="#1f77b4", linewidth=1.4)
        ax.plot(t, yp, label=f"pred:{c}", color="#ff7f0e", linewidth=1.2, alpha=0.9)
        ax.set_ylabel(c)
        ax.grid(alpha=0.25)
        ax.legend(loc="upper right", fontsize=8)

    axes[0].set_title(title)
    axes[-1].set_xlabel("timestamp")
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=140)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description="Run Transformer rolling backtest and render plot(s) per horizon")
    p.add_argument("--dataset", nargs="*", default=None, help="Input parquet path(s)")
    p.add_argument("--dataset-root", default="", help="Optional root with date partitions (date=YYYY-MM-DD)")
    p.add_argument("--dataset-filename", default="data.parquet", help="Filename inside each date partition")
    p.add_argument("--date-from", default="", help="Inclusive lower date bound for --dataset-root (YYYY-MM-DD)")
    p.add_argument("--date-to", default="", help="Inclusive upper date bound for --dataset-root (YYYY-MM-DD)")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--timestamp-col", required=True)
    p.add_argument("--group-col", default="")

    p.add_argument("--checkpoint-root", default="", help="Root containing horizon_* subdirs with timeseries_transformer.pt")
    p.add_argument("--model", default="", help="Single model checkpoint path (.pt). If set, runs one horizon only.")
    p.add_argument("--horizons", default="1m,1h,6h,24h", help="Comma-separated horizons")

    p.add_argument("--lookback", type=int, default=0, help="Override lookback (0 uses bundle config)")
    p.add_argument("--stride", type=int, default=1)
    p.add_argument("--max-gap-seconds", type=float, default=0.0)
    p.add_argument("--target-mode", default="", choices=["", "mean", "last"], help="Override target mode")

    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--dataloader-num-workers", type=int, default=0)
    p.add_argument("--device", default="auto")

    p.add_argument("--plot-features", default="", help="Comma-separated feature list for plot panels")
    p.add_argument("--plot-max-features", type=int, default=4)
    p.add_argument("--plot-max-points", type=int, default=5000)
    args = p.parse_args()

    if not str(args.model).strip() and not str(args.checkpoint_root).strip():
        raise SystemExit("Provide either --model or --checkpoint-root")
    if str(args.model).strip() and str(args.checkpoint_root).strip():
        raise SystemExit("Use either --model or --checkpoint-root, not both")

    dataset_paths = [str(p) for p in (args.dataset or []) if str(p).strip()]
    if str(args.dataset_root).strip():
        found = discover_date_partitioned_parquets(
            Path(args.dataset_root),
            filename=str(args.dataset_filename),
            date_from=str(args.date_from),
            date_to=str(args.date_to),
        )
        dataset_paths.extend(str(p) for p in found)
    if not dataset_paths:
        raise SystemExit("No datasets resolved. Provide --dataset and/or --dataset-root")

    seen = set()
    dataset_paths_unique = []
    for pth in dataset_paths:
        if pth not in seen:
            dataset_paths_unique.append(pth)
            seen.add(pth)

    print(f"Resolved {len(dataset_paths_unique)} parquet file(s)")
    dfs = [pd.read_parquet(pth) for pth in dataset_paths_unique]
    df = pd.concat(dfs, axis=0, ignore_index=True, sort=False)

    horizons = [h.strip() for h in str(args.horizons).split(",") if h.strip()]
    if str(args.model).strip():
        if len(horizons) != 1:
            raise SystemExit("When using --model, pass exactly one horizon in --horizons")

    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    for h in horizons:
        model_path = Path(args.model) if str(args.model).strip() else _resolve_model_path(Path(args.checkpoint_root), h)
        out_h = out_root / f"horizon_{h}"
        out_h.mkdir(parents=True, exist_ok=True)

        bt = backtest_timeseries_transformer(
            df,
            model_path,
            timestamp_col=str(args.timestamp_col),
            group_col=str(args.group_col),
            horizon=str(h),
            lookback=int(args.lookback),
            stride=int(args.stride),
            max_gap_seconds=float(args.max_gap_seconds),
            target_mode=str(args.target_mode),
            batch_size=int(args.batch_size),
            dataloader_num_workers=int(args.dataloader_num_workers),
            device=str(args.device),
        )

        pred_path = out_h / "backtest_predictions.parquet"
        metrics_path = out_h / "backtest_metrics.json"
        plot_path = out_h / "backtest_plot.png"
        bt.predictions.to_parquet(pred_path, index=False)

        metrics = dict(bt.metrics)
        metrics["model_path"] = str(model_path)

        metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

        plot_features = [c.strip() for c in str(args.plot_features).split(",") if c.strip()]
        if not plot_features:
            plot_features = list(bt.feature_cols[: max(1, int(args.plot_max_features))])

        _make_plot(
            bt.predictions,
            plot_features,
            out_png=plot_path,
            title=f"Transformer Backtest | horizon={h}",
            max_points=int(args.plot_max_points),
            max_features=int(args.plot_max_features),
        )

        print(f"[{h}] model   -> {model_path}")
        print(f"[{h}] pred    -> {pred_path}")
        print(f"[{h}] metrics -> {metrics_path}")
        print(f"[{h}] plot    -> {plot_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
