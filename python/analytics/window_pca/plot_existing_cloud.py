#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build an interactive 3D scatter HTML from existing PCA point/voxel parquet outputs."
    )
    p.add_argument("--input-parquet", required=True, help="Path to existing point sample or voxel parquet")
    p.add_argument("--mode", choices=["auto", "points", "voxels"], default="auto")
    p.add_argument("--x-col", default="")
    p.add_argument("--y-col", default="")
    p.add_argument("--z-col", default="")
    p.add_argument("--count-col", default="count", help="Voxel weight/intensity column")
    p.add_argument("--color-col", default="", help="Optional column for coloring points")
    p.add_argument("--max-points", type=int, default=1_000_000, help="Random cap for rendered points")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--point-size", type=float, default=1.6)
    p.add_argument("--opacity", type=float, default=0.35)
    p.add_argument("--title", default="PCA 3D Cloud")
    p.add_argument("--out-html", required=True, help="Output interactive HTML")
    return p


def _pick_mode(df: pd.DataFrame, mode: str) -> str:
    if mode != "auto":
        return mode
    if {"pc1", "pc2", "pc3", "count"}.issubset(df.columns):
        return "voxels"
    return "points"


def _pick_xyz(df: pd.DataFrame, mode: str, x_col: str, y_col: str, z_col: str) -> tuple[str, str, str]:
    if x_col and y_col and z_col:
        return x_col, y_col, z_col
    if mode == "voxels":
        if {"pc1", "pc2", "pc3"}.issubset(df.columns):
            return "pc1", "pc2", "pc3"
    else:
        if {"pca1", "pca2", "pca3"}.issubset(df.columns):
            return "pca1", "pca2", "pca3"
        if {"pc1", "pc2", "pc3"}.issubset(df.columns):
            return "pc1", "pc2", "pc3"
    raise SystemExit("Could not infer x/y/z columns. Pass --x-col --y-col --z-col explicitly.")


def _sample_df(df: pd.DataFrame, max_points: int, seed: int) -> pd.DataFrame:
    if max_points <= 0 or len(df) <= max_points:
        return df
    return df.sample(n=int(max_points), random_state=int(seed))


def _log_color_from_count(s: pd.Series) -> np.ndarray:
    x = pd.to_numeric(s, errors="coerce").fillna(0.0).to_numpy(dtype=np.float64)
    return np.log1p(np.maximum(0.0, x))


def main() -> None:
    args = _build_argparser().parse_args()
    try:
        import plotly.express as px  # type: ignore
    except Exception as e:
        raise SystemExit(f"Missing plotly. Install with: pip install plotly. Error: {e}") from e

    inp = Path(args.input_parquet)
    if not inp.exists():
        raise SystemExit(f"input parquet does not exist: {inp}")
    df = pd.read_parquet(inp)
    if len(df) == 0:
        raise SystemExit("input parquet is empty")

    mode = _pick_mode(df, str(args.mode))
    x_col, y_col, z_col = _pick_xyz(df, mode, str(args.x_col), str(args.y_col), str(args.z_col))

    work = df.copy()
    for c in (x_col, y_col, z_col):
        work[c] = pd.to_numeric(work[c], errors="coerce")
    work = work[np.isfinite(work[x_col]) & np.isfinite(work[y_col]) & np.isfinite(work[z_col])].copy()
    work = _sample_df(work, int(args.max_points), int(args.seed))
    if len(work) == 0:
        raise SystemExit("no finite points after filtering/sampling")

    color_col: Optional[str] = None
    if str(args.color_col).strip() and str(args.color_col) in work.columns:
        color_col = str(args.color_col)
    elif mode == "voxels" and str(args.count_col) in work.columns:
        tmp_name = "__log_count_color"
        work[tmp_name] = _log_color_from_count(work[str(args.count_col)])
        color_col = tmp_name

    fig = px.scatter_3d(
        work,
        x=x_col,
        y=y_col,
        z=z_col,
        color=color_col,
        color_continuous_scale="Viridis" if color_col else None,
        opacity=float(args.opacity),
        title=f"{args.title} ({mode}, n={len(work):,})",
    )
    fig.update_traces(marker=dict(size=float(args.point_size)))
    fig.update_layout(scene=dict(xaxis_title="PC1", yaxis_title="PC2", zaxis_title="PC3"))

    out = Path(args.out_html)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out), include_plotlyjs="cdn", full_html=True)
    print(f"[OK] wrote {out}")


if __name__ == "__main__":
    main()
