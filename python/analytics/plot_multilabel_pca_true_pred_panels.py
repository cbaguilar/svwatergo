#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Render PCA true-vs-pred panels colored by multilabel fields from pann_true_vs_pred.parquet."
    )
    p.add_argument("--input-parquet", required=True)
    p.add_argument("--out-png", required=True)
    p.add_argument("--projection", choices=["2d", "3d"], default="3d")
    p.add_argument("--layout", choices=["true_pred", "true_only"], default="true_pred")
    p.add_argument("--true-prefix", default="pann_true_pc")
    p.add_argument("--pred-prefix", default="pann_pred_pc")
    p.add_argument("--quantile-limits", default="1,99")
    p.add_argument("--point-size", type=float, default=8.0)
    p.add_argument("--alpha", type=float, default=0.45)
    p.add_argument("--title-prefix", default="Multilabel PANN PCA")
    p.add_argument(
        "--color-cols",
        default="ml__true_label,ml__pred_label,ml__pred_confidence_mean,ml__pred_confidence_combo,ml__exact_match,ml__hamming_error,ml__bce_loss,audio_source",
        help="Comma-separated columns to color by",
    )
    p.add_argument(
        "--categorical-max-unique",
        type=int,
        default=24,
        help="Auto-treat numeric columns with <= this many unique values as categorical",
    )
    return p.parse_args()


def _axis_limits(
    df: pd.DataFrame,
    cols: list[str],
    q0: float,
    q1: float,
) -> tuple[float, float, float, float, float | None, float | None]:
    x0, x1 = np.percentile(pd.to_numeric(df[cols[0]], errors="coerce").dropna(), [q0, q1])
    y0, y1 = np.percentile(pd.to_numeric(df[cols[1]], errors="coerce").dropna(), [q0, q1])
    if len(cols) >= 3:
        z0, z1 = np.percentile(pd.to_numeric(df[cols[2]], errors="coerce").dropna(), [q0, q1])
        return float(x0), float(x1), float(y0), float(y1), float(z0), float(z1)
    return float(x0), float(x1), float(y0), float(y1), None, None


def _is_categorical(series: pd.Series, categorical_max_unique: int) -> bool:
    if not pd.api.types.is_numeric_dtype(series):
        return True
    return 0 < int(series.nunique(dropna=True)) <= int(categorical_max_unique)


