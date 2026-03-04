#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    import joblib  # type: ignore
except Exception as e:
    raise SystemExit("Missing joblib. Install with: pip install joblib") from e

try:
    import matplotlib.pyplot as plt
except Exception as e:
    raise SystemExit("Missing matplotlib. Install with: pip install matplotlib") from e

try:
    from sklearn.cross_decomposition import CCA
    from sklearn.decomposition import PCA
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
except Exception as e:
    raise SystemExit("Missing scikit-learn. Install with: pip install scikit-learn") from e


NON_SENSOR_COLS = {
    "mel_shard_path",
    "mel_shard_local_index",
    "audio_source",
    "audio_day",
    "segment_path",
    "segment_relpath",
    "segment_start_ts_utc",
    "segment_end_ts_utc",
    "source_path",
    "source_name",
    "source_clip_start_ts_utc",
    "source_clip_end_ts_utc",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Run CCA between audio mel embeddings and aligned PLC window features "
            "from bluerock_audio_dataset partitions."
        )
    )
    p.add_argument(
        "--root",
        default="/mnt/d/datasets/svwatergo/derived/dataset=bluerock_audio_dataset/window_s=10/site=bluerock",
        help="Root containing audio_source=*/date=*/audio_dataset.parquet",
    )
    p.add_argument(
        "--out-dir",
        default="/mnt/d/datasets/svwatergo/derived/cca_bluerock_audio_sensor",
        help="Output directory",
    )
    p.add_argument("--limit", type=int, default=25000, help="Max rows to sample (0 means all)")
    p.add_argument("--sample", choices=["random", "head"], default="random")
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--test-size", type=float, default=0.2)
    p.add_argument("--audio-pca-components", type=int, default=64)
    p.add_argument("--sensor-pca-components", type=int, default=32)
    p.add_argument("--cca-components", type=int, default=8)
    p.add_argument(
        "--no-audio-pca",
        action="store_true",
        help="Use standardized raw mel vectors directly for CCA (no PCA reduction)",
    )
    p.add_argument(
        "--no-sensor-pca",
        action="store_true",
        help="Use standardized raw sensor vectors directly for CCA (no PCA reduction)",
    )
    p.add_argument(
        "--sensor-col-regex",
        default="",
        help="Optional regex to keep only matching numeric sensor columns",
    )
    p.add_argument(
        "--drop-col-regex",
        default="",
        help="Optional regex to drop matching numeric sensor columns",
    )
    p.add_argument(
        "--target-col",
        default="ropumprun__duty",
        help="Optional context column to carry into scores output if present",
    )
    p.add_argument(
        "--topk-sensors",
        type=int,
        default=25,
        help="Print/save top-K sensors ranked by CCA loading magnitude",
    )
    return p.parse_args()


def _find_dataset_paths(root: Path) -> List[Path]:
    return sorted(root.glob("audio_source=*/date=*/audio_dataset.parquet"))


def _sample_rows(df: pd.DataFrame, limit: int, mode: str, random_state: int) -> pd.DataFrame:
    if limit <= 0 or limit >= len(df):
        return df
    if mode == "random":
        return df.sample(n=limit, random_state=int(random_state))
    return df.head(limit)


def _load_mels_from_rows(df: pd.DataFrame) -> np.ndarray:
    grouped = df.groupby("mel_shard_path", sort=False)
    chunks: List[np.ndarray] = []
    positions: List[np.ndarray] = []
    for shard_path, g in grouped:
        z = np.load(str(shard_path))
        key = "mel" if "mel" in z.files else z.files[0]
        mel = z[key]
        idx = g["mel_shard_local_index"].astype(int).to_numpy()
        chunks.append(mel[idx])
        positions.append(g.index.to_numpy())

    if not chunks:
        raise ValueError("No mel shards loaded from selected rows.")

    n = len(df)
    mel_shape = chunks[0].shape[1:]
    X = np.empty((n, mel_shape[0], mel_shape[1]), dtype=np.float32)
    for part, pos in zip(chunks, positions):
        X[pos, :, :] = part
    return X


