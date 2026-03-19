from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

_PYTHON_ROOT = Path(__file__).resolve().parents[2]
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from units import label_with_unit
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
        ax.set_ylabel(label_with_unit(c))
        ax.grid(alpha=0.25)
        ax.legend(loc="upper right", fontsize=8)

    axes[0].set_title(title)
    axes[-1].set_xlabel("timestamp")
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=140)
    plt.close(fig)


def _safe_plot_features(pred_df: pd.DataFrame, feature_cols: List[str], max_features: int) -> List[str]:
    chosen: List[str] = []
    for c in feature_cols:
        if f"true_{c}" in pred_df.columns and f"pred_{c}" in pred_df.columns:
            chosen.append(c)
        if len(chosen) >= max(1, int(max_features)):
            break
    if not chosen:
        raise SystemExit("No requested plot features are present in backtest predictions")
    return chosen


def _make_embedding_pca_plot(
    emb_df: pd.DataFrame,
    *,
    out_png: Path,
    out_parquet: Path,
    max_points: int,
) -> Dict[str, float]:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as e:
        raise SystemExit("Missing matplotlib. Install: pip install matplotlib") from e

    emb_cols = [c for c in emb_df.columns if str(c).startswith("embedding_")]
    if len(emb_cols) < 3:
        raise SystemExit("Need at least 3 embedding dimensions for PCA plot")
    x = emb_df[emb_cols].to_numpy(dtype=np.float32)
    x = x - x.mean(axis=0, keepdims=True)
    u, s, _ = np.linalg.svd(x, full_matrices=False)
    pcs = (u[:, :3] * s[:3]).astype(np.float32)
    var = (s ** 2) / max(1.0, float(np.sum(s ** 2)))
    out = emb_df[[c for c in emb_df.columns if not str(c).startswith("embedding_")]].copy()
    out["pc1"] = pcs[:, 0]
    out["pc2"] = pcs[:, 1]
    out["pc3"] = pcs[:, 2]
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_parquet, index=False)

    idx = _downsample_idx(len(out), max(1, int(max_points)))
    d = out.iloc[idx].copy()
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")
    t_num = np.arange(len(d), dtype=np.float32)
    sc = ax.scatter(d["pc1"], d["pc2"], d["pc3"], c=t_num, cmap="viridis", s=8, alpha=0.8)
    ax.set_xlabel(f"PC1 ({var[0] * 100.0:.1f}%)")
    ax.set_ylabel(f"PC2 ({var[1] * 100.0:.1f}%)")
    ax.set_zlabel(f"PC3 ({var[2] * 100.0:.1f}%)")
    ax.set_title("Lookback Embedding PCA")
    fig.colorbar(sc, ax=ax, shrink=0.7, pad=0.1, label="sample order")
    fig.tight_layout()
    fig.savefig(out_png, dpi=140)
    plt.close(fig)
    return {
        "pc1_explained_variance_ratio": float(var[0]),
        "pc2_explained_variance_ratio": float(var[1]),
        "pc3_explained_variance_ratio": float(var[2]),
    }


def _select_embedding_color_features(emb_df: pd.DataFrame, max_features: int) -> List[str]:
    cols = [str(c) for c in emb_df.columns if not str(c).startswith("embedding_")]
    preferred = [
        c for c in cols
        if (
            c == "state"
            or "flow" in c.lower()
            or "pressure" in c.lower()
            or c.lower().endswith("run")
            or c.lower().endswith("auto")
            or "pump" in c.lower()
        )
    ]
    ordered = preferred + [c for c in cols if c not in preferred]
    out: List[str] = []
    for c in ordered:
        if c in {"sample_end_index", "timestamp", "horizon"}:
            continue
        if c not in out:
            out.append(c)
        if len(out) >= max(1, int(max_features)):
            break
    return out


