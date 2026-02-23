from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

try:
    import joblib  # type: ignore
except Exception as e:
    raise SystemExit("Missing joblib. Install: pip install joblib") from e

from .io import write_json_local, write_s3_bytes
from .loader import load_many
from .model import fit_pca, print_pca_loadings, transform_pca
from .plotting import plot_pca_2d_live, plot_pca_2d_webgl, plot_pca_3d
from .selection import select_pca_columns


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fit PCA on window_features parquet(s), with optional control influence weighting."
    )

    p.add_argument("--input-file", help="Local parquet path or s3://bucket/key")
    p.add_argument("--input-list", help="Text file of paths/URIs (local or s3://...), one per line")

    p.add_argument("--local-root", help="Root directory to search for parquets by site/date")
    p.add_argument("--s3-bucket", help="S3 bucket for window_features")
    p.add_argument("--s3-prefix", help="S3 prefix root (e.g. derived/) for window_features")

    p.add_argument("--site", help="Site name (for date-range loading)")
    p.add_argument("--day", help="Single day YYYY-MM-DD (UTC)")
    p.add_argument("--date-from", help="Start day YYYY-MM-DD (UTC), inclusive")
    p.add_argument("--date-to", help="End day YYYY-MM-DD (UTC), inclusive")

    p.add_argument("--window-s", type=int, default=None, help="window_s folder value if using default S3 layout")
    p.add_argument("--stride-s", type=int, default=None, help="stride_s folder value if using default S3 layout")
    p.add_argument(
        "--s3-key-template",
        default=None,
        help="Custom S3 key template (without s3://bucket/). Supports {prefix} {site} {date} {window_s} {stride_s}.",
    )

    p.add_argument("--pca-cols", default=None, help="Comma-separated explicit PCA columns (overrides regex selection)")
    p.add_argument("--include-regex", action="append", default=[], help="Regex to include columns (repeatable)")
    p.add_argument("--exclude-regex", action="append", default=[], help="Regex to exclude columns (repeatable)")
    p.add_argument("--include-cols-file", default=None, help="File with include regex patterns (one per line)")
    p.add_argument("--exclude-cols-file", default=None, help="File with exclude regex patterns (one per line)")
    p.add_argument("--drop-cols", default=None, help="Comma-separated columns to always exclude")
    p.add_argument("--drop-unknown", action="store_true", help="Drop windows with state_unknown==1 from PCA fit")

    p.add_argument("--n-components", type=int, default=8)
    p.add_argument("--whiten", action="store_true")
    p.add_argument("--no-standardize", action="store_true")
    p.add_argument("--fill-value", type=float, default=0.0, help="Fill NaN with this value before scaling/PCA")
    p.add_argument("--clip-abs", type=float, default=None, help="Clip features to [-clip_abs, clip_abs] before fill")

    p.add_argument(
        "--controls-weight",
        type=float,
        default=1.0,
        help="Weight for control-ish features in standardized space. 0=no controls, 1=full, <1 down-weight, >1 emphasize.",
    )
    p.add_argument(
        "--control-regex",
        action="append",
        default=[],
        help="Regex defining control-ish features (repeatable). If none provided, defaults to duties/transitions/state/warn/alarm.",
    )
    p.add_argument(
        "--controls-off",
        action="store_true",
        help="Shortcut for --controls-weight 0.0 (no control influence).",
    )

    p.add_argument("--print-loadings", action="store_true", help="Print PCA loadings per PC")
    p.add_argument("--top-loadings", type=int, default=25, help="Top-K (by abs weight) loadings to print per PC")
    p.add_argument("--print-full-loadings", action="store_true", help="Print all feature loadings per PC (can be huge)")

    p.add_argument("--plot-2d", action="store_true", help="Show live PC1 vs PC2 matplotlib plot")
    p.add_argument("--plot-2d-webgl", action="store_true", help="Show PC1 vs PC2 plotly WebGL plot")
    p.add_argument("--plot-2d-path", action="store_true", help="Draw faint trajectory line in 2D matplotlib plot")
    p.add_argument("--plot-2d-path-alpha", type=float, default=0.12, help="Alpha for 2D trajectory line")
    p.add_argument("--plot-2d-path-width", type=float, default=1.0, help="Line width for 2D trajectory line")
    p.add_argument("--plot-2d-symlog", action="store_true", help="Use symlog scale on y-axis for 2D plot")
    p.add_argument("--plot-2d-symlog-linthresh", type=float, default=1.0, help="Symlog linthresh for y-axis")
    p.add_argument("--plot-color-col", default=None, help="Column to color points by (optional)")
    p.add_argument("--plot-max-points", type=int, default=200_000, help="Max points to plot (subsample)")
    p.add_argument("--plot-alpha", type=float, default=0.25)
    p.add_argument("--plot-point-size", type=float, default=4.0)
    p.add_argument("--plot-3d", action="store_true", help="Show interactive 3D PCA plot (Plotly)")
    p.add_argument("--plot-3d-color-col", default=None, help="Column to color 3D points by (optional)")
    p.add_argument("--plot-3d-color-discrete", action="store_true", help="Treat 3D color column as discrete categories")
    p.add_argument("--plot-3d-max-points", type=int, default=200_000, help="Max points in 3D plot (subsample)")
    p.add_argument("--plot-3d-point-size", type=float, default=3.0)
    p.add_argument("--plot-3d-hover-col", default="window_start_ts", help="Hover column in 3D plot (optional)")
    p.add_argument("--plot-3d-path", action="store_true", help="Draw a faint time-ordered path through points")
    p.add_argument("--plot-3d-path-time-col", default="window_start_ts", help="Time column for path ordering")
    p.add_argument("--plot-3d-path-opacity", type=float, default=0.25, help="Opacity for path line")
    p.add_argument("--plot-3d-path-width", type=float, default=2.0, help="Line width for path")


    p.add_argument("--out-dir", default="./pca_out")
    p.add_argument("--out-prefix", default="pca")
    p.add_argument("--model-only", action="store_true", help="Only fit model; do not project")

    p.add_argument("--out-s3-bucket", default=None)
    p.add_argument("--out-s3-prefix", default=None)

    p.add_argument("--animate", action="store_true", help="Animate a point trajectory through PCA space")
    p.add_argument("--time-col", default=None, help="Time column for ordering trajectory (e.g. window_start_ts)")
    p.add_argument("--trail-len", type=int, default=60, help="Trail length (points) for trajectory animation")
    p.add_argument("--interval-ms", type=int, default=60, help="Frame interval in ms for animation")
    p.add_argument("--sample-every", type=int, default=1, help="Use every Nth point in trajectory")
    p.add_argument("--no-background", action="store_true", help="Disable background scatter")

    return p


