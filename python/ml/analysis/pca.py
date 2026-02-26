from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class PCAResult:
    points_path: Path
    model_path: Path
    meta_path: Path


def _sample_rows(df: pd.DataFrame, limit: int, mode: str) -> pd.DataFrame:
    if limit <= 0 or limit >= len(df):
        return df
    if mode == "random":
        return df.sample(n=limit, random_state=42)
    return df.head(limit)


def _load_mels_from_manifest_rows(df: pd.DataFrame) -> np.ndarray:
    if "mel_shard_path" not in df.columns or "mel_shard_local_index" not in df.columns:
        raise ValueError("Manifest missing mel_shard_path or mel_shard_local_index")
    grouped = df.groupby("mel_shard_path", sort=False)
    chunks = []
    for shard_path, g in grouped:
        z = np.load(shard_path)
        mel = z["mel"]
        idx = g["mel_shard_local_index"].astype(int).to_numpy()
        chunks.append(mel[idx])
    X = np.concatenate(chunks, axis=0)
    if X.ndim != 3:
        raise ValueError(f"Expected 3D mel tensor, got {X.shape}")
    return X


def pca_from_mel_df(
    df: pd.DataFrame,
    out_dir: Path,
    *,
    limit: int = 1000,
    sample_mode: str = "head",
    n_components: int = 2,
    standardize: bool = True,
    meta: dict | None = None,
) -> PCAResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    if "mel_saved" in df.columns:
        df = df[df["mel_saved"] != False].copy()
    df = _sample_rows(df, limit, sample_mode)
    X = _load_mels_from_manifest_rows(df)
    X = X.reshape(X.shape[0], -1)

    scaler = None
    if standardize:
        scaler = StandardScaler(with_mean=True, with_std=True)
        X = scaler.fit_transform(X)

    pca = PCA(n_components=n_components, random_state=42)
    pts = pca.fit_transform(X)

    points_df = df.reset_index(drop=True).copy()
    points_df["pc1"] = pts[:, 0]
    points_df["pc2"] = pts[:, 1] if pts.shape[1] > 1 else 0.0

    points_path = out_dir / "pca_points.parquet"
    points_df.to_parquet(points_path, index=False)

    model_path = out_dir / "pca_model.npz"
    np.savez_compressed(
        model_path,
        components=pca.components_,
        mean=pca.mean_,
        explained_variance=pca.explained_variance_,
        explained_variance_ratio=pca.explained_variance_ratio_,
        n_components=pca.n_components_,
    )

    meta_path = out_dir / "pca_meta.json"
    meta_out = {
        "rows": int(len(df)),
        "limit": int(limit),
        "sample_mode": str(sample_mode),
        "n_components": int(n_components),
        "standardize": bool(standardize),
    }
    if meta:
        meta_out.update(meta)
    meta_path.write_text(json.dumps(meta_out, indent=2), encoding="utf-8")

    return PCAResult(points_path=points_path, model_path=model_path, meta_path=meta_path)


def pca_from_tabular_df(
    df: pd.DataFrame,
    out_dir: Path,
    *,
    feature_cols: List[str] | None = None,
    limit: int = 0,
    sample_mode: str = "head",
    n_components: int = 2,
    standardize: bool = True,
    meta: dict | None = None,
) -> PCAResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    if feature_cols is None:
        feature_cols = [c for c in df.columns if np.issubdtype(df[c].dtype, np.number)]
    feat = df[feature_cols].copy()
    if limit > 0:
        df = _sample_rows(df, limit, sample_mode)
        feat = df[feature_cols].copy()

    feat = feat.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    X = feat.to_numpy(dtype="float32", copy=False)

    if standardize:
        scaler = StandardScaler(with_mean=True, with_std=True)
        X = scaler.fit_transform(X)

    pca = PCA(n_components=n_components, random_state=42)
    pts = pca.fit_transform(X)

    points_df = df.reset_index(drop=True).copy()
    points_df["pc1"] = pts[:, 0]
    points_df["pc2"] = pts[:, 1] if pts.shape[1] > 1 else 0.0

    points_path = out_dir / "pca_points.parquet"
    points_df.to_parquet(points_path, index=False)

    model_path = out_dir / "pca_model.npz"
    np.savez_compressed(
        model_path,
        components=pca.components_,
        mean=pca.mean_,
        explained_variance=pca.explained_variance_,
        explained_variance_ratio=pca.explained_variance_ratio_,
        n_components=pca.n_components_,
        feature_cols=np.array(feature_cols),
    )

    meta_path = out_dir / "pca_meta.json"
    meta_out = {
        "rows": int(len(df)),
        "limit": int(limit),
        "sample_mode": str(sample_mode),
        "n_components": int(n_components),
        "standardize": bool(standardize),
        "feature_cols": feature_cols,
    }
    if meta:
        meta_out.update(meta)
    meta_path.write_text(json.dumps(meta_out, indent=2), encoding="utf-8")

    return PCAResult(points_path=points_path, model_path=model_path, meta_path=meta_path)
