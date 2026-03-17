#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd


def _load(df_path: str, *, time_col: str, state_col: str) -> pd.DataFrame:
    df = pd.read_parquet(df_path).copy()
    if time_col not in df.columns:
        raise ValueError(f"Missing time column: {time_col}")
    if state_col not in df.columns:
        raise ValueError(f"Missing state column: {state_col}")
    df[time_col] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
    df = df[df[time_col].notna()].copy()
    df[state_col] = df[state_col].astype(str)
    conf_col = "pred_confidence" if "pred_confidence" in df.columns else None
    if conf_col is not None:
        df[conf_col] = pd.to_numeric(df[conf_col], errors="coerce")
    return df.sort_values(time_col, kind="mergesort").reset_index(drop=True)


def _state_palette(states: Sequence[str]) -> Dict[str, tuple]:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as e:
        raise SystemExit("Missing matplotlib. Install: pip install matplotlib") from e
    cmap = plt.get_cmap("tab20")
    uniq = [str(x) for x in states]
    return {s: cmap(i % cmap.N) for i, s in enumerate(uniq)}


def _plot_ribbon(ax, df: pd.DataFrame, *, time_col: str, state_col: str, palette: Dict[str, tuple], title: str) -> None:
    times = pd.to_datetime(df[time_col], utc=True, errors="coerce")
    states = df[state_col].astype(str).tolist()
    y = np.zeros((1, len(states)), dtype=np.int64)
    code_map = {s: i for i, s in enumerate(palette.keys())}
    for i, s in enumerate(states):
        y[0, i] = code_map[str(s)]
    colors = [palette[s] for s in palette.keys()]
    from matplotlib.colors import ListedColormap  # type: ignore

    cmap = ListedColormap(colors)
    t_num = times.view("int64").to_numpy(dtype=np.int64, copy=False)
    if len(t_num) == 1:
        t_num = np.asarray([t_num[0], t_num[0] + 1], dtype=np.int64)
        y = np.repeat(y, 2, axis=1)
    ax.imshow(
        y,
        aspect="auto",
        interpolation="nearest",
        cmap=cmap,
        extent=[float(t_num[0]), float(t_num[-1]), 0.0, 1.0],
    )
    ax.set_yticks([])
    ax.set_title(title)


def main() -> int:
    p = argparse.ArgumentParser(description="Plot inferred state over time for one or two day-level parquet files")
    p.add_argument("--inference-parquet", required=True, help="Primary inference parquet")
    p.add_argument("--time-col", default="segment_start_ts_utc")
    p.add_argument("--state-col", default="pred_label")
    p.add_argument("--title", default="Inferred Day")
    p.add_argument("--reference-parquet", default="", help="Optional second parquet to compare against")
    p.add_argument("--reference-time-col", default="segment_start_ts_utc")
    p.add_argument("--reference-state-col", default="true_label")
    p.add_argument("--reference-title", default="Reference Day")
    p.add_argument("--out-png", required=True)
    args = p.parse_args()

    primary = _load(args.inference_parquet, time_col=str(args.time_col), state_col=str(args.state_col))
    ref = None
    if str(args.reference_parquet).strip():
        ref = _load(
            str(args.reference_parquet),
            time_col=str(args.reference_time_col),
            state_col=str(args.reference_state_col),
        )

    all_states: List[str] = sorted(
        set(primary[str(args.state_col)].astype(str).tolist())
        | (set(ref[str(args.reference_state_col)].astype(str).tolist()) if ref is not None else set())
    )
    palette = _state_palette(all_states)

    try:
        import matplotlib.pyplot as plt  # type: ignore
        import matplotlib.dates as mdates  # type: ignore
        from matplotlib.lines import Line2D  # type: ignore
    except Exception as e:
        raise SystemExit("Missing matplotlib. Install: pip install matplotlib") from e

    nrows = 3 if ref is not None else 2
    fig, axes = plt.subplots(nrows, 1, figsize=(14, 2.4 * nrows), sharex=False, constrained_layout=True)
    axes = np.atleast_1d(axes)

    _plot_ribbon(
        axes[0],
        primary,
        time_col=str(args.time_col),
        state_col=str(args.state_col),
        palette=palette,
        title=str(args.title),
    )
    if "pred_confidence" in primary.columns:
        axes[1].plot(primary[str(args.time_col)], pd.to_numeric(primary["pred_confidence"], errors="coerce"), lw=1.2)
        axes[1].set_ylim(0.0, 1.0)
        axes[1].set_ylabel("Confidence")
        axes[1].set_title("Prediction Confidence")
    else:
        axes[1].set_visible(False)

    if ref is not None:
        _plot_ribbon(
            axes[2],
            ref,
            time_col=str(args.reference_time_col),
            state_col=str(args.reference_state_col),
            palette=palette,
            title=str(args.reference_title),
        )

    for ax in axes:
        if not ax.get_visible():
            continue
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.set_xlabel("UTC Time")

    legend_handles = [Line2D([0], [0], color=palette[s], lw=6, label=s) for s in all_states]
    fig.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(0.5, 1.02), ncol=max(1, min(5, len(all_states))))

    out_path = Path(args.out_png)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180)
    plt.close(fig)
    print(f"[ok] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
