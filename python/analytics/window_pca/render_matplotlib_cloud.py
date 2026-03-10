#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Noninteractive 3D matplotlib scatter from existing PCA point/voxel parquet.")
    p.add_argument("--input-parquet", required=True, help="Input parquet file")
    p.add_argument("--mode", choices=["auto", "points", "voxels"], default="auto")
    p.add_argument("--x-col", default="")
    p.add_argument("--y-col", default="")
    p.add_argument("--z-col", default="")
    p.add_argument("--color-col", default="", help="Optional color column")
    p.add_argument("--max-points", type=int, default=1_500_000)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--point-size", type=float, default=0.8)
    p.add_argument("--alpha", type=float, default=0.08)
    p.add_argument("--x-min", type=float, default=None)
    p.add_argument("--x-max", type=float, default=None)
    p.add_argument("--y-min", type=float, default=None)
    p.add_argument("--y-max", type=float, default=None)
    p.add_argument("--z-min", type=float, default=None)
    p.add_argument("--z-max", type=float, default=None)
    p.add_argument(
        "--fit-quantile",
        type=float,
        default=0.0,
        help="If in (0,1], keep the central quantile of points (e.g. 0.99).",
    )
    p.add_argument(
        "--fit-method",
        choices=["axis", "mahal"],
        default="axis",
        help="axis=per-axis central quantiles; mahal=Mahalanobis core.",
    )
    p.add_argument("--elev", type=float, default=24.0)
    p.add_argument("--azim", type=float, default=-60.0)
    p.add_argument("--title", default="PCA bounded scatter")
    p.add_argument("--out-png", required=True)
    return p


def _infer_mode(df: pd.DataFrame, mode: str) -> str:
    if mode != "auto":
        return mode
    if {"pca1", "pca2", "pca3"}.issubset(df.columns):
        return "points"
    if {"pc1", "pc2", "pc3"}.issubset(df.columns):
        return "voxels"
    raise SystemExit("Could not infer mode. Provide --mode and --x-col/--y-col/--z-col.")


def _infer_xyz(df: pd.DataFrame, mode: str, x_col: str, y_col: str, z_col: str) -> tuple[str, str, str]:
    if x_col and y_col and z_col:
        return x_col, y_col, z_col
    if mode == "points" and {"pca1", "pca2", "pca3"}.issubset(df.columns):
        return "pca1", "pca2", "pca3"
    if mode == "voxels" and {"pc1", "pc2", "pc3"}.issubset(df.columns):
        return "pc1", "pc2", "pc3"
    raise SystemExit("Missing coordinate columns; pass --x-col --y-col --z-col.")


def main() -> None:
    args = _build_argparser().parse_args()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    inp = Path(args.input_parquet)
    if not inp.exists():
        raise SystemExit(f"input parquet not found: {inp}")
    df = pd.read_parquet(inp)
    if len(df) == 0:
        raise SystemExit("input parquet is empty")

    mode = _infer_mode(df, str(args.mode))
    x_col, y_col, z_col = _infer_xyz(df, mode, str(args.x_col), str(args.y_col), str(args.z_col))

    work = df.copy()
    for c in (x_col, y_col, z_col):
        work[c] = pd.to_numeric(work[c], errors="coerce")
    work = work[np.isfinite(work[x_col]) & np.isfinite(work[y_col]) & np.isfinite(work[z_col])].copy()
    if len(work) == 0:
        raise SystemExit("no finite points after coercion")

    if args.x_min is not None:
        work = work[work[x_col] >= float(args.x_min)]
    if args.x_max is not None:
        work = work[work[x_col] <= float(args.x_max)]
    if args.y_min is not None:
        work = work[work[y_col] >= float(args.y_min)]
    if args.y_max is not None:
        work = work[work[y_col] <= float(args.y_max)]
    if args.z_min is not None:
        work = work[work[z_col] >= float(args.z_min)]
    if args.z_max is not None:
        work = work[work[z_col] <= float(args.z_max)]
    if len(work) == 0:
        raise SystemExit("no points remain after bounds filtering")

    q = float(args.fit_quantile or 0.0)
    if 0.0 < q < 1.0:
        if str(args.fit_method) == "axis":
            lo = (1.0 - q) / 2.0
            hi = 1.0 - lo
            xlo, xhi = work[x_col].quantile([lo, hi]).to_numpy(dtype=np.float64)
            ylo, yhi = work[y_col].quantile([lo, hi]).to_numpy(dtype=np.float64)
            zlo, zhi = work[z_col].quantile([lo, hi]).to_numpy(dtype=np.float64)
            work = work[
                (work[x_col] >= xlo) & (work[x_col] <= xhi) &
                (work[y_col] >= ylo) & (work[y_col] <= yhi) &
                (work[z_col] >= zlo) & (work[z_col] <= zhi)
            ]
        else:
            X = work[[x_col, y_col, z_col]].to_numpy(dtype=np.float64)
            mu = np.median(X, axis=0)
            C = np.cov((X - mu).T)
            Ci = np.linalg.pinv(C)
            d2 = np.einsum("ij,jk,ik->i", X - mu, Ci, X - mu)
            thr = float(np.quantile(d2, q))
            work = work.loc[d2 <= thr]

        if len(work) == 0:
            raise SystemExit("no points remain after --fit-quantile filtering")

    if int(args.max_points) > 0 and len(work) > int(args.max_points):
        work = work.sample(n=int(args.max_points), random_state=int(args.seed))

    fig = plt.figure(figsize=(10, 9), constrained_layout=True)
    ax = fig.add_subplot(111, projection="3d")

    color_col = str(args.color_col).strip()
    if color_col and color_col in work.columns:
        c = work[color_col]
        if pd.api.types.is_numeric_dtype(c):
            cnum = pd.to_numeric(c, errors="coerce").fillna(0.0).to_numpy(dtype=np.float64)
            sc = ax.scatter(
                work[x_col], work[y_col], work[z_col],
                c=cnum, cmap="viridis", s=float(args.point_size),
                alpha=float(args.alpha), linewidths=0,
            )
            fig.colorbar(sc, ax=ax, fraction=0.03, pad=0.02, label=color_col)
        else:
            codes, _ = pd.factorize(c.astype(str).fillna("nan"), sort=True)
            ax.scatter(
                work[x_col], work[y_col], work[z_col],
                c=codes, cmap="tab20", s=float(args.point_size),
                alpha=float(args.alpha), linewidths=0,
            )
    else:
        ax.scatter(
            work[x_col], work[y_col], work[z_col],
            c="black", s=float(args.point_size),
            alpha=float(args.alpha), linewidths=0,
        )

    ax.view_init(elev=float(args.elev), azim=float(args.azim))
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.set_zlabel("PC3")
    ax.set_title(f"{args.title} (n={len(work):,})")

    out = Path(args.out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)
    print(f"[OK] wrote {out}")


if __name__ == "__main__":
    main()
