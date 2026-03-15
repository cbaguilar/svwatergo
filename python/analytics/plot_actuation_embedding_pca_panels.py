#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D


ACTUATORS = (
    "ropumprun",
    "wellpumprun",
    "feedpumprun",
    "deliveryrun",
    "inletrun",
    "flushrun",
    "concbypassrun",
    "proddiversionrun",
)

STATE_COLORS = {
    "off": "#4c78a8",
    "transition": "#f58518",
    "on": "#54a24b",
    "unknown": "#9d9da1",
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Render 2D/3D PCA plots from actuation embedding PCA points parquet: one top-bits plot "
            "plus one plot per actuator state."
        )
    )
    p.add_argument("--input-parquet", required=True, help="PCA points parquet from audio_embedding_pca_plot")
    p.add_argument("--out-dir", required=True, help="Directory for output PNGs")
    p.add_argument("--x-col", default="pca1")
    p.add_argument("--y-col", default="pca2")
    p.add_argument("--z-col", default="pca3")
    p.add_argument("--projection", default="3d", choices=["2d", "3d"])
    p.add_argument("--combo-col", default="actuation_bits")
    p.add_argument("--combo-top-k", type=int, default=12)
    p.add_argument("--drop-unknown", default="yes", choices=["yes", "no"])
    p.add_argument("--quantile-limits", default="1,99", help="Lower,upper percentiles for shared axis limits")
    p.add_argument("--point-size", type=float, default=10.0)
    p.add_argument("--alpha", type=float, default=0.6)
    p.add_argument("--title-prefix", default="Bluerock PANN Embedding PCA")
    return p.parse_args()


def _axis_limits(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    z_col: str,
    quantiles: tuple[float, float],
    projection: str,
) -> tuple[float, float, float, float, float, float | None]:
    q0, q1 = quantiles
    x0, x1 = np.percentile(pd.to_numeric(df[x_col], errors="coerce").dropna(), [q0, q1])
    y0, y1 = np.percentile(pd.to_numeric(df[y_col], errors="coerce").dropna(), [q0, q1])
    if projection == "3d":
        z0, z1 = np.percentile(pd.to_numeric(df[z_col], errors="coerce").dropna(), [q0, q1])
        return float(x0), float(x1), float(y0), float(y1), float(z0), float(z1)
    return float(x0), float(x1), float(y0), float(y1), 0.0, None


def _apply_common_style(ax, *, title: str, x_label: str, y_label: str, z_label: str, limits) -> None:
    x0, x1, y0, y1, z0, z1 = limits
    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    if z1 is not None:
        ax.set_zlabel(z_label)
        ax.set_zlim(z0, z1)
    ax.grid(alpha=0.2)


def _legend_handles(labels, colors):
    return [
        Line2D([0], [0], marker="o", linestyle="", markersize=6, markerfacecolor=color, markeredgewidth=0, label=str(label))
        for label, color in zip(labels, colors)
    ]