def _make_embedding_pca_color_plot(
    pca_df: pd.DataFrame,
    *,
    color_col: str,
    out_png: Path,
    max_points: int,
) -> None:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as e:
        raise SystemExit("Missing matplotlib. Install: pip install matplotlib") from e

    if color_col not in pca_df.columns:
        raise SystemExit(f"Embedding PCA color column missing: {color_col}")
    idx = _downsample_idx(len(pca_df), max(1, int(max_points)))
    d = pca_df.iloc[idx].copy()
    c_raw = pd.to_numeric(d[color_col], errors="coerce")
    valid = c_raw.notna().to_numpy()
    if not np.any(valid):
        raise SystemExit(f"No valid numeric values available for embedding PCA color column: {color_col}")

    x = d.loc[valid, "pc1"].to_numpy(dtype=np.float32)
    y = d.loc[valid, "pc2"].to_numpy(dtype=np.float32)
    z = d.loc[valid, "pc3"].to_numpy(dtype=np.float32)
    c = c_raw.loc[valid].to_numpy(dtype=np.float32)

    is_discrete = False
    uniq = np.unique(c)
    if len(uniq) <= 12 and np.all(np.isclose(uniq, np.round(uniq))):
        is_discrete = True

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")
    if is_discrete:
        cmap = plt.get_cmap("tab10", max(2, len(uniq)))
        sc = ax.scatter(x, y, z, c=c, cmap=cmap, s=8, alpha=0.85)
        cbar = fig.colorbar(sc, ax=ax, shrink=0.7, pad=0.1)
        cbar.set_label(label_with_unit(color_col))
    else:
        sc = ax.scatter(x, y, z, c=c, cmap="viridis", s=8, alpha=0.85)
        cbar = fig.colorbar(sc, ax=ax, shrink=0.7, pad=0.1)
        cbar.set_label(label_with_unit(color_col))
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.set_zlabel("PC3")
    ax.set_title(f"Lookback Embedding PCA | color={label_with_unit(color_col)}")
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
    p.add_argument("--embedding-pca-plot", default="yes", choices=["yes", "no"])
    p.add_argument("--embedding-pca-color-features", default="", help="Comma-separated columns to color embedding PCA by")
    p.add_argument("--embedding-pca-max-color-features", type=int, default=24)
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

    if str(args.embedding_pca_plot) == "yes" and bt.embeddings is not None and len(bt.embeddings) > 0:
        emb_plot = out_root / "embedding_pca_3d.png"
        emb_parquet = out_root / "embedding_pca_3d.parquet"
        print("[backtest-cli] rendering embedding PCA plot", flush=True)
        metrics_payload["embedding_pca"] = _make_embedding_pca_plot(
            bt.embeddings,
            out_png=emb_plot,
            out_parquet=emb_parquet,
            max_points=int(args.plot_max_points),
        )
        metrics_payload["embedding_pca"]["plot_path"] = str(emb_plot)
        metrics_payload["embedding_pca"]["parquet_path"] = str(emb_parquet)
        emb_pca_df = pd.read_parquet(emb_parquet)
        color_features = [c.strip() for c in str(args.embedding_pca_color_features).split(",") if c.strip()]
        if not color_features:
            color_features = _select_embedding_color_features(
                emb_pca_df,
                int(args.embedding_pca_max_color_features),
            )
        color_features = [c for c in color_features if c in emb_pca_df.columns]
        metrics_payload["embedding_pca"]["color_features"] = list(color_features)
        color_dir = out_root / "embedding_pca_colored"
        color_dir.mkdir(parents=True, exist_ok=True)
        for c in color_features:
            print(f"[backtest-cli] rendering embedding PCA color={c}", flush=True)
            _make_embedding_pca_color_plot(
                emb_pca_df,
                color_col=c,
                out_png=color_dir / f"embedding_pca_3d_color_{c}.png",
                max_points=int(args.plot_max_points),
            )
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
        hz_plot_features = _safe_plot_features(
            pred_df,
            plot_features,
            int(args.plot_max_features),
        )
        _make_plot(
            pred_df,
            hz_plot_features,
            out_png=plot_path,
            title=f"Multi-Horizon Transformer Backtest | horizon={hz}",
            max_points=int(args.plot_max_points),
            max_features=int(args.plot_max_features),
        )
        print(f"[{hz}] pred -> {pred_path}")
        print(f"[{hz}] plot -> {plot_path}")
        print(f"[{hz}] focus -> {','.join(hz_plot_features)}")

    print(f"Metrics -> {metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