def _select_sensor_cols(
    df: pd.DataFrame,
    include_regex: str,
    drop_regex: str,
) -> List[str]:
    cols = []
    inc_re = re.compile(include_regex) if include_regex else None
    drop_re = re.compile(drop_regex) if drop_regex else None
    for c in df.columns:
        if c in NON_SENSOR_COLS:
            continue
        if c.startswith("pc"):
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            continue
        if inc_re and not inc_re.search(c):
            continue
        if drop_re and drop_re.search(c):
            continue
        cols.append(c)
    return cols


def _canonical_corrs(U: np.ndarray, V: np.ndarray) -> List[float]:
    out: List[float] = []
    k = min(U.shape[1], V.shape[1])
    for i in range(k):
        u = U[:, i]
        v = V[:, i]
        m = np.isfinite(u) & np.isfinite(v)
        if int(m.sum()) < 3:
            out.append(float("nan"))
            continue
        c = np.corrcoef(u[m], v[m])[0, 1]
        out.append(float(c))
    return out


def _plot_correlations(train_corr: Sequence[float], test_corr: Sequence[float], out_path: Path) -> None:
    x = np.arange(1, len(train_corr) + 1)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(x, train_corr, marker="o", label="train")
    ax.plot(x, test_corr, marker="o", label="test")
    ax.set_xlabel("Canonical Component")
    ax.set_ylabel("Correlation")
    ax.set_title("Canonical Correlations by Component")
    ax.set_ylim(-0.05, 1.0)
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def _plot_top_pair(U: np.ndarray, V: np.ndarray, split: str, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(U[:, 0], V[:, 0], s=5, alpha=0.35)
    ax.set_xlabel("Audio Canonical 1")
    ax.set_ylabel("Sensor Canonical 1")
    ax.set_title(f"Top Canonical Pair ({split})")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def _sensor_loading_matrix(sensor_pca, cca) -> np.ndarray:
    """
    Return sensor->canonical loading matrix.
    Rows: sensors, Cols: canonical components.
    """
    y_w = np.asarray(cca.y_weights_, dtype=np.float64)
    if sensor_pca is None:
        return y_w
    return np.asarray(sensor_pca.components_.T, dtype=np.float64) @ y_w


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = _find_dataset_paths(root)
    if not paths:
        raise SystemExit(f"No audio_dataset.parquet found under {root}")

    dfs = [pd.read_parquet(p) for p in paths]
    df = pd.concat(dfs, ignore_index=True, sort=False)
    if "mel_shard_path" not in df.columns or "mel_shard_local_index" not in df.columns:
        raise SystemExit("Required columns missing: mel_shard_path / mel_shard_local_index")

    df = df.dropna(subset=["mel_shard_path", "mel_shard_local_index"]).copy()
    df["mel_shard_local_index"] = pd.to_numeric(df["mel_shard_local_index"], errors="coerce")
    df = df[df["mel_shard_local_index"].notna()].copy()
    df["mel_shard_local_index"] = df["mel_shard_local_index"].astype(int)
    df = df.reset_index(drop=True)
    df = _sample_rows(df, int(args.limit), str(args.sample), int(args.random_state)).reset_index(drop=True)

    sensor_cols = _select_sensor_cols(df, include_regex=str(args.sensor_col_regex), drop_regex=str(args.drop_col_regex))
    if not sensor_cols:
        raise SystemExit("No numeric sensor columns selected for CCA.")

    X_mel = _load_mels_from_rows(df)
    X_audio = X_mel.reshape(X_mel.shape[0], -1).astype(np.float32, copy=False)
    X_sensor = df[sensor_cols].copy()
    X_sensor = X_sensor.replace([np.inf, -np.inf], np.nan)
    X_sensor = X_sensor.fillna(X_sensor.median(numeric_only=True)).fillna(0.0)
    X_sensor_np = X_sensor.to_numpy(dtype=np.float32, copy=False)

    idx = np.arange(len(df), dtype=np.int64)
    idx_train, idx_test = train_test_split(
        idx,
        test_size=float(args.test_size),
        random_state=int(args.random_state),
        shuffle=True,
    )

    X_audio_train = X_audio[idx_train]
    X_audio_test = X_audio[idx_test]
    X_sensor_train = X_sensor_np[idx_train]
    X_sensor_test = X_sensor_np[idx_test]

    audio_scaler = StandardScaler(with_mean=True, with_std=True)
    sensor_scaler = StandardScaler(with_mean=True, with_std=True)
    X_audio_train_s = audio_scaler.fit_transform(X_audio_train)
    X_audio_test_s = audio_scaler.transform(X_audio_test)
    X_sensor_train_s = sensor_scaler.fit_transform(X_sensor_train)
    X_sensor_test_s = sensor_scaler.transform(X_sensor_test)

    audio_pca = None
    sensor_pca = None

    if args.no_audio_pca:
        A_train = X_audio_train_s
        A_test = X_audio_test_s
    else:
        a_dim = min(int(args.audio_pca_components), X_audio_train_s.shape[0], X_audio_train_s.shape[1])
        if a_dim < 2:
            raise SystemExit("Not enough dimensions for audio PCA reduction.")
        audio_pca = PCA(n_components=a_dim, random_state=int(args.random_state))
        A_train = audio_pca.fit_transform(X_audio_train_s)
        A_test = audio_pca.transform(X_audio_test_s)

    if args.no_sensor_pca:
        S_train = X_sensor_train_s
        S_test = X_sensor_test_s
    else:
        s_dim = min(int(args.sensor_pca_components), X_sensor_train_s.shape[0], X_sensor_train_s.shape[1])
        if s_dim < 2:
            raise SystemExit("Not enough dimensions for sensor PCA reduction.")
        sensor_pca = PCA(n_components=s_dim, random_state=int(args.random_state))
        S_train = sensor_pca.fit_transform(X_sensor_train_s)
        S_test = sensor_pca.transform(X_sensor_test_s)

    cca_k = min(int(args.cca_components), A_train.shape[1], S_train.shape[1])
    if cca_k < 1:
        raise SystemExit("Invalid --cca-components after dimensionality checks.")
    cca = CCA(n_components=cca_k, max_iter=1000)
    U_train, V_train = cca.fit_transform(A_train, S_train)
    U_test, V_test = cca.transform(A_test, S_test)

    train_corr = _canonical_corrs(U_train, V_train)
    test_corr = _canonical_corrs(U_test, V_test)

    scores = pd.DataFrame(index=np.arange(len(df), dtype=np.int64))
    scores["split"] = "train"
    scores.loc[idx_test, "split"] = "test"
    if "audio_source" in df.columns:
        scores["audio_source"] = df["audio_source"].astype(str)
    if "audio_day" in df.columns:
        scores["audio_day"] = df["audio_day"].astype(str)
    if args.target_col in df.columns:
        scores[args.target_col] = pd.to_numeric(df[args.target_col], errors="coerce")
    for i in range(cca_k):
        col_u = f"cca_audio_{i+1}"
        col_v = f"cca_sensor_{i+1}"
        scores[col_u] = np.nan
        scores[col_v] = np.nan
        scores.loc[idx_train, col_u] = U_train[:, i]
        scores.loc[idx_train, col_v] = V_train[:, i]
        scores.loc[idx_test, col_u] = U_test[:, i]
        scores.loc[idx_test, col_v] = V_test[:, i]

    scores_path = out_dir / "cca_scores.parquet"
    scores.to_parquet(scores_path, index=False)

    model_bundle = {
        "audio_scaler": audio_scaler,
        "sensor_scaler": sensor_scaler,
        "audio_pca": audio_pca,
        "sensor_pca": sensor_pca,
        "cca": cca,
        "sensor_cols": sensor_cols,
        "config": {
            "audio_pca_components": int(args.audio_pca_components),
            "sensor_pca_components": int(args.sensor_pca_components),
            "cca_components": int(args.cca_components),
            "test_size": float(args.test_size),
            "random_state": int(args.random_state),
            "no_audio_pca": bool(args.no_audio_pca),
            "no_sensor_pca": bool(args.no_sensor_pca),
        },
    }
    model_path = out_dir / "cca_model.joblib"
    joblib.dump(model_bundle, model_path)

    corr_plot = out_dir / "cca_canonical_correlations.png"
    _plot_correlations(train_corr, test_corr, corr_plot)
    pair_train_plot = out_dir / "cca_pair1_train.png"
    pair_test_plot = out_dir / "cca_pair1_test.png"
    _plot_top_pair(U_train, V_train, "train", pair_train_plot)
    _plot_top_pair(U_test, V_test, "test", pair_test_plot)

    sensor_pc_corr = np.corrcoef(V_train.T, rowvar=True)
    sensor_pc_corr_df = pd.DataFrame(
        sensor_pc_corr,
        index=[f"cca_sensor_{i+1}" for i in range(cca_k)],
        columns=[f"cca_sensor_{i+1}" for i in range(cca_k)],
    )
    sensor_pc_corr_path = out_dir / "cca_sensor_component_corr.parquet"
    sensor_pc_corr_df.to_parquet(sensor_pc_corr_path)

    # Sensor ranking from canonical loadings.
    # For PCA->CCA, this maps raw standardized sensor space into canonical space.
    W = _sensor_loading_matrix(sensor_pca, cca)  # [n_sensors, n_cca]
    sensor_weight_df = pd.DataFrame({"sensor": sensor_cols})
    for i in range(W.shape[1]):
        sensor_weight_df[f"weight_c{i+1}"] = W[:, i]
        sensor_weight_df[f"abs_weight_c{i+1}"] = np.abs(W[:, i])

    test_corr_abs = np.asarray([abs(float(x)) if np.isfinite(x) else 0.0 for x in test_corr], dtype=np.float64)
    if test_corr_abs.sum() <= 0:
        test_corr_abs = np.ones_like(test_corr_abs)
    test_corr_abs = test_corr_abs / test_corr_abs.sum()
    sensor_weight_df["overall_score"] = np.abs(W) @ test_corr_abs
    sensor_weight_df = sensor_weight_df.sort_values("overall_score", ascending=False).reset_index(drop=True)

    sensor_weights_path = out_dir / "cca_sensor_weights.parquet"
    sensor_weight_df.to_parquet(sensor_weights_path, index=False)
    sensor_weights_csv = out_dir / "cca_sensor_weights.csv"
    sensor_weight_df.to_csv(sensor_weights_csv, index=False)

    topk = max(1, int(args.topk_sensors))
    topk_df = sensor_weight_df.head(topk).copy()
    topk_path = out_dir / f"cca_sensor_topk_{topk}.csv"
    topk_df.to_csv(topk_path, index=False)

    meta = {
        "n_rows": int(len(df)),
        "n_train": int(len(idx_train)),
        "n_test": int(len(idx_test)),
        "n_sensor_cols": int(len(sensor_cols)),
        "audio_view_dim": int(A_train.shape[1]),
        "sensor_view_dim": int(S_train.shape[1]),
        "sensor_cols": sensor_cols,
        "train_canonical_corr": train_corr,
        "test_canonical_corr": test_corr,
        "paths": {
            "model": str(model_path),
            "scores": str(scores_path),
            "corr_plot": str(corr_plot),
            "pair_train_plot": str(pair_train_plot),
            "pair_test_plot": str(pair_test_plot),
            "sensor_component_corr": str(sensor_pc_corr_path),
            "sensor_weights": str(sensor_weights_path),
            "sensor_weights_csv": str(sensor_weights_csv),
            "sensor_topk_csv": str(topk_path),
        },
    }
    meta_path = out_dir / "cca_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Model      -> {model_path}")
    print(f"Scores     -> {scores_path}")
    print(f"Meta       -> {meta_path}")
    print(f"Corr Plot  -> {corr_plot}")
    print(f"Pair Train -> {pair_train_plot}")
    print(f"Pair Test  -> {pair_test_plot}")
    print(f"Weights    -> {sensor_weights_path}")
    print(f"TopK CSV   -> {topk_path}")
    print(f"Train Corr -> {train_corr}")
    print(f"Test Corr  -> {test_corr}")
    print("\nTop sensors by overall CCA score:")
    print(topk_df[["sensor", "overall_score"]].to_string(index=False))


if __name__ == "__main__":
    main()
