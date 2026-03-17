from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd


DEFAULT_METRICS = [
    "macro_f1",
    "exact_match",
    "f1__deliveryrun_duty_target",
    "f1__feedpumprun_duty_target",
    "f1__ropumprun_duty_target",
    "f1__wellpumprun_duty_target",
]


def _parse_label_map(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in str(text or "").split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _metric_title(metric: str) -> str:
    mapping = {
        "macro_f1": "Macro F1",
        "exact_match": "Exact Match",
        "f1__deliveryrun_duty_target": "Deliveryrun F1",
        "f1__feedpumprun_duty_target": "Feedpump F1",
        "f1__ropumprun_duty_target": "RO Pump F1",
        "f1__wellpumprun_duty_target": "Wellpump F1",
        "f1__flushrun_duty_target": "Flushrun F1",
    }
    return mapping.get(metric, metric.replace("_", " "))


def _ordered_domains(df: pd.DataFrame, label_map: Dict[str, str]) -> List[str]:
    raw = sorted(set(df["train_domain"].astype(str)).union(df["eval_domain"].astype(str)))
    return [label_map.get(x, x) for x in raw]


def _apply_labels(df: pd.DataFrame, label_map: Dict[str, str]) -> pd.DataFrame:
    out = df.copy()
    out["train_domain"] = out["train_domain"].astype(str).map(lambda x: label_map.get(x, x))
    out["eval_domain"] = out["eval_domain"].astype(str).map(lambda x: label_map.get(x, x))
    return out


def _pivot_metric(df: pd.DataFrame, metric: str, order: Sequence[str]) -> pd.DataFrame:
    piv = df.pivot(index="train_domain", columns="eval_domain", values=metric)
    piv = piv.reindex(index=list(order), columns=list(order))
    return piv.astype(float)


def _draw_heatmap(
    ax,
    data: pd.DataFrame,
    *,
    title: str,
    cmap: str,
    vmin: float | None = None,
    vmax: float | None = None,
    fmt: str = ".3f",
    text_color_threshold: float | None = None,
):
    import matplotlib.pyplot as plt  # type: ignore

    arr = data.to_numpy(dtype=float)
    im = ax.imshow(arr, cmap=cmap, vmin=vmin, vmax=vmax, aspect="equal")
    ax.set_title(title, fontsize=11)
    ax.set_xticks(np.arange(len(data.columns)))
    ax.set_yticks(np.arange(len(data.index)))
    ax.set_xticklabels(list(data.columns), rotation=25, ha="right")
    ax.set_yticklabels(list(data.index))
    ax.set_xlabel("Eval Domain")
    ax.set_ylabel("Train Domain")
    ax.set_xticks(np.arange(-0.5, len(data.columns), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(data.index), 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=0.8, alpha=0.6)
    ax.tick_params(which="minor", bottom=False, left=False)

    finite = arr[np.isfinite(arr)]
    threshold = float(np.nanmean(finite)) if (text_color_threshold is None and finite.size) else text_color_threshold
    if threshold is None:
        threshold = 0.0
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            val = arr[i, j]
            label = "NA" if not np.isfinite(val) else format(float(val), fmt)
            color = "white" if np.isfinite(val) and float(val) >= float(threshold) else "black"
            ax.text(j, i, label, ha="center", va="center", fontsize=9, color=color)
    return im


def _save_metric_panel(
    *,
    out_path: Path,
    metric: str,
    baseline: pd.DataFrame,
    improved: pd.DataFrame | None,
    baseline_label: str,
    improved_label: str | None,
):
    import matplotlib.pyplot as plt  # type: ignore

    if improved is None:
        fig, ax = plt.subplots(1, 1, figsize=(5.8, 5.2), constrained_layout=True)
        im = _draw_heatmap(
            ax,
            baseline,
            title=f"{_metric_title(metric)} | {baseline_label}",
            cmap="viridis",
            vmin=0.0,
            vmax=1.0,
        )
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    else:
        delta = improved - baseline
        vmax_delta = float(np.nanmax(np.abs(delta.to_numpy(dtype=float)))) if np.isfinite(delta.to_numpy(dtype=float)).any() else 0.1
        vmax_delta = max(vmax_delta, 0.05)
        fig, axes = plt.subplots(1, 3, figsize=(16.0, 5.2), constrained_layout=True)
        im0 = _draw_heatmap(
            axes[0],
            baseline,
            title=f"{_metric_title(metric)} | {baseline_label}",
            cmap="viridis",
            vmin=0.0,
            vmax=1.0,
        )
        im1 = _draw_heatmap(
            axes[1],
            improved,
            title=f"{_metric_title(metric)} | {improved_label}",
            cmap="viridis",
            vmin=0.0,
            vmax=1.0,
        )
        im2 = _draw_heatmap(
            axes[2],
            delta,
            title=f"{_metric_title(metric)} | Delta",
            cmap="coolwarm",
            vmin=-vmax_delta,
            vmax=vmax_delta,
            fmt="+.3f",
            text_color_threshold=0.0,
        )
        fig.colorbar(im0, ax=axes[0], fraction=0.046, pad=0.04)
        fig.colorbar(im1, ax=axes[1], fraction=0.046, pad=0.04)
        fig.colorbar(im2, ax=axes[2], fraction=0.046, pad=0.04)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def _save_summary_panel(
    *,
    out_path: Path,
    metrics: Sequence[str],
    baseline: Dict[str, pd.DataFrame],
    improved: Dict[str, pd.DataFrame] | None,
    baseline_label: str,
    improved_label: str | None,
):
    import matplotlib.pyplot as plt  # type: ignore

    n = len(metrics)
    cols = 2
    rows = int(np.ceil(n / cols))
    if improved is None:
        fig, axes = plt.subplots(rows, cols, figsize=(10.5, 4.6 * rows), constrained_layout=True)
        axes = np.atleast_1d(axes).reshape(rows, cols)
        for ax, metric in zip(axes.flat, metrics):
            im = _draw_heatmap(
                ax,
                baseline[metric],
                title=f"{_metric_title(metric)} | {baseline_label}",
                cmap="viridis",
                vmin=0.0,
                vmax=1.0,
            )
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        for ax in axes.flat[n:]:
            ax.axis("off")
    else:
        fig, axes = plt.subplots(rows, cols, figsize=(10.5, 4.6 * rows), constrained_layout=True)
        axes = np.atleast_1d(axes).reshape(rows, cols)
        for ax, metric in zip(axes.flat, metrics):
            delta = improved[metric] - baseline[metric]
            vmax_delta = float(np.nanmax(np.abs(delta.to_numpy(dtype=float)))) if np.isfinite(delta.to_numpy(dtype=float)).any() else 0.1
            vmax_delta = max(vmax_delta, 0.05)
            im = _draw_heatmap(
                ax,
                delta,
                title=f"{_metric_title(metric)} | {improved_label} - {baseline_label}",
                cmap="coolwarm",
                vmin=-vmax_delta,
                vmax=vmax_delta,
                fmt="+.3f",
                text_color_threshold=0.0,
            )
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        for ax in axes.flat[n:]:
            ax.axis("off")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description="Render site generalization heatmaps from matrix summary CSVs.")
    p.add_argument("--baseline-csv", required=True, help="Baseline site_matrix_summary.csv")
    p.add_argument("--improved-csv", default="", help="Optional improved site_matrix_summary.csv")
    p.add_argument("--baseline-label", default="Baseline")
    p.add_argument("--improved-label", default="Improved")
    p.add_argument("--metrics", default=",".join(DEFAULT_METRICS))
    p.add_argument(
        "--site-label-map",
        default="bluerock=Site A,santateresa=Site B,pryorfarm=Site C,all_sites=All Sites",
        help="Comma-separated raw=display label mapping",
    )
    p.add_argument("--out-dir", required=True)
    args = p.parse_args()

    baseline_csv = Path(args.baseline_csv)
    improved_csv = Path(args.improved_csv) if str(args.improved_csv).strip() else None
    out_dir = Path(args.out_dir)
    metrics = [m.strip() for m in str(args.metrics).split(",") if m.strip()]
    label_map = _parse_label_map(args.site_label_map)

    df_base = _apply_labels(pd.read_csv(baseline_csv), label_map)
    df_imp = _apply_labels(pd.read_csv(improved_csv), label_map) if improved_csv else None
    order = _ordered_domains(pd.concat([x for x in [df_base, df_imp] if x is not None], ignore_index=True), {})
    if "All Sites" in order:
        order = [x for x in order if x != "All Sites"] + ["All Sites"]

    base_tables = {metric: _pivot_metric(df_base, metric, order) for metric in metrics}
    imp_tables = {metric: _pivot_metric(df_imp, metric, order) for metric in metrics} if df_imp is not None else None

    for metric in metrics:
        _save_metric_panel(
            out_path=out_dir / f"{metric}_heatmaps.png",
            metric=metric,
            baseline=base_tables[metric],
            improved=(imp_tables[metric] if imp_tables is not None else None),
            baseline_label=str(args.baseline_label),
            improved_label=(str(args.improved_label) if imp_tables is not None else None),
        )

    _save_summary_panel(
        out_path=out_dir / "summary_baseline.png",
        metrics=metrics,
        baseline=base_tables,
        improved=None,
        baseline_label=str(args.baseline_label),
        improved_label=None,
    )
    if imp_tables is not None:
        _save_summary_panel(
            out_path=out_dir / "summary_delta.png",
            metrics=metrics,
            baseline=base_tables,
            improved=imp_tables,
            baseline_label=str(args.baseline_label),
            improved_label=str(args.improved_label),
        )

    print(f"[ok] wrote heatmaps -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
