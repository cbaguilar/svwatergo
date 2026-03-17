#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Render 3-row PCA grid: audio embedding PCA, learned PLC PCA aux, real PLC PCA aux."
    )
    p.add_argument("--embedding-parquet", required=True)
    p.add_argument("--plc-parquet", required=True)
    p.add_argument("--out-png", required=True)
    p.add_argument("--projection", choices=["2d", "3d"], default="3d")
    p.add_argument("--quantile-limits", default="1,99")
    p.add_argument("--point-size", type=float, default=8.0)
    p.add_argument("--alpha", type=float, default=0.45)
    p.add_argument("--title-prefix", default="Multilabel PCA Grid")
    p.add_argument(
        "--color-cols",
        default="ml__true_label,ml__pred_label,ml__pred_confidence_mean,ml__pred_confidence_combo,ml__exact_match,ml__hamming_error,ml__bce_loss,audio_source",
    )
    p.add_argument("--categorical-max-unique", type=int, default=24)
    return p.parse_args()


def _axis_limits(df: pd.DataFrame, cols: list[str], q0: float, q1: float):
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


def _plot_panel(fig, ax, df: pd.DataFrame, xyz_cols: list[str], color_col: str, *, point_size: float, alpha: float, categorical_max_unique: int, title: str, limits) -> None:
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
                ax.scatter(x[m], y[m], z[m], s=point_size, alpha=alpha, c=[cmap[lab]], linewidths=0.0, label=str(lab))
            else:
                ax.scatter(x[m], y[m], s=point_size, alpha=alpha, c=[cmap[lab]], linewidths=0.0, label=str(lab))
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
    x0, x1, y0, y1, z0, z1 = limits
    ax.set_title(title)
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    if z is not None and z0 is not None and z1 is not None:
        ax.set_zlabel("PC3")
        ax.set_zlim(z0, z1)
    ax.grid(alpha=0.2)


def main() -> int:
    args = _parse_args()
    emb_df = pd.read_parquet(Path(args.embedding_parquet))
    plc_df = pd.read_parquet(Path(args.plc_parquet))
    proj = str(args.projection)
    emb_cols = ["pann_true_pc1", "pann_true_pc2"] + (["pann_true_pc3"] if proj == "3d" else [])
    plc_pred_cols = ["plc_pred_pc1", "plc_pred_pc2"] + (["plc_pred_pc3"] if proj == "3d" else [])
    plc_true_cols = ["plc_true_pc1", "plc_true_pc2"] + (["plc_true_pc3"] if proj == "3d" else [])
    for cols in (emb_cols, plc_pred_cols, plc_true_cols):
        missing = [c for c in cols if c not in (emb_df.columns if cols is emb_cols else plc_df.columns)]
        if missing:
            raise SystemExit(f"missing PCA columns: {', '.join(missing)}")
    q0, q1 = [float(x.strip()) for x in str(args.quantile_limits).split(",")]
    emb_limits = _axis_limits(emb_df, emb_cols, q0, q1)
    plc_merged = pd.DataFrame(
        {
            "pc1": pd.concat([plc_df[plc_true_cols[0]], plc_df[plc_pred_cols[0]]], ignore_index=True),
            "pc2": pd.concat([plc_df[plc_true_cols[1]], plc_df[plc_pred_cols[1]]], ignore_index=True),
        }
    )
    plc_limit_cols = ["pc1", "pc2"]
    if proj == "3d":
        plc_merged["pc3"] = pd.concat([plc_df[plc_true_cols[2]], plc_df[plc_pred_cols[2]]], ignore_index=True)
        plc_limit_cols.append("pc3")
    plc_limits = _axis_limits(plc_merged, plc_limit_cols, q0, q1)
    color_cols = [c.strip() for c in str(args.color_cols).split(",") if c.strip()]
    keep_cols = [c for c in color_cols if c in emb_df.columns or c in plc_df.columns]
    ncols = len(keep_cols)
    if proj == "3d":
        fig = plt.figure(figsize=(5.2 * ncols, 13.2), constrained_layout=True)
        axes = np.empty((3, ncols), dtype=object)
        for rr in range(3):
            for cc in range(ncols):
                axes[rr, cc] = fig.add_subplot(3, ncols, rr * ncols + cc + 1, projection="3d")
    else:
        fig, axes = plt.subplots(3, ncols, figsize=(5.0 * ncols, 12.0), constrained_layout=True)
        if ncols == 1:
            axes = np.asarray(axes).reshape(3, 1)
    row_titles = ["Audio Embedding PCA", "Learned PLC PCA Aux", "Real PLC PCA Aux"]
    for j, color_col in enumerate(keep_cols):
        _plot_panel(fig, axes[0, j], emb_df, emb_cols, color_col, point_size=float(args.point_size), alpha=float(args.alpha), categorical_max_unique=int(args.categorical_max_unique), title=f"{row_titles[0]} colored by {color_col}", limits=emb_limits)
        _plot_panel(fig, axes[1, j], plc_df, plc_pred_cols, color_col, point_size=float(args.point_size), alpha=float(args.alpha), categorical_max_unique=int(args.categorical_max_unique), title=f"{row_titles[1]} colored by {color_col}", limits=plc_limits)
        _plot_panel(fig, axes[2, j], plc_df, plc_true_cols, color_col, point_size=float(args.point_size), alpha=float(args.alpha), categorical_max_unique=int(args.categorical_max_unique), title=f"{row_titles[2]} colored by {color_col}", limits=plc_limits)
    fig.suptitle(str(args.title_prefix))
    out = Path(args.out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
