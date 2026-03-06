from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from ..train.audio_pca_svm import _attach_split_labels, _normalize_split_value
from ..train.audio_pca_svm_plot import _render_feature_atlas, _select_feature_atlas_columns


def _downsample_indices(n: int, limit: int, random_state: int) -> np.ndarray:
    idx = np.arange(n, dtype=np.int64)
    if limit <= 0 or n <= limit:
        return idx
    rng = np.random.default_rng(int(random_state))
    return np.sort(rng.choice(idx, size=int(limit), replace=False))


def main() -> int:
    p = argparse.ArgumentParser(description="Render big feature atlas from PCA of pretrained embeddings")
    p.add_argument("--dataset", nargs="+", required=True, help="Dataset parquet path(s)")
    p.add_argument("--split-manifest", default="", help="Optional split manifest parquet")
    p.add_argument("--split-col", default="split")
    p.add_argument("--dataset-id-col", default="sample_id")
    p.add_argument("--split-id-col", default="sample_id")
    p.add_argument("--embeddings-npz", required=True)
    p.add_argument("--embeddings-key", default="embeddings")
    p.add_argument("--out-png", required=True)
    p.add_argument("--out-meta", default="")
    p.add_argument("--split", default="", help="Optional split filter: train/test/val")
    p.add_argument("--source", default="", help="Optional source filter")
    p.add_argument("--limit", type=int, default=30000)
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--max-cols", type=int, default=96, help="Max atlas feature columns")
    p.add_argument(
        "--feature-regex",
        action="append",
        default=[],
        help=(
            "Regex for feature selection (repeatable). If omitted, defaults include "
            "primary_class, duty, mean/avg, derivative/delta/diff, and sensor-like terms"
        ),
    )
    p.add_argument("--title", default="PANN Embedding PCA Feature Atlas")
    args = p.parse_args()

    try:
        from sklearn.decomposition import PCA  # type: ignore
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
    X = emb[mask]

    keep_idx = _downsample_indices(len(df3), int(args.limit), int(args.random_state))
    df4 = df3.iloc[keep_idx].reset_index(drop=True)
    X4 = np.asarray(X[keep_idx], dtype=np.float32)

    pca = PCA(n_components=2, random_state=int(args.random_state))
    P = pca.fit_transform(X4)
    plot_df = df4.copy()
    plot_df["pca1"] = P[:, 0]
    plot_df["pca2"] = P[:, 1]

    default_regex = [
        r"primary_class",
        r"duty",
        r"mean|avg|average",
        r"deriv|derivative|delta|diff|gradient|slope",
        r"flow|press|pressure|conduct|temp|temperature|state|pump",
    ]
    feat_regex = list(args.feature_regex or default_regex)
    feat_cols = _select_feature_atlas_columns(
        plot_df,
        include_regex=feat_regex,
        max_cols=int(args.max_cols),
    )
    if not feat_cols:
        raise SystemExit("No feature columns matched atlas selection regex")

    out_png = Path(args.out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    atlas = _render_feature_atlas(
        plot_df=plot_df,
        xcol="pca1",
        ycol="pca2",
        xname="PC1",
        yname="PC2",
        feature_cols=feat_cols,
        out_png=out_png,
        title=str(args.title),
    )

    out_meta = Path(args.out_meta) if str(args.out_meta).strip() else out_png.with_suffix(".json")
    meta: Dict[str, Any] = {
        "dataset_paths": [str(p) for p in args.dataset],
        "split_manifest": str(args.split_manifest) if str(args.split_manifest).strip() else None,
        "split_source": str(split_source),
        "embeddings_npz": str(args.embeddings_npz),
        "embeddings_key": str(args.embeddings_key),
        "rows_filtered": int(len(df3)),
        "rows_plotted": int(len(plot_df)),
        "split_filter": split_f or None,
        "source_filter": source_f or None,
        "pca_explained_variance_ratio": [float(x) for x in pca.explained_variance_ratio_.tolist()],
        "feature_regex": feat_regex,
        "feature_count": int(len(feat_cols)),
        "selected_feature_cols": feat_cols,
        "plot_path": str(out_png),
        "atlas": atlas,
    }
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Atlas -> {out_png}")
    print(f"Meta  -> {out_meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
