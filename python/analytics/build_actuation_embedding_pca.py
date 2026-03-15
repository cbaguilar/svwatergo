#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd


def _ensure_repo_on_syspath() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


_ensure_repo_on_syspath()

from python.ml.train.audio_pca_svm import _attach_split_labels, _normalize_split_value


def _downsample_indices(n: int, limit: int, random_state: int) -> np.ndarray:
    idx = np.arange(n, dtype=np.int64)
    if limit <= 0 or n <= limit:
        return idx
    rng = np.random.default_rng(int(random_state))
    return np.sort(rng.choice(idx, size=int(limit), replace=False))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build 2D/3D PCA projection parquet from embedding npz + dataset parquet")
    p.add_argument("--dataset", nargs="+", required=True, help="Dataset parquet path(s)")
    p.add_argument("--split-manifest", default="", help="Optional split manifest parquet")
    p.add_argument("--split-col", default="split")
    p.add_argument("--dataset-id-col", default="sample_id")
    p.add_argument("--split-id-col", default="sample_id")
    p.add_argument("--embeddings-npz", required=True, help="Path to embeddings npz")
    p.add_argument("--embeddings-key", default="embeddings")
    p.add_argument("--split", default="", help="Optional split filter")
    p.add_argument("--source", default="", help="Optional exact source filter")
    p.add_argument("--limit", type=int, default=12000)
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--n-components", type=int, default=3)
    p.add_argument("--standardize", default="yes", choices=["yes", "no"])
    p.add_argument("--out-parquet", required=True)
    p.add_argument("--out-meta", default="")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        from sklearn.decomposition import PCA  # type: ignore
        from sklearn.preprocessing import StandardScaler  # type: ignore
    except Exception as e:
        raise SystemExit("Missing scikit-learn. Install: pip install scikit-learn") from e

    dfs = [pd.read_parquet(pth) for pth in args.dataset]
    df = pd.concat(dfs, axis=0, ignore_index=True, sort=False)
    split_manifest_df = pd.read_parquet(args.split_manifest) if str(args.split_manifest).strip() else None

    df2, split_ser, split_source = _attach_split_labels(
        df,
        split_manifest_df=split_manifest_df,
        split_col=str(args.split_col),
        dataset_id_col=str(args.dataset_id_col),
        split_manifest_id_col=str(args.split_id_col),
    )
    if split_ser is not None:
        split_norm = split_ser.map(_normalize_split_value).astype("string")
        keep_mask = split_norm.isin(["train", "test", "val"])
        df2 = df2.loc[keep_mask].reset_index(drop=True)
        split_norm = split_norm.loc[keep_mask].reset_index(drop=True)
        df2["split"] = split_norm.astype(str)
    else:
        df2["split"] = "unknown"

    z = np.load(str(Path(args.embeddings_npz)))
    if str(args.embeddings_key) not in z.files:
        raise SystemExit(f"Embeddings key {args.embeddings_key!r} not found. Available: {list(z.files)}")
    emb = np.asarray(z[str(args.embeddings_key)], dtype=np.float32)
    if emb.ndim != 2:
        emb = emb.reshape(emb.shape[0], -1)

    if len(df2) != emb.shape[0]:
        raise SystemExit(
            f"Row mismatch: filtered dataset rows={len(df2)} embeddings rows={emb.shape[0]}. "
            "Use the same dataset+split manifest used when embeddings were generated."
        )

    mask = np.ones(len(df2), dtype=bool)
    split_f = str(args.split).strip().lower()
    if split_f:
        mask &= (df2["split"].astype(str).str.lower().to_numpy() == split_f)
    source_f = str(args.source).strip()
    if source_f:
        src_col = next((c for c in ("audio_source", "source_name", "source") if c in df2.columns), None)
        if src_col is None:
            raise SystemExit("--source provided but dataset has no source column")
        mask &= (df2[src_col].astype(str).to_numpy() == source_f)
    if int(mask.sum()) <= 0:
        raise SystemExit("No rows left after filters")

    df3 = df2.loc[mask].reset_index(drop=True)
    X = np.asarray(emb[mask], dtype=np.float32)
    keep_idx = _downsample_indices(len(df3), int(args.limit), int(args.random_state))
    df4 = df3.iloc[keep_idx].reset_index(drop=True)
    X4 = np.asarray(X[keep_idx], dtype=np.float32)

    if str(args.standardize) == "yes":
        scaler = StandardScaler(with_mean=True, with_std=True)
        X4 = scaler.fit_transform(X4)

    n_components = max(2, int(args.n_components))
    pca = PCA(n_components=n_components, random_state=int(args.random_state))
    P = pca.fit_transform(X4)

    for j in range(P.shape[1]):
        df4[f"pca{j+1}"] = P[:, j]

    out_parquet = Path(args.out_parquet)
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    df4.to_parquet(out_parquet, index=False)

    out_meta = Path(args.out_meta) if str(args.out_meta).strip() else None
    if out_meta is not None:
        meta: Dict[str, Any] = {
            "dataset_paths": [str(p) for p in args.dataset],
            "split_manifest": str(args.split_manifest) if str(args.split_manifest).strip() else None,
            "split_source": str(split_source),
            "embeddings_npz": str(args.embeddings_npz),
            "embeddings_key": str(args.embeddings_key),
            "rows_filtered": int(len(df3)),
            "rows_projected": int(len(df4)),
            "split_filter": split_f or None,
            "source_filter": source_f or None,
            "n_components": int(P.shape[1]),
            "pca_explained_variance_ratio": [float(x) for x in pca.explained_variance_ratio_.tolist()],
            "out_parquet": str(out_parquet),
        }
        out_meta.parent.mkdir(parents=True, exist_ok=True)
        out_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Points -> {out_parquet}")
    if out_meta is not None:
        print(f"Meta -> {out_meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
