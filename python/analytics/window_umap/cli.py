from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

try:
    import joblib  # type: ignore
except Exception as e:
    raise SystemExit("Missing joblib. Install: pip install joblib") from e

try:
    import umap  # type: ignore
except Exception as e:
    raise SystemExit("Missing umap-learn. Install: pip install umap-learn") from e

from python.analytics.site_alias import alias_site_names
from window_pca.loader import load_many
from window_pca.model import apply_controls_weight, extract_matrix

from .plotting import plot_umap_2d_webgl


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compute UMAP embeddings from PCA model + window_features parquet(s)."
    )

    p.add_argument("--pca-model", required=True, help="Path to PCA model joblib produced by pca_from_window_features.py")

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

    p.add_argument("--umap-pca-dims", type=int, default=3, help="Number of PCA dimensions to feed into UMAP")
    p.add_argument("--umap-n-neighbors", type=int, default=15, help="UMAP n_neighbors")
    p.add_argument("--umap-min-dist", type=float, default=0.1, help="UMAP min_dist")
    p.add_argument("--umap-metric", default="euclidean", help="UMAP distance metric")
    p.add_argument("--umap-n-jobs", type=int, default=1, help="UMAP n_jobs (parallelism)")
    p.add_argument("--umap-no-seed", action="store_true", help="Disable random_state to allow parallelism")
    p.add_argument("--umap-max-fit-points", type=int, default=0, help="Fit UMAP on a subsample, then transform all points")

    p.add_argument("--plot-2d-webgl", action="store_true", help="Show UMAP plot in Plotly WebGL")
    p.add_argument("--plot-color-col", default=None, help="Column to color points by (optional)")
    p.add_argument("--plot-max-points", type=int, default=200_000, help="Max points to plot (subsample)")
    p.add_argument("--plot-point-size", type=float, default=3.0)

    p.add_argument("--out-dir", default="./umap_out")
    p.add_argument("--out-prefix", default="umap")
    p.add_argument("--write-parquet", action="store_true", help="Write parquet with UMAP columns")

    return p


def _load_pca_model(path: str) -> dict:
    obj = joblib.load(path)
    if not isinstance(obj, dict):
        raise SystemExit("--pca-model must be a joblib dict produced by pca_from_window_features.py")
    missing = [k for k in ("cols", "scaler", "pca", "control_mask", "controls_weight", "controls_regex") if k not in obj]
    if missing:
        raise SystemExit(f"--pca-model missing keys: {missing}")
    return obj


def main() -> None:
    args = build_argparser().parse_args()

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

    model = _load_pca_model(args.pca_model)

    class Bundle:
        cols = model["cols"]
        scaler = model["scaler"]
        pca = model["pca"]
        control_mask = model["control_mask"]
        controls_weight = model["controls_weight"]
        controls_regex = model["controls_regex"]

    missing = [c for c in Bundle.cols if c not in df_all.columns]
    if missing:
        for c in missing:
            df_all[c] = np.nan

    X = extract_matrix(df_all, Bundle.cols)
    Xs = Bundle.scaler.transform(X)
    Xw = apply_controls_weight(Xs, Bundle.control_mask, Bundle.controls_weight)
    Z = Bundle.pca.transform(Xw)

    n_umap_dims = int(args.umap_pca_dims)
    if n_umap_dims <= 0:
        raise SystemExit("--umap-pca-dims must be > 0")
    if Z.shape[1] < n_umap_dims:
        raise SystemExit(f"UMAP requires >= {n_umap_dims} PCA dims, got {Z.shape[1]}")

    random_state = None if args.umap_no_seed else 0
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=int(args.umap_n_neighbors),
        min_dist=float(args.umap_min_dist),
        metric=str(args.umap_metric),
        random_state=random_state,
        n_jobs=int(args.umap_n_jobs),
    )
    Z_use = Z[:, :n_umap_dims]
    max_fit = int(args.umap_max_fit_points)
    if max_fit > 0 and len(Z_use) > max_fit:
        rng = np.random.default_rng(0)
        fit_idx = rng.choice(len(Z_use), size=max_fit, replace=False)
        reducer.fit(Z_use[fit_idx])
        emb = reducer.transform(Z_use)
    else:
        emb = reducer.fit_transform(Z_use)

    umap1 = emb[:, 0].astype("float64")
    umap2 = emb[:, 1].astype("float64")

    if args.plot_2d_webgl:
        plot_df = pd.DataFrame({"umap1": umap1, "umap2": umap2})
        if args.plot_color_col and (args.plot_color_col in df_all.columns):
            plot_df[args.plot_color_col] = df_all[args.plot_color_col].to_numpy()
        plot_umap_2d_webgl(
            plot_df,
            x_col="umap1",
            y_col="umap2",
            color_col=args.plot_color_col,
            max_points=int(args.plot_max_points),
            point_size=float(args.plot_point_size),
            title=alias_site_names(f"{args.site or ''} UMAP (umap1 vs umap2)".strip()),
        )

    if args.write_parquet:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{args.out_prefix}.parquet"
        df_all = df_all.copy()
        df_all["umap1"] = umap1
        df_all["umap2"] = umap2
        df_all.to_parquet(out_path, index=False)

        meta = {
            "created_utc": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
            "n_rows_loaded": int(len(df_all)),
            "n_rows_out": int(len(df_all)),
            "umap_pca_dims": int(args.umap_pca_dims),
            "umap_n_neighbors": int(args.umap_n_neighbors),
            "umap_min_dist": float(args.umap_min_dist),
            "umap_metric": str(args.umap_metric),
            "load_meta": load_meta,
            "pca_model_path": args.pca_model,
        }
        meta_path = out_dir / f"{args.out_prefix}_metadata.json"
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[OK] wrote {out_path}")
        print(f"[OK] wrote {meta_path}")


if __name__ == "__main__":
    main()
