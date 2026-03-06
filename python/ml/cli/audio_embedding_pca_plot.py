from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ..train.audio_pca_svm import _attach_split_labels, _normalize_split_value


def _downsample_indices(n: int, limit: int, random_state: int) -> np.ndarray:
    idx = np.arange(n, dtype=np.int64)
    if limit <= 0 or n <= limit:
        return idx
    rng = np.random.default_rng(int(random_state))
    return np.sort(rng.choice(idx, size=int(limit), replace=False))


def main() -> int:
    p = argparse.ArgumentParser(description="PCA scatter from pretrained audio embeddings")
    p.add_argument("--dataset", nargs="+", required=True, help="Dataset parquet path(s)")
    p.add_argument("--split-manifest", default="", help="Optional split manifest parquet")
    p.add_argument("--split-col", default="split")
    p.add_argument("--dataset-id-col", default="sample_id")
    p.add_argument("--split-id-col", default="sample_id")
    p.add_argument("--embeddings-npz", required=True, help="Path to embeddings_panns.npz")
    p.add_argument("--embeddings-key", default="embeddings")
    p.add_argument("--out-png", required=True)
    p.add_argument("--out-parquet", default="", help="Optional parquet with pca1/pca2 + metadata")
    p.add_argument("--out-meta", default="", help="Optional metadata json")
    p.add_argument("--color-col", default="primary_class", help="Column used to color points")
    p.add_argument("--split", default="", help="Optional split filter: train/test/val")
    p.add_argument("--source", default="", help="Optional exact source filter")
    p.add_argument("--limit", type=int, default=12000)
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--title", default="Embedding PCA")
    p.add_argument("--alpha", type=float, default=0.65)
    p.add_argument("--point-size", type=float, default=8.0)
    args = p.parse_args()

    try:
        from sklearn.decomposition import PCA  # type: ignore
    except Exception as e:
        raise SystemExit("Missing scikit-learn. Install: pip install scikit-learn") from e

    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as e:
        raise SystemExit("Missing matplotlib. Install: pip install matplotlib") from e

    dfs = [pd.read_parquet(pth) for pth in args.dataset]
    df = pd.concat(dfs, axis=0, ignore_index=True, sort=False)
    split_manifest_df = pd.read_parquet(args.split_manifest) if str(args.split_manifest).strip() else None

    # Match the same row filtering used in training harness (train/test/val only).
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
    df4["pca1"] = P[:, 0]
    df4["pca2"] = P[:, 1]

    ccol = str(args.color_col)
    if ccol not in df4.columns:
        raise SystemExit(f"color column not found: {ccol}")

    fig, ax = plt.subplots(figsize=(10.5, 8.0), dpi=140)

    cser = df4[ccol]
    numeric = pd.api.types.is_numeric_dtype(cser)
    if numeric:
        vals = pd.to_numeric(cser, errors="coerce").to_numpy(dtype=np.float64)
        finite = np.isfinite(vals)
        if not np.any(finite):
            vals = np.zeros_like(vals)
        sc = ax.scatter(
            df4["pca1"],
            df4["pca2"],
            c=vals,
            s=float(args.point_size),
            alpha=float(args.alpha),
            cmap="viridis",
            linewidths=0.0,
        )
        cb = fig.colorbar(sc, ax=ax)
        cb.set_label(ccol)
    else:
        cats = cser.astype("string").fillna("<NA>").astype(str)
        top = cats.value_counts().head(24).index.tolist()
        cats2 = cats.where(cats.isin(top), other="<OTHER>")
        uniq = sorted(cats2.unique().tolist())
        cmap = plt.get_cmap("tab20", len(uniq) if len(uniq) > 0 else 1)
        for i, u in enumerate(uniq):
            m = (cats2.to_numpy() == u)
            ax.scatter(
                df4.loc[m, "pca1"],
                df4.loc[m, "pca2"],
                s=float(args.point_size),
                alpha=float(args.alpha),
                color=cmap(i),
                label=str(u),
                linewidths=0.0,
            )
        ax.legend(loc="best", fontsize=8, framealpha=0.9, ncol=2)

    title_extra = []
    if split_f:
        title_extra.append(f"split={split_f}")
    if source_f:
        title_extra.append(f"source={source_f}")
    suffix = (" | " + ", ".join(title_extra)) if title_extra else ""
    ax.set_title(f"{args.title} | color={ccol}{suffix}")
    ax.set_xlabel("PCA 1")
    ax.set_ylabel("PCA 2")
    ax.grid(alpha=0.2)

    out_png = Path(args.out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)

    out_parquet = Path(args.out_parquet) if str(args.out_parquet).strip() else None
    if out_parquet is not None:
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
            "rows_plotted": int(len(df4)),
            "color_col": str(ccol),
            "split_filter": split_f or None,
            "source_filter": source_f or None,
            "pca_explained_variance_ratio": [float(x) for x in pca.explained_variance_ratio_.tolist()],
            "out_png": str(out_png),
            "out_parquet": str(out_parquet) if out_parquet is not None else None,
        }
        out_meta.parent.mkdir(parents=True, exist_ok=True)
        out_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Plot -> {out_png}")
    if out_parquet is not None:
        print(f"Points -> {out_parquet}")
    if out_meta is not None:
        print(f"Meta -> {out_meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