def _plot_panel(
    fig,
    ax,
    df: pd.DataFrame,
    *,
    xyz_cols: list[str],
    color_col: str,
    point_size: float,
    alpha: float,
    categorical_max_unique: int,
    title: str,
    limits: tuple[float, float, float, float, float | None, float | None],
) -> None:
    x = pd.to_numeric(df[xyz_cols[0]], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(df[xyz_cols[1]], errors="coerce").to_numpy(dtype=float)
    z = pd.to_numeric(df[xyz_cols[2]], errors="coerce").to_numpy(dtype=float) if len(xyz_cols) >= 3 else None
    valid = np.isfinite(x) & np.isfinite(y)
    if z is not None:
        valid &= np.isfinite(z)

    s = df[color_col] if color_col in df.columns else pd.Series(["missing"] * len(df), dtype="string")
    if _is_categorical(s, categorical_max_unique):
        cats = s.astype("string").fillna("<NA>").astype(str)
        labels = sorted(cats[valid].unique().tolist())
        pal = plt.cm.tab20(np.linspace(0.0, 1.0, max(1, len(labels))))
        cmap = {lab: pal[i] for i, lab in enumerate(labels)}
        for lab in labels:
            m = valid & (cats.to_numpy() == lab)
            if int(np.sum(m)) <= 0:
                continue
            if z is not None:
                ax.scatter(x[m], y[m], z[m], s=point_size, alpha=alpha, c=[cmap[lab]], label=str(lab), linewidths=0.0)
            else:
                ax.scatter(x[m], y[m], s=point_size, alpha=alpha, c=[cmap[lab]], label=str(lab), linewidths=0.0)
        if len(labels) <= 12:
            ax.legend(fontsize=7, loc="best", framealpha=0.9)
    else:
        v = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
        finite = valid & np.isfinite(v)
        if finite.any():
            lo = float(np.nanquantile(v[finite], 0.01))
            hi = float(np.nanquantile(v[finite], 0.99))
            if hi <= lo:
                lo = float(np.nanmin(v[finite]))
                hi = float(np.nanmax(v[finite]) + 1e-9)
            vv = np.clip(v, lo, hi)
            if z is not None:
                sc = ax.scatter(x[valid], y[valid], z[valid], c=vv[valid], s=point_size, alpha=alpha, cmap="viridis", vmin=lo, vmax=hi, linewidths=0.0)
            else:
                sc = ax.scatter(x[valid], y[valid], c=vv[valid], s=point_size, alpha=alpha, cmap="viridis", vmin=lo, vmax=hi, linewidths=0.0)
            cb = fig.colorbar(sc, ax=ax, fraction=0.04, pad=0.03)
            cb.ax.tick_params(labelsize=7)
        else:
            if z is not None:
                ax.scatter(x[valid], y[valid], z[valid], s=point_size, alpha=alpha, c="#777777", linewidths=0.0)
            else:
                ax.scatter(x[valid], y[valid], s=point_size, alpha=alpha, c="#777777", linewidths=0.0)

    ax.set_title(title)
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    x0, x1, y0, y1, z0, z1 = limits
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    if z is not None and z0 is not None and z1 is not None:
        ax.set_zlabel("PC3")
        ax.set_zlim(z0, z1)
    ax.grid(alpha=0.2)


def main() -> int:
    args = _parse_args()
    inp = Path(args.input_parquet)
    if not inp.exists():
        raise SystemExit(f"input parquet not found: {inp}")
    df = pd.read_parquet(inp)
    if df.empty:
        raise SystemExit("input parquet is empty")

    proj = str(args.projection)
    layout = str(args.layout)
    true_cols = [f"{args.true_prefix}{i}" for i in (1, 2)] + ([f"{args.true_prefix}3"] if proj == "3d" else [])
    pred_cols = [f"{args.pred_prefix}{i}" for i in (1, 2)] + ([f"{args.pred_prefix}3"] if proj == "3d" else [])
    req = list(true_cols)
    if layout == "true_pred":
        req += pred_cols
    missing = [c for c in req if c not in df.columns]
    if missing:
        raise SystemExit(f"missing PCA columns: {', '.join(missing)}")

    q_parts = [x.strip() for x in str(args.quantile_limits).split(",") if x.strip()]
    if len(q_parts) != 2:
        raise SystemExit("--quantile-limits must be lower,upper")
    q0, q1 = float(q_parts[0]), float(q_parts[1])
    merged = pd.DataFrame(
        {
            "pc1": pd.concat(
                [df[true_cols[0]]] + ([df[pred_cols[0]]] if layout == "true_pred" else []),
                ignore_index=True,
            ),
            "pc2": pd.concat(
                [df[true_cols[1]]] + ([df[pred_cols[1]]] if layout == "true_pred" else []),
                ignore_index=True,
            ),
        }
    )
    limit_cols = ["pc1", "pc2"]
    if proj == "3d":
        merged["pc3"] = pd.concat(
            [df[true_cols[2]]] + ([df[pred_cols[2]]] if layout == "true_pred" else []),
            ignore_index=True,
        )
        limit_cols.append("pc3")
    limits = _axis_limits(merged, limit_cols, q0, q1)

    color_cols = [c.strip() for c in str(args.color_cols).split(",") if c.strip()]
    keep_cols = [c for c in color_cols if c in df.columns]
    if not keep_cols:
        raise SystemExit("none of the requested color columns exist in the parquet")

    ncols = len(keep_cols)
    nrows = 2 if layout == "true_pred" else 1
    if proj == "3d":
        fig = plt.figure(figsize=(5.2 * ncols, 4.8 if nrows == 1 else 9.2), constrained_layout=True)
        axes = np.empty((nrows, ncols), dtype=object)
        for rr in range(nrows):
            for cc in range(ncols):
                axes[rr, cc] = fig.add_subplot(nrows, ncols, rr * ncols + cc + 1, projection="3d")
    else:
        fig, axes = plt.subplots(nrows, ncols, figsize=(5.0 * ncols, 4.2 if nrows == 1 else 8.0), constrained_layout=True)
        if ncols == 1:
            axes = np.asarray(axes).reshape(nrows, 1)
        elif nrows == 1:
            axes = np.asarray(axes).reshape(1, ncols)

    for j, color_col in enumerate(keep_cols):
        _plot_panel(
            fig,
            axes[0, j],
            df,
            xyz_cols=true_cols,
            color_col=color_col,
            point_size=float(args.point_size),
            alpha=float(args.alpha),
            categorical_max_unique=int(args.categorical_max_unique),
            title=f"True PCA colored by {color_col}",
            limits=limits,
        )
        if layout == "true_pred":
            _plot_panel(
                fig,
                axes[1, j],
                df,
                xyz_cols=pred_cols,
                color_col=color_col,
                point_size=float(args.point_size),
                alpha=float(args.alpha),
                categorical_max_unique=int(args.categorical_max_unique),
                title=f"Pred PCA colored by {color_col}",
                limits=limits,
            )

    fig.suptitle(str(args.title_prefix))
    out = Path(args.out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