def _plot_combo_bits(
    df: pd.DataFrame,
    *,
    out_path: Path,
    x_col: str,
    y_col: str,
    z_col: str,
    projection: str,
    combo_col: str,
    top_k: int,
    point_size: float,
    alpha: float,
    title_prefix: str,
    limits,
) -> None:
    cats = df[combo_col].astype("string").fillna("<NA>").astype(str)
    top = cats.value_counts().head(max(1, int(top_k))).index.tolist()
    plot_label = cats.where(cats.isin(top), other="OTHER")
    uniq = sorted(plot_label.unique().tolist())

    fig = plt.figure(figsize=(11, 8), dpi=160)
    ax = fig.add_subplot(111, projection=("3d" if projection == "3d" else None))
    cmap = plt.get_cmap("tab20", max(len(uniq), 1))
    handle_colors = []
    for i, label in enumerate(uniq):
        m = plot_label.to_numpy() == label
        color = cmap(i)
        handle_colors.append(color)
        if projection == "3d":
            ax.scatter(
                df.loc[m, x_col],
                df.loc[m, y_col],
                df.loc[m, z_col],
                s=float(point_size),
                alpha=float(alpha),
                color=color,
                linewidths=0.0,
            )
        else:
            ax.scatter(
                df.loc[m, x_col],
                df.loc[m, y_col],
                s=float(point_size),
                alpha=float(alpha),
                color=color,
                linewidths=0.0,
            )

    _apply_common_style(
        ax,
        title=f"{title_prefix} | top actuation bit patterns",
        x_label="PCA 1",
        y_label="PCA 2",
        z_label="PCA 3",
        limits=limits,
    )
    ax.legend(
        handles=_legend_handles(uniq, handle_colors),
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        fontsize=8,
        framealpha=0.9,
        title=combo_col,
    )
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def _plot_one_actuator(
    df: pd.DataFrame,
    *,
    out_path: Path,
    actuator: str,
    x_col: str,
    y_col: str,
    z_col: str,
    projection: str,
    point_size: float,
    alpha: float,
    title_prefix: str,
    limits,
) -> None:
    state_col = f"{actuator}_state"
    if state_col not in df.columns:
        return

    ser = df[state_col].astype("string").fillna("unknown").astype(str)
    order = [s for s in ("off", "transition", "on", "unknown") if s in set(ser.tolist())]
    if not order:
        return

    fig = plt.figure(figsize=(10, 7.5), dpi=160)
    ax = fig.add_subplot(111, projection=("3d" if projection == "3d" else None))
    handle_colors = []
    for state in order:
        m = ser.to_numpy() == state
        color = STATE_COLORS.get(state, "#444444")
        handle_colors.append(color)
        if projection == "3d":
            ax.scatter(
                df.loc[m, x_col],
                df.loc[m, y_col],
                df.loc[m, z_col],
                s=float(point_size),
                alpha=float(alpha),
                color=color,
                linewidths=0.0,
            )
        else:
            ax.scatter(
                df.loc[m, x_col],
                df.loc[m, y_col],
                s=float(point_size),
                alpha=float(alpha),
                color=color,
                linewidths=0.0,
            )

    _apply_common_style(
        ax,
        title=f"{title_prefix} | {actuator} state",
        x_label="PCA 1",
        y_label="PCA 2",
        z_label="PCA 3",
        limits=limits,
    )
    ax.legend(handles=_legend_handles(order, handle_colors), loc="best", fontsize=9, framealpha=0.9, title=actuator)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    args = _parse_args()
    inp = Path(args.input_parquet)
    if not inp.exists():
        raise SystemExit(f"input parquet not found: {inp}")

    df = pd.read_parquet(inp)
    if df.empty:
        raise SystemExit("input parquet is empty")

    x_col = str(args.x_col)
    y_col = str(args.y_col)
    z_col = str(args.z_col)
    projection = str(args.projection)
    combo_col = str(args.combo_col)
    required = [x_col, y_col] + ([z_col] if projection == "3d" else [])
    if any(c not in df.columns for c in required):
        raise SystemExit(f"missing PCA columns: {', '.join(required)}")
    if combo_col not in df.columns:
        raise SystemExit(f"missing combo column: {combo_col}")

    work = df.copy()
    if str(args.drop_unknown) == "yes" and "actuation_combo" in work.columns:
        work = work[~work["actuation_combo"].astype(str).str.contains("unknown", na=False)].copy()
    if work.empty:
        raise SystemExit("no rows left after unknown filtering")

    q_parts = [x.strip() for x in str(args.quantile_limits).split(",") if x.strip()]
    if len(q_parts) != 2:
        raise SystemExit("--quantile-limits must be lower,upper")
    q0, q1 = float(q_parts[0]), float(q_parts[1])
    limits = _axis_limits(work, x_col=x_col, y_col=y_col, z_col=z_col, quantiles=(q0, q1), projection=projection)

    out_dir = Path(args.out_dir)
    _plot_combo_bits(
        work,
        out_path=out_dir / "actuation_bits_topk.png",
        x_col=x_col,
        y_col=y_col,
        z_col=z_col,
        projection=projection,
        combo_col=combo_col,
        top_k=int(args.combo_top_k),
        point_size=float(args.point_size),
        alpha=float(args.alpha),
        title_prefix=str(args.title_prefix),
        limits=limits,
    )
    print(f"[ok] wrote {out_dir / 'actuation_bits_topk.png'}", flush=True)

    for actuator in ACTUATORS:
        out_path = out_dir / f"{actuator}_state.png"
        _plot_one_actuator(
            work,
            out_path=out_path,
            actuator=actuator,
            x_col=x_col,
            y_col=y_col,
            z_col=z_col,
            projection=projection,
            point_size=float(args.point_size),
            alpha=float(args.alpha),
            title_prefix=str(args.title_prefix),
            limits=limits,
        )
        if out_path.exists():
            print(f"[ok] wrote {out_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
