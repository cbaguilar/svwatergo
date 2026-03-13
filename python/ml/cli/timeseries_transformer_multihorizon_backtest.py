from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

from ..train.timeseries_transformer import backtest_timeseries_transformer_multihorizon
from ..utils.parquet_discovery import discover_date_partitioned_parquets


def _select_focus_features(feature_cols: List[str], max_features: int) -> List[str]:
    want = max(1, int(max_features))
    preferred = [
        c for c in feature_cols
        if any(tok in str(c).lower() for tok in ("flow", "pressure", "tanklevel", "tankdepth"))
    ]
    ordered = preferred + [c for c in feature_cols if c not in preferred]
    out: List[str] = []
    for c in ordered:
        if c not in out:
            out.append(c)
        if len(out) >= want:
            break
    return out


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
    p = argparse.ArgumentParser(description="Backtest multi-horizon Transformer and write per-horizon plots")
    p.add_argument("--model", required=True, help="Path to timeseries_transformer_multihorizon.pt")
    p.add_argument("--dataset", nargs="*", default=None, help="Input parquet path(s)")
    p.add_argument("--dataset-root", default="", help="Optional root with date partitions (date=YYYY-MM-DD)")
    p.add_argument("--dataset-filename", default="data.parquet", help="Filename inside each date partition")
    p.add_argument("--date-from", default="", help="Inclusive lower date bound for --dataset-root (YYYY-MM-DD)")
    p.add_argument("--date-to", default="", help="Inclusive upper date bound for --dataset-root (YYYY-MM-DD)")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--timestamp-col", required=True)
    p.add_argument("--group-col", default="")
    p.add_argument("--horizons", default="", help="Optional comma-separated subset of horizons")
    p.add_argument("--lookback", type=int, default=0)
    p.add_argument("--stride", type=int, default=1)
    p.add_argument("--max-gap-seconds", type=float, default=0.0)
    p.add_argument("--target-mode", default="", choices=["", "mean", "last"])
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--dataloader-num-workers", type=int, default=0)
    p.add_argument("--device", default="auto")
    p.add_argument("--plot-features", default="", help="Comma-separated feature list for plot panels")
    p.add_argument("--plot-max-features", type=int, default=4)
    p.add_argument("--plot-max-points", type=int, default=5000)
    args = p.parse_args()

    dataset_paths = [str(pth) for pth in (args.dataset or []) if str(pth).strip()]
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
    print("[backtest-cli] reading parquet files", flush=True)
    dfs = [pd.read_parquet(pth) for pth in unique_paths]
    df = pd.concat(dfs, axis=0, ignore_index=True, sort=False)
    print(f"[backtest-cli] concatenated rows={len(df)}", flush=True)

    hz_subset = [h.strip() for h in str(args.horizons).split(",") if h.strip()]
    print("[backtest-cli] running model backtest", flush=True)
    bt = backtest_timeseries_transformer_multihorizon(
        df,
        Path(args.model),
        timestamp_col=str(args.timestamp_col),
        group_col=str(args.group_col),
        horizons=(hz_subset if hz_subset else None),
        lookback=int(args.lookback),
        stride=int(args.stride),
        max_gap_seconds=float(args.max_gap_seconds),
        target_mode=str(args.target_mode),
        batch_size=int(args.batch_size),
        dataloader_num_workers=int(args.dataloader_num_workers),
        device=str(args.device),
    )

    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    metrics_path = out_root / "timeseries_transformer_multihorizon_backtest_metrics.json"
    metrics_payload = dict(bt.metrics)
    metrics_payload["model_path"] = str(Path(args.model))

    plot_features = [c.strip() for c in str(args.plot_features).split(",") if c.strip()]
    if not plot_features:
        plot_features = _select_focus_features(bt.feature_cols, int(args.plot_max_features))
    metrics_payload["focus_plot_features"] = list(plot_features)
    metrics_path.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")
    print(f"[backtest-cli] metrics -> {metrics_path}", flush=True)

    for hz, pred_df in bt.predictions_by_horizon.items():
        out_h = out_root / f"horizon_{hz}"
        out_h.mkdir(parents=True, exist_ok=True)
        pred_path = out_h / "backtest_predictions.parquet"
        plot_path = out_h / "backtest_plot.png"
        print(f"[backtest-cli] writing horizon={hz} predictions", flush=True)
        pred_df.to_parquet(pred_path, index=False)
        print(f"[backtest-cli] rendering horizon={hz} plot", flush=True)
        _make_plot(
            pred_df,
            plot_features,
            out_png=plot_path,
            title=f"Multi-Horizon Transformer Backtest | horizon={hz}",
            max_points=int(args.plot_max_points),
            max_features=int(args.plot_max_features),
        )
        print(f"[{hz}] pred -> {pred_path}")
        print(f"[{hz}] plot -> {plot_path}")
        print(f"[{hz}] focus -> {','.join(plot_features)}")

    print(f"Metrics -> {metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
