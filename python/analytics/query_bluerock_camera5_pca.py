#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_PCA_PARQUET = (
    "/mnt/d/datasets/svwatergo/derived/plots/"
    "bluerock_camera5_actuation_embedding_pca.parquet"
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Query the Bluerock camera 5 actuation PCA parquet for clips nearest a 3D PCA point."
        )
    )
    p.add_argument("--input-parquet", default=DEFAULT_PCA_PARQUET, help="PCA points parquet")
    p.add_argument("--pca1", type=float, required=True, help="Target PCA 1 coordinate")
    p.add_argument("--pca2", type=float, required=True, help="Target PCA 2 coordinate")
    p.add_argument("--pca3", type=float, required=True, help="Target PCA 3 coordinate")
    p.add_argument("--top-k", type=int, default=10, help="Number of nearest rows to print")
    p.add_argument(
        "--cols",
        default="sample_id,segment_path,audio_source,split,actuation_trit,actuation_combo,pca1,pca2,pca3",
        help="Comma-separated output columns",
    )
    p.add_argument(
        "--copy-path-col",
        default="segment_path",
        help="Column whose values should be printed again as a plain list for copy/paste",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    inp = Path(args.input_parquet)
    if not inp.exists():
        raise SystemExit(f"input parquet not found: {inp}")

    df = pd.read_parquet(inp)
    if df.empty:
        raise SystemExit("input parquet is empty")

    required = ("pca1", "pca2", "pca3")
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"missing PCA columns: {', '.join(missing)}")

    df = df.copy()
    df["dist2"] = (
        (pd.to_numeric(df["pca1"], errors="coerce") - float(args.pca1)) ** 2
        + (pd.to_numeric(df["pca2"], errors="coerce") - float(args.pca2)) ** 2
        + (pd.to_numeric(df["pca3"], errors="coerce") - float(args.pca3)) ** 2
    )
    df = df[df["dist2"].notna()].sort_values("dist2").reset_index(drop=True)
    if df.empty:
        raise SystemExit("no finite PCA rows found")

    cols = [c.strip() for c in str(args.cols).split(",") if c.strip()]
    cols = [c for c in cols if c in df.columns]
    if "dist2" not in cols:
        cols.append("dist2")

    top = df.head(max(1, int(args.top_k))).copy()
    print(top[cols].to_string(index=False))

    path_col = str(args.copy_path_col).strip()
    if path_col in top.columns:
        print("\nCopy/paste paths:")
        for path in top[path_col].astype(str).tolist():
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
