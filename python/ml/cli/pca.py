from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ..analysis.pca import pca_from_mel_df, pca_from_tabular_df


def main() -> int:
    p = argparse.ArgumentParser(description="Run PCA on mel manifests or tabular parquet")
    p.add_argument("--mode", choices=["mel", "tabular"], default="mel")
    p.add_argument("--manifest", help="Mel manifest parquet (mode=mel)")
    p.add_argument("--parquet", nargs="*", help="Tabular parquet paths (mode=tabular)")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--sample", choices=["head", "random"], default="head")
    p.add_argument("--n-components", type=int, default=2)
    p.add_argument("--no-standardize", action="store_true")
    p.add_argument("--feature-cols", nargs="*", help="Columns to use (mode=tabular)")
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    standardize = not bool(args.no_standardize)

    if args.mode == "mel":
        if not args.manifest:
            raise SystemExit("--manifest is required for mode=mel")
        df = pd.read_parquet(args.manifest)
        res = pca_from_mel_df(
            df,
            out_dir,
            limit=int(args.limit),
            sample_mode=str(args.sample),
            n_components=int(args.n_components),
            standardize=standardize,
            meta={"manifest": str(args.manifest)},
        )
    else:
        if not args.parquet:
            raise SystemExit("--parquet is required for mode=tabular")
        dfs = [pd.read_parquet(p) for p in args.parquet]
        df = pd.concat(dfs, axis=0, ignore_index=True)
        res = pca_from_tabular_df(
            df,
            out_dir,
            feature_cols=args.feature_cols,
            limit=int(args.limit),
            sample_mode=str(args.sample),
            n_components=int(args.n_components),
            standardize=standardize,
            meta={"parquet_paths": [str(p) for p in args.parquet]},
        )

    print(f"PCA points -> {res.points_path}")
    print(f"PCA model  -> {res.model_path}")
    print(f"PCA meta   -> {res.meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
