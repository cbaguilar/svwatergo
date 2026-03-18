from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd


DEFAULT_LABEL_MAP = ",".join(
    [
        "bluerock=Site A",
        "pryorfarm=Site C",
        "santateresa=Site B",
        "all_sites=Pooled Train",
        "bluerock__rpi_audio=Site A RPi Audio",
        "bluerock__wyze_Bluerock_Cam_1=Site A Wyze Cam 1",
        "bluerock__wyze_Bluerock_Cam_2=Site A Wyze Cam 2",
        "bluerock__wyze_camera_5=Site A Wyze Cam 5",
        "pryorfarm__wyze_Pryor_Farms_1_inside_near_door=Site C Inside Near Door",
        "pryorfarm__wyze_Pryor_Farms_3_behind_ro=Site C Behind RO",
        "santateresa__wyze_Santa_Teresa_Cam_1=Site B Cam 1",
        "santateresa__wyze_Santa_Teresa_Outside=Site B Outside",
    ]
)


def _parse_label_map(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in str(text or "").split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _sanitize_label(text: str) -> str:
    s = str(text)
    replacements = [
        ("pryor_farms", "Site C"),
        ("pryorfarm", "Site C"),
        ("pryor farms", "Site C"),
        ("santa_teresa", "Site B"),
        ("santateresa", "Site B"),
        ("santa teresa", "Site B"),
        ("bluerock", "Site A"),
    ]
    lower = s.lower()
    for old, new in replacements:
        if old in lower:
            idx = lower.find(old)
            s = s[:idx] + new + s[idx + len(old) :]
            lower = s.lower()
    return s


def _apply_labels(df: pd.DataFrame, *, train_col: str, eval_col: str, label_map: Dict[str, str]) -> pd.DataFrame:
    out = df.copy()
    out[train_col] = out[train_col].astype(str).map(lambda x: _sanitize_label(label_map.get(x, x)))
    out[eval_col] = out[eval_col].astype(str).map(lambda x: _sanitize_label(label_map.get(x, x)))
    return out


def _ordered_domains(df: pd.DataFrame, *, train_col: str, eval_col: str) -> List[str]:
    raw = sorted(set(df[train_col].astype(str)).union(df[eval_col].astype(str)), key=lambda x: str(x).lower())
    for special in ("Pooled Train", "all_sites"):
        if special in raw:
            raw = [x for x in raw if x != special] + [special]
    return raw


def _pivot_metric(df: pd.DataFrame, *, train_col: str, eval_col: str, metric: str, order: Sequence[str]) -> pd.DataFrame:
    work = df.copy()
    work[metric] = pd.to_numeric(work[metric], errors="coerce")
    piv = work.pivot(index=train_col, columns=eval_col, values=metric)
    piv = piv.reindex(index=list(order), columns=list(order))
    return piv.astype(float)


def _drop_all_na_axes(data: pd.DataFrame) -> pd.DataFrame:
    keep_rows = ~data.isna().all(axis=1)
    keep_cols = ~data.isna().all(axis=0)
    return data.loc[keep_rows, keep_cols]


def _metric_title(metric: str) -> str:
    title = str(metric)
    title = title.replace("macro_f1", "Macro F1")
    title = title.replace("exact_match", "Exact Match")
    title = title.replace("r2_mean", "Mean R²")
    title = title.replace("mae_mean", "Mean MAE")
    title = title.replace("rmse_mean", "Mean RMSE")
    title = title.replace("mse_mean", "Mean MSE")
    title = title.replace("r2__", "R² ")
    title = title.replace("f1__", "F1 ")
    title = title.replace("__mean_tw", "")
    title = title.replace("_", " ")
    return title


def _metric_style(metric: str) -> Dict[str, object]:
    m = str(metric).lower()
    if "r2" in m:
        return {"cmap": "viridis", "vmin": None, "vmax": None, "fmt": ".2f", "threshold_mode": "mid"}
    if "f1" in m or "exact_match" in m or "accuracy" in m or "precision" in m or "recall" in m:
        return {"cmap": "viridis", "vmin": 0.0, "vmax": 1.0, "fmt": ".2f", "threshold_mode": "mid"}
    if "mse" in m or "rmse" in m or "mae" in m:
        return {"cmap": "magma_r", "vmin": None, "vmax": None, "fmt": ".0f", "threshold_mode": "low"}
    return {"cmap": "viridis", "vmin": None, "vmax": None, "fmt": ".2f", "threshold_mode": "mid"}


def _draw_heatmap(ax, data: pd.DataFrame, *, metric: str, title: str):
    import matplotlib.pyplot as plt  # type: ignore

    data = _drop_all_na_axes(data)
    arr = data.to_numpy(dtype=float)
    style = _metric_style(metric)

    finite = arr[np.isfinite(arr)]
    if finite.size and (style["vmin"] is None or style["vmax"] is None):
        if "r2" in str(metric).lower():
            vmax = float(np.nanmax(finite))
            vmin = float(np.nanmin(finite))
            style["vmin"] = min(vmin, 0.0)
            style["vmax"] = max(vmax, 0.0)
        else:
            style["vmin"] = float(np.nanmin(finite)) if style["vmin"] is None else style["vmin"]
            style["vmax"] = float(np.nanmax(finite)) if style["vmax"] is None else style["vmax"]

    im = ax.imshow(
        arr,
        cmap=str(style["cmap"]),
        vmin=style["vmin"],
        vmax=style["vmax"],
        aspect="equal",
    )
    ax.set_title(title, fontsize=11)
    ax.set_xticks(np.arange(len(data.columns)))
    ax.set_yticks(np.arange(len(data.index)))
    ax.set_xticklabels(list(data.columns), rotation=35, ha="right")
    ax.set_yticklabels(list(data.index))
    ax.set_xlabel("Eval Domain")
    ax.set_ylabel("Train Domain")
    ax.set_xticks(np.arange(-0.5, len(data.columns), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(data.index), 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=0.8, alpha=0.5)
    ax.tick_params(which="minor", bottom=False, left=False)

    if finite.size:
        threshold = float(np.nanmean(finite))
        if style["threshold_mode"] == "low":
            threshold = float(np.nanmedian(finite))
    else:
        threshold = 0.0

    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            val = arr[i, j]
            label = "NA" if not np.isfinite(val) else format(float(val), str(style["fmt"]))
            color = "white" if np.isfinite(val) and float(val) >= float(threshold) else "black"
            ax.text(j, i, label, ha="center", va="center", fontsize=9, color=color)
    return im


def _save_metric_panel(*, out_path: Path, metric: str, table: pd.DataFrame, title_prefix: str) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    fig, ax = plt.subplots(1, 1, figsize=(7.6, 6.2), constrained_layout=True)
    im = _draw_heatmap(ax, table, metric=metric, title=f"{title_prefix}{_metric_title(metric)}")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def _save_summary_panel(*, out_path: Path, metrics: Sequence[str], tables: Dict[str, pd.DataFrame], title_prefix: str) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    n = len(metrics)
    cols = 2
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(12.5, 5.0 * rows), constrained_layout=True)
    axes = np.atleast_1d(axes).reshape(rows, cols)
    for ax, metric in zip(axes.flat, metrics):
        im = _draw_heatmap(ax, tables[metric], metric=metric, title=f"{title_prefix}{_metric_title(metric)}")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    for ax in axes.flat[n:]:
        ax.axis("off")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description="Render heatmaps from a domain matrix summary CSV.")
    p.add_argument("--csv", required=True, help="Matrix summary CSV path")
    p.add_argument("--metrics", required=True, help="Comma-separated metrics to plot")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--train-col", default="train_domain")
    p.add_argument("--eval-col", default="eval_domain")
    p.add_argument("--label-map", default=DEFAULT_LABEL_MAP)
    p.add_argument("--title-prefix", default="")
    args = p.parse_args()

    csv_path = Path(args.csv)
    out_dir = Path(args.out_dir)
    metrics = [m.strip() for m in str(args.metrics).split(",") if m.strip()]
    label_map = _parse_label_map(args.label_map)

    df = pd.read_csv(csv_path)
    if "status" in df.columns:
        df = df[df["status"].fillna("ok").astype(str) == "ok"].copy()
    df = _apply_labels(df, train_col=str(args.train_col), eval_col=str(args.eval_col), label_map=label_map)
    order = _ordered_domains(df, train_col=str(args.train_col), eval_col=str(args.eval_col))
    tables = {metric: _pivot_metric(df, train_col=str(args.train_col), eval_col=str(args.eval_col), metric=metric, order=order) for metric in metrics}

    prefix = (str(args.title_prefix).strip() + " | ") if str(args.title_prefix).strip() else ""
    for metric in metrics:
        _save_metric_panel(
            out_path=out_dir / f"{metric}_heatmap.png",
            metric=metric,
            table=tables[metric],
            title_prefix=prefix,
        )
    _save_summary_panel(
        out_path=out_dir / "summary_heatmaps.png",
        metrics=metrics,
        tables=tables,
        title_prefix=prefix,
    )
    print(f"[ok] wrote heatmaps -> {out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