def main() -> None:
    args = build_argparser().parse_args()

    if args.controls_off:
        args.controls_weight = 0.0

    explicit_cols = None
    if args.pca_cols:
        explicit_cols = [c.strip() for c in args.pca_cols.split(",") if c.strip()]

    always_exclude: List[str] = []
    if args.drop_cols:
        always_exclude = [c.strip() for c in args.drop_cols.split(",") if c.strip()]

    df_all, load_meta = load_many(
        input_file=args.input_file,
        input_list=args.input_list,
        local_root=args.local_root,
        s3_bucket=args.s3_bucket,
        s3_prefix=args.s3_prefix,
        site=args.site,
        day=args.day,
        date_from=args.date_from,
        date_to=args.date_to,
        window_s=args.window_s,
        stride_s=args.stride_s,
        s3_key_template=args.s3_key_template,
        verbose=False,
    )

    cols = select_pca_columns(
        df_all,
        explicit_cols=explicit_cols,
        include_regex=args.include_regex,
        exclude_regex=args.exclude_regex,
        include_cols_file=args.include_cols_file,
        exclude_cols_file=args.exclude_cols_file,
        always_exclude=always_exclude,
    )

    if not cols:
        raise SystemExit("No PCA columns selected. Provide --pca-cols or broaden --include-regex.")

    df_fit = df_all
    if args.drop_unknown and "state_unknown" in df_fit.columns:
        df_fit = df_fit[pd.to_numeric(df_fit["state_unknown"], errors="coerce").fillna(0).astype(int) == 0].copy()

    if len(df_fit) < 2:
        raise SystemExit("Not enough rows to fit PCA after filtering.")

    control_regex = args.control_regex if args.control_regex else None

    if "n_rows" in df_fit.columns:
        df_fit = df_fit[pd.to_numeric(df_fit["n_rows"], errors="coerce").fillna(0).astype(int) > 0].copy()

    bundle = fit_pca(
        df_fit,
        cols,
        n_components=int(args.n_components),
        whiten=bool(args.whiten),
        standardize=not bool(args.no_standardize),
        fill_value=float(args.fill_value),
        clip_abs=args.clip_abs,
        controls_weight=float(args.controls_weight),
        control_regex=control_regex,
    )

    if args.print_loadings:
        print_pca_loadings(
            bundle,
            top_k=int(args.top_loadings),
            abs_sort=True,
            print_full=bool(args.print_full_loadings),
        )

    if args.model_only and not args.plot_2d and not args.plot_3d:
        return

    df_proj, _Z = transform_pca(
        df_all,
        bundle,
        fill_value=float(args.fill_value),
        clip_abs=args.clip_abs,
    )

    x_plot = "pca1"
    y_plot = "pca2"
    plot_label = "PCA"

    if args.plot_2d:
        plot_pca_2d_live(
            df_proj,
            x_col=x_plot,
            y_col=y_plot,
            color_col=args.plot_color_col,
            max_points=int(args.plot_max_points),
            alpha=float(args.plot_alpha),
            point_size=float(args.plot_point_size),
            title=f"{args.site or ''} {plot_label} ({x_plot} vs {y_plot})  controls_weight={float(args.controls_weight):.2f}".strip(),
            animate=bool(args.animate),
            time_col=args.time_col,
            trail_len=int(args.trail_len),
            interval_ms=int(args.interval_ms),
            sample_every=int(args.sample_every),
            show_background=not bool(args.no_background),
            path=bool(args.plot_2d_path),
            path_alpha=float(args.plot_2d_path_alpha),
            path_width=float(args.plot_2d_path_width),
            symlog_y=bool(args.plot_2d_symlog),
            symlog_linthresh=float(args.plot_2d_symlog_linthresh),
        )
    if args.plot_2d_webgl:
        plot_pca_2d_webgl(
            df_proj,
            x_col=x_plot,
            y_col=y_plot,
            color_col=args.plot_color_col,
            max_points=int(args.plot_max_points),
            point_size=float(args.plot_point_size),
            title=f"{args.site or ''} {plot_label} ({x_plot} vs {y_plot})  controls_weight={float(args.controls_weight):.2f}".strip(),
        )
    if args.plot_3d:
        plot_pca_3d(
            df_proj,
            x_col="pca1",
            y_col="pca2",
            z_col="pca3",
            color_col=args.plot_3d_color_col or args.plot_color_col,
            max_points=int(args.plot_3d_max_points),
            point_size=float(args.plot_3d_point_size),
            title=f"{args.site or ''} PCA (PC1 vs PC2 vs PC3)  controls_weight={float(args.controls_weight):.2f}".strip(),
            hover_col=args.plot_3d_hover_col,
            color_discrete=bool(args.plot_3d_color_discrete),
            path=bool(args.plot_3d_path),
            path_time_col=args.plot_3d_path_time_col,
            path_opacity=float(args.plot_3d_path_opacity),
            path_width=float(args.plot_3d_path_width),
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / f"{args.out_prefix}_model.joblib"
    meta_path = out_dir / f"{args.out_prefix}_metadata.json"

    joblib.dump(
        {
            "cols": bundle.cols,
            "scaler": bundle.scaler,
            "pca": bundle.pca,
            "control_mask": bundle.control_mask,
            "controls_weight": bundle.controls_weight,
            "controls_regex": bundle.controls_regex,
            "feature_ranges": bundle.feature_ranges,
        },
        model_path,
    )

    explained = bundle.pca.explained_variance_ratio_.astype("float64").tolist()
    meta = {
        "created_utc": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
        "n_rows_loaded": int(len(df_all)),
        "n_rows_fit": int(len(df_fit)),
        "n_cols_selected": int(len(cols)),
        "cols_selected": cols,
        "n_components": int(args.n_components),
        "whiten": bool(args.whiten),
        "standardize": not bool(args.no_standardize),
        "fill_value": float(args.fill_value),
        "clip_abs": args.clip_abs,
        "controls_weight": bundle.controls_weight,
        "controls_regex": bundle.controls_regex,
        "n_control_features": int(bundle.control_mask.sum()),
        "explained_variance_ratio": explained,
        "explained_variance_ratio_sum": float(np.sum(bundle.pca.explained_variance_ratio_)),
        "pca_singular_values": bundle.pca.singular_values_.astype("float64").tolist(),
        "feature_ranges": bundle.feature_ranges,
        "load_meta": load_meta,
    }
    write_json_local(meta, meta_path)

    if args.out_s3_bucket and args.out_s3_prefix:
        b = args.out_s3_bucket
        pref = args.out_s3_prefix.rstrip("/")
        write_s3_bytes(b, f"{pref}/{model_path.name}", model_path.read_bytes(), "application/octet-stream")
        write_s3_bytes(b, f"{pref}/{meta_path.name}", meta_path.read_bytes(), "application/json")
        print(f"[OK] uploaded outputs to s3://{b}/{pref}/")


if __name__ == "__main__":
    main()
