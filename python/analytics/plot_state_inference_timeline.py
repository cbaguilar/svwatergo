#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from python.units import label_with_unit


def _load(df_path: str, *, time_col: str, state_col: Optional[str]) -> pd.DataFrame:
    df = pd.read_parquet(df_path).copy()
    if time_col not in df.columns:
        raise ValueError(f"Missing time column: {time_col}")
    if state_col is not None and state_col not in df.columns:
        raise ValueError(f"Missing state column: {state_col}")
    df[time_col] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
    df = df[df[time_col].notna()].copy()
    if state_col is not None:
        df[state_col] = df[state_col].astype(str)
    conf_col = "pred_confidence" if "pred_confidence" in df.columns else None
    if conf_col is not None:
        df[conf_col] = pd.to_numeric(df[conf_col], errors="coerce")
    return df.sort_values(time_col, kind="mergesort").reset_index(drop=True)


def _r2_score(y_true: pd.Series, y_pred: pd.Series) -> Optional[float]:
    yt = pd.to_numeric(y_true, errors="coerce")
    yp = pd.to_numeric(y_pred, errors="coerce")
    mask = yt.notna() & yp.notna()
    if int(mask.sum()) < 2:
        return None
    yt_np = yt.loc[mask].to_numpy(dtype=np.float64, copy=False)
    yp_np = yp.loc[mask].to_numpy(dtype=np.float64, copy=False)
    ss_res = float(np.sum((yt_np - yp_np) ** 2))
    yt_mean = float(np.mean(yt_np))
    ss_tot = float(np.sum((yt_np - yt_mean) ** 2))
    if ss_tot <= 0.0:
        return None
    r2 = 1.0 - (ss_res / ss_tot)
    return float(r2) if np.isfinite(r2) else None


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
    import matplotlib.dates as mdates  # type: ignore

    cmap = ListedColormap(colors)
    t_num = mdates.date2num(times.dt.to_pydatetime())
    if len(t_num) == 1:
        t_num = np.asarray(
            [
                float(t_num[0]),
                float(t_num[0] + (pd.Timedelta(seconds=1) / pd.Timedelta(days=1))),
            ],
            dtype=np.float64,
        )
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
    p.add_argument("--primary-label", default="pred")
    p.add_argument("--reference-label", default="ref")
    p.add_argument("--overlay-parquet", default="", help="Optional third parquet for extra numeric overlay traces")
    p.add_argument("--overlay-time-col", default="segment_start_ts_utc")
    p.add_argument("--overlay-label", default="overlay")
    p.add_argument("--value-cols", default="", help="Comma-separated numeric columns to plot as time-series instead of state ribbons")
    p.add_argument("--reference-value-cols", default="", help="Optional comma-separated numeric columns from reference parquet")
    p.add_argument("--overlay-value-cols", default="", help="Optional comma-separated numeric columns from overlay parquet")
    p.add_argument("--out-png", required=True)
    args = p.parse_args()

    value_cols = [str(c).strip() for c in str(args.value_cols).split(",") if str(c).strip()]
    ref_value_cols = [str(c).strip() for c in str(args.reference_value_cols).split(",") if str(c).strip()]
    overlay_value_cols = [str(c).strip() for c in str(args.overlay_value_cols).split(",") if str(c).strip()]
    state_col: Optional[str] = None if value_cols else str(args.state_col)
    ref_state_col: Optional[str] = None if value_cols else str(args.reference_state_col)

    primary = _load(args.inference_parquet, time_col=str(args.time_col), state_col=state_col)
    ref = None
    if str(args.reference_parquet).strip():
        ref = _load(
            str(args.reference_parquet),
            time_col=str(args.reference_time_col),
            state_col=ref_state_col,
        )
    overlay = None
    if str(args.overlay_parquet).strip():
        overlay = _load(
            str(args.overlay_parquet),
            time_col=str(args.overlay_time_col),
            state_col=None,
        )

    try:
        import matplotlib.pyplot as plt  # type: ignore
        import matplotlib.dates as mdates  # type: ignore
        from matplotlib.lines import Line2D  # type: ignore
    except Exception as e:
        raise SystemExit("Missing matplotlib. Install: pip install matplotlib") from e

    if value_cols:
        if ref is not None and ref_value_cols and len(ref_value_cols) != len(value_cols):
            raise ValueError("reference_value_cols must match value_cols length")
        if ref is not None and not ref_value_cols:
            ref_value_cols = value_cols
        if overlay is not None and overlay_value_cols and len(overlay_value_cols) != len(value_cols):
            raise ValueError("overlay_value_cols must match value_cols length")
        if overlay is not None and not overlay_value_cols:
            overlay_value_cols = value_cols
        nrows = len(value_cols)
        fig, axes = plt.subplots(nrows, 1, figsize=(14, 2.5 * max(1, nrows)), sharex=False, constrained_layout=True)
        axes = np.atleast_1d(axes)
        primary_label = str(args.primary_label).strip() or "pred"
        reference_label = str(args.reference_label).strip() or "ref"
        overlay_label = str(args.overlay_label).strip() or "overlay"
        for i, col in enumerate(value_cols):
            if col not in primary.columns:
                raise ValueError(f"Missing value column in inference parquet: {col}")
            ax = axes[i]
            pred_series = pd.to_numeric(primary[col], errors="coerce")
            title = label_with_unit(col)
            primary_legend = primary_label
            ref_series = None
            if ref is not None:
                ref_col = ref_value_cols[i]
                if ref_col not in ref.columns:
                    raise ValueError(f"Missing reference value column: {ref_col}")
                ref_series = pd.to_numeric(ref[ref_col], errors="coerce")
                r2 = _r2_score(ref_series, pred_series)
                if r2 is not None:
                    primary_legend = f"{primary_label} (R2={r2:.3f})"
            ax.plot(primary[str(args.time_col)], pred_series, lw=1.2, label=primary_legend)
            if ref is not None:
                ax.plot(ref[str(args.reference_time_col)], ref_series, lw=1.2, alpha=0.85, label=reference_label)
            if overlay is not None:
                overlay_col = overlay_value_cols[i]
                if overlay_col not in overlay.columns:
                    raise ValueError(f"Missing overlay value column: {overlay_col}")
                overlay_series = pd.to_numeric(overlay[overlay_col], errors="coerce")
                overlay_legend = overlay_label
                if ref_series is not None:
                    overlay_r2 = _r2_score(ref_series, overlay_series)
                    if overlay_r2 is not None:
                        overlay_legend = f"{overlay_label} (R2={overlay_r2:.3f})"
                ax.plot(
                    overlay[str(args.overlay_time_col)],
                    overlay_series,
                    lw=1.2,
                    alpha=0.9,
                    linestyle="--",
                    label=overlay_legend,
                )
            ax.set_title(title)
            ax.set_ylabel(label_with_unit(col))
            ax.grid(alpha=0.25)
            ax.legend(loc="best")
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
            ax.set_xlabel("UTC Time")
        out_path = Path(args.out_png)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=180)
        plt.close(fig)
        print(f"[ok] wrote {out_path}", flush=True)
        return 0

    all_states: List[str] = sorted(
        set(primary[str(args.state_col)].astype(str).tolist())
        | (set(ref[str(args.reference_state_col)].astype(str).tolist()) if ref is not None else set())
    )
    palette = _state_palette(all_states)

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
