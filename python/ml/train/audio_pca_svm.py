from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..features.audio_mel import (
    ensure_mono,
    fix_length,
    make_mel_filterbank,
    read_wav_with_meta,
    resample_if_needed,
    waveform_to_logmel,
)

try:
    import joblib  # type: ignore
except Exception as e:
    raise SystemExit("Missing joblib. Install: pip install joblib") from e

try:
    from sklearn.decomposition import PCA
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC
except Exception as e:
    raise SystemExit("Missing scikit-learn. Install: pip install scikit-learn") from e


@dataclass(frozen=True)
class AudioPCASVMResult:
    model_path: Path
    metrics_path: Path
    projection_path: Path


def _sample_rows(df: pd.DataFrame, limit: int, mode: str) -> pd.DataFrame:
    if limit <= 0 or limit >= len(df):
        return df
    if mode == "random":
        return df.sample(n=limit, random_state=42)
    return df.head(limit)


def _load_mels_from_manifest_rows(df: pd.DataFrame) -> np.ndarray:
    grouped = df.groupby("mel_shard_path", sort=False)
    chunks: List[np.ndarray] = []
    for shard_path, g in grouped:
        z = np.load(str(shard_path))
        key = "mel" if "mel" in z.files else z.files[0]
        mel = z[key]
        idx = g["mel_shard_local_index"].astype(int).to_numpy()
        chunks.append(mel[idx])
    if not chunks:
        raise ValueError("No mel chunks loaded from dataset rows.")
    X = np.concatenate(chunks, axis=0)
    if X.ndim != 3:
        raise ValueError(f"Expected 3D mel tensor, got {X.shape}")
    return X


def _coerce_target(
    df: pd.DataFrame,
    *,
    target_col: str,
    task: str,
    positive_label: str,
) -> Tuple[pd.DataFrame, np.ndarray, Dict[str, Any]]:
    out = df.copy()
    if target_col not in out.columns:
        raise ValueError(f"Target column not found: {target_col}")

    y_meta: Dict[str, Any] = {"target_col": target_col, "task": task}
    if task == "binary":
        ser = out[target_col]
        if pd.api.types.is_numeric_dtype(ser):
            y = pd.to_numeric(ser, errors="coerce")
            mask = y.notna()
            out = out[mask].reset_index(drop=True)
            y = (y[mask].astype(int) > 0).astype("int64").to_numpy()
            y_meta["positive_rule"] = f"{target_col} > 0"
        else:
            s = ser.astype(str)
            mask = ser.notna()
            out = out[mask].reset_index(drop=True)
            y = (s[mask].str.lower() == str(positive_label).lower()).astype("int64").to_numpy()
            y_meta["positive_label"] = positive_label
        return out, y, y_meta

    s = out[target_col].astype("string")
    mask = s.notna()
    out = out[mask].reset_index(drop=True)
    s = s[mask].astype(str)
    classes = sorted(s.unique().tolist())
    class_to_idx = {c: i for i, c in enumerate(classes)}
    y = np.asarray([class_to_idx[v] for v in s.tolist()], dtype=np.int64)
    y_meta["classes"] = classes
    return out, y, y_meta


def _normalize_split_value(v: Any) -> str:
    s = str(v).strip().lower()
    if s in {"train", "training"}:
        return "train"
    if s in {"test", "testing"}:
        return "test"
    if s in {"val", "valid", "validation", "eval"}:
        return "val"
    return s


def _normalize_primary_class_alias(v: str) -> str:
    return str(v).strip()


def _build_stratify_labels(
    *,
    df: pd.DataFrame,
    y: np.ndarray,
    split_stratify_col: str,
) -> Optional[np.ndarray]:
    col = str(split_stratify_col or "").strip()
    if col and col in df.columns:
        s = df[col].astype("string")
        if int(s.notna().sum()) == len(df):
            vals = s.astype(str).to_numpy()
            counts = pd.Series(vals).value_counts(dropna=False)
            if len(counts) > 1 and int(counts.min()) >= 2:
                return vals
    y_vals = np.asarray(y)
    counts = pd.Series(y_vals).value_counts(dropna=False)
    if len(counts) > 1 and int(counts.min()) >= 2:
        return y_vals
    return None


def _oversample_train_indices(
    *,
    df: pd.DataFrame,
    idx_train: np.ndarray,
    oversample_class_col: str,
    oversample_classes: Optional[Sequence[str]],
    oversample_multiplier: int,
    random_state: int,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    out: Dict[str, Any] = {
        "enabled": False,
        "class_col": str(oversample_class_col),
        "classes": [],
        "multiplier": int(oversample_multiplier),
        "n_train_base": int(len(idx_train)),
        "n_train_fit": int(len(idx_train)),
        "n_added": 0,
    }
    if int(oversample_multiplier) <= 1 or not oversample_classes:
        return idx_train, out

    col = str(oversample_class_col).strip()
    if not col:
        raise ValueError("oversample_class_col cannot be empty when oversampling is enabled")
    if col not in df.columns:
        raise ValueError(f"Oversample class column not found: {col}")

    classes_norm = [_normalize_primary_class_alias(c) for c in oversample_classes if str(c).strip()]
    if not classes_norm:
        return idx_train, out

    s = df[col].astype("string").fillna("").astype(str)
    train_class = s.iloc[idx_train].reset_index(drop=True)
    add_idx: List[int] = []
    for klass in classes_norm:
        m = (train_class == str(klass)).to_numpy()
        hit_idx = idx_train[m]
        if len(hit_idx):
            add_idx.extend(hit_idx.tolist() * (int(oversample_multiplier) - 1))

    if not add_idx:
        out["enabled"] = True
        out["classes"] = classes_norm
        return idx_train, out

    fit_idx = np.concatenate([idx_train, np.asarray(add_idx, dtype=np.int64)], axis=0)
    rng = np.random.default_rng(int(random_state))
    rng.shuffle(fit_idx)
    out["enabled"] = True
    out["classes"] = classes_norm
    out["n_train_fit"] = int(len(fit_idx))
    out["n_added"] = int(len(fit_idx) - len(idx_train))
    return fit_idx, out


def _attach_split_labels(
    df: pd.DataFrame,
    *,
    split_manifest_df: Optional[pd.DataFrame],
    split_col: str,
    dataset_id_col: str,
    split_manifest_id_col: str,
) -> Tuple[pd.DataFrame, Optional[pd.Series], str]:
    out = df.copy()

    if split_manifest_df is not None:
        sm = split_manifest_df.copy()
        if split_col not in sm.columns:
            raise ValueError(f"Split manifest missing split column: {split_col}")

        if dataset_id_col in out.columns and split_manifest_id_col in sm.columns:
            keep = sm[[split_manifest_id_col, split_col]].drop_duplicates(subset=[split_manifest_id_col], keep="last")
            out = out.merge(
                keep.rename(columns={split_manifest_id_col: dataset_id_col, split_col: "__split"}),
                on=dataset_id_col,
                how="left",
            )
            return out, out["__split"], "manifest"

        fallback_keys = ["segment_path", "segment_start_ts_utc", "segment_end_ts_utc"]
        if all(c in out.columns for c in fallback_keys) and all(c in sm.columns for c in fallback_keys):
            keep = sm[fallback_keys + [split_col]].drop_duplicates(subset=fallback_keys, keep="last")
            out = out.merge(
                keep.rename(columns={split_col: "__split"}),
                on=fallback_keys,
                how="left",
            )
            return out, out["__split"], "manifest_fallback_segment_keys"

        raise ValueError(
            "Could not join split manifest. Need either matching ID columns "
            f"({dataset_id_col}, {split_manifest_id_col}) or fallback keys {fallback_keys}."
        )

    if split_col in out.columns:
        return out, out[split_col], "dataset"
    return out, None, "random"


def _infer_mel_shape(df: pd.DataFrame, X_mel: np.ndarray) -> Tuple[int, int]:
    if "mel_n_mels" in df.columns and "mel_n_frames" in df.columns:
        m = pd.to_numeric(df["mel_n_mels"], errors="coerce").dropna()
        f = pd.to_numeric(df["mel_n_frames"], errors="coerce").dropna()
        if len(m) and len(f):
            return int(m.iloc[0]), int(f.iloc[0])
    return int(X_mel.shape[1]), int(X_mel.shape[2])


def _metrics_dict(y_true: np.ndarray, y_pred: np.ndarray, y_score: Optional[np.ndarray], *, task: str) -> Dict[str, Any]:
    out = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1": float(f1_score(y_true, y_pred, average="binary" if task == "binary" else "macro", zero_division=0)),
        "precision": float(
            precision_score(y_true, y_pred, average="binary" if task == "binary" else "macro", zero_division=0)
        ),
        "recall": float(recall_score(y_true, y_pred, average="binary" if task == "binary" else "macro", zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
    }
    if task == "binary" and y_score is not None:
        try:
            out["roc_auc"] = float(roc_auc_score(y_true, y_score))
        except Exception:
            pass
    return out


def fit_audio_pca_svm(
    df: pd.DataFrame,
    out_dir: Path,
    *,
    target_col: str = "ropumprun_label",
    task: str = "binary",
    positive_label: str = "on",
    limit: int = 0,
    sample_mode: str = "random",
    n_components: int = 8,
    standardize: bool = True,
    test_size: float = 0.2,
    random_state: int = 42,
    svm_kernel: str = "rbf",
    svm_c: float = 1.0,
    svm_gamma: str = "scale",
    svm_class_weight: Optional[str] = None,
    mel_config: Optional[Dict[str, Any]] = None,
    split_manifest_df: Optional[pd.DataFrame] = None,
    split_col: str = "split",
    dataset_id_col: str = "sample_id",
    split_manifest_id_col: str = "sample_id",
    split_stratify_col: str = "",
    oversample_class_col: str = "primary_class",
    oversample_classes: Optional[Sequence[str]] = None,
    oversample_multiplier: int = 1,
) -> AudioPCASVMResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = _sample_rows(df, limit, sample_mode)
    df, y, y_meta = _coerce_target(df, target_col=target_col, task=task, positive_label=positive_label)
    df, split_ser, split_source = _attach_split_labels(
        df,
        split_manifest_df=split_manifest_df,
        split_col=str(split_col),
        dataset_id_col=str(dataset_id_col),
        split_manifest_id_col=str(split_manifest_id_col),
    )
    if len(df) < 4:
        raise ValueError("Not enough labeled rows to train.")

    X_mel = _load_mels_from_manifest_rows(df)
    mel_n_mels, mel_n_frames = _infer_mel_shape(df, X_mel)
    X = X_mel.reshape(X_mel.shape[0], -1).astype("float32", copy=False)

    idx = np.arange(len(df), dtype=np.int64)
    idx_train: np.ndarray
    idx_test: np.ndarray
    idx_val: np.ndarray = np.asarray([], dtype=np.int64)
    split_for_projection = pd.Series(["train"] * len(df), index=df.index, dtype="string")

    if split_ser is not None:
        norm = split_ser.map(_normalize_split_value).astype("string")
        keep_mask = norm.isin(["train", "test", "val"])
        if int(keep_mask.sum()) <= 0:
            raise ValueError("No rows mapped to train/test/val from split source.")
        df = df.loc[keep_mask].reset_index(drop=True)
        y = y[np.asarray(keep_mask.to_numpy(), dtype=bool)]
        X = X[np.asarray(keep_mask.to_numpy(), dtype=bool)]
        norm = norm.loc[keep_mask].reset_index(drop=True)
        split_for_projection = norm.astype("string")
        idx_all = np.arange(len(df), dtype=np.int64)
        idx_train = idx_all[norm.to_numpy() == "train"]
        idx_test = idx_all[norm.to_numpy() == "test"]
        idx_val = idx_all[norm.to_numpy() == "val"]
        if len(idx_train) < 2:
            raise ValueError("Need at least 2 train rows from provided splits.")
    else:
        stratify = _build_stratify_labels(
            df=df,
            y=y,
            split_stratify_col=str(split_stratify_col),
        )
        idx_train, idx_test = train_test_split(
            idx,
            test_size=float(test_size),
            random_state=int(random_state),
            stratify=stratify,
        )
        split_for_projection = pd.Series(["train"] * len(df), index=df.index, dtype="string")
        split_for_projection.iloc[idx_test] = "test"

    if len(np.unique(y[idx_train])) < 2:
        raise ValueError("Train split has only one class after filtering; cannot train SVM classifier.")

    idx_train_fit, oversample_meta = _oversample_train_indices(
        df=df,
        idx_train=idx_train,
        oversample_class_col=str(oversample_class_col),
        oversample_classes=list(oversample_classes) if oversample_classes else None,
        oversample_multiplier=int(oversample_multiplier),
        random_state=int(random_state),
    )

    scaler = None
    X_train_fit = X[idx_train_fit]
    if standardize:
        scaler = StandardScaler(with_mean=True, with_std=True)
        X_train_fit = scaler.fit_transform(X_train_fit)
    X_train_fit_in = X_train_fit
    X_all_in = scaler.transform(X) if scaler is not None else X

    pca = PCA(n_components=int(n_components), random_state=int(random_state))
    Z_train_fit = pca.fit_transform(X_train_fit_in)
    Z_all = pca.transform(X_all_in)
    Z_train = Z_all[idx_train]
    Z_test = Z_all[idx_test] if len(idx_test) else np.zeros((0, Z_all.shape[1]), dtype=np.float64)
    Z_val = Z_all[idx_val] if len(idx_val) else np.zeros((0, Z_all.shape[1]), dtype=np.float64)

    svm = SVC(
        kernel=str(svm_kernel),
        C=float(svm_c),
        gamma=str(svm_gamma),
        class_weight=(str(svm_class_weight) if svm_class_weight else None),
        probability=True,
        random_state=int(random_state),
    )
    svm.fit(Z_train_fit, y[idx_train_fit])

    y_train_pred = svm.predict(Z_train)
    y_test_pred = svm.predict(Z_test) if len(idx_test) else np.asarray([], dtype=np.int64)
    y_val_pred = svm.predict(Z_val) if len(idx_val) else np.asarray([], dtype=np.int64)
    y_train_score = None
    y_test_score = None
    if task == "binary" and hasattr(svm, "predict_proba"):
        y_train_score = svm.predict_proba(Z_train)[:, 1]
        y_test_score = svm.predict_proba(Z_test)[:, 1] if len(idx_test) else None
        y_val_score = svm.predict_proba(Z_val)[:, 1] if len(idx_val) else None
    else:
        y_val_score = None

    proj_df = df.reset_index(drop=True).copy()
    for i in range(Z_all.shape[1]):
        proj_df[f"pca{i+1}"] = Z_all[:, i].astype("float64")
    proj_df["split"] = split_for_projection.reset_index(drop=True)
    proj_df["y_true"] = y.astype(int)
    proj_df["y_pred"] = svm.predict(Z_all).astype(int)
    if hasattr(svm, "predict_proba"):
        proba_all = svm.predict_proba(Z_all)
        if task == "binary":
            proj_df["score_positive"] = proba_all[:, 1].astype("float64")
        else:
            for j in range(proba_all.shape[1]):
                proj_df[f"score_class_{j}"] = proba_all[:, j].astype("float64")

    projection_path = out_dir / "train_projection.parquet"
    proj_df.to_parquet(projection_path, index=False)

    model_path = out_dir / "audio_pca_svm_model.joblib"
    bundle = {
        "bundle_version": 1,
        "task": task,
        "target_col": target_col,
        "y_meta": y_meta,
        "standardize": bool(standardize),
        "input_scaler": scaler,
        "pca": pca,
        "svm": svm,
        "mel_shape": {"n_mels": int(mel_n_mels), "n_frames": int(mel_n_frames)},
        "mel_config": mel_config or {},
        "feature_dim": int(X.shape[1]),
        "n_rows": int(len(df)),
        "train_idx": idx_train.tolist(),
        "train_fit_idx": idx_train_fit.tolist(),
        "test_idx": idx_test.tolist(),
        "val_idx": idx_val.tolist(),
        "split_source": str(split_source),
        "split_stratify_col": str(split_stratify_col),
        "oversample": oversample_meta,
    }
    joblib.dump(bundle, model_path)

    metrics = {
        "task": task,
        "target_col": target_col,
        "y_meta": y_meta,
        "n_rows": int(len(df)),
        "n_train": int(len(idx_train)),
        "n_train_fit": int(len(idx_train_fit)),
        "n_test": int(len(idx_test)),
        "n_val": int(len(idx_val)),
        "split_source": str(split_source),
        "split_stratify_col": str(split_stratify_col),
        "oversample": oversample_meta,
        "class_counts": {str(int(k)): int(v) for k, v in pd.Series(y).value_counts().sort_index().items()},
        "pca": {
            "n_components": int(pca.n_components_),
            "explained_variance_ratio": [float(x) for x in pca.explained_variance_ratio_.tolist()],
            "explained_variance_ratio_sum": float(np.sum(pca.explained_variance_ratio_)),
        },
        "svm": {
            "kernel": svm_kernel,
            "C": float(svm_c),
            "gamma": svm_gamma,
            "class_weight": (str(svm_class_weight) if svm_class_weight else None),
        },
        "train_metrics": _metrics_dict(y[idx_train], y_train_pred, y_train_score, task=task),
        "test_metrics": _metrics_dict(y[idx_test], y_test_pred, y_test_score, task=task) if len(idx_test) else {},
        "val_metrics": _metrics_dict(y[idx_val], y_val_pred, y_val_score, task=task) if len(idx_val) else {},
    }
    metrics_path = out_dir / "audio_pca_svm_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return AudioPCASVMResult(model_path=model_path, metrics_path=metrics_path, projection_path=projection_path)


def load_audio_pca_svm_bundle(model_path: Path) -> Dict[str, Any]:
    obj = joblib.load(model_path)
    if not isinstance(obj, dict):
        raise ValueError("Model bundle must be a joblib dict")
    for key in ("pca", "svm", "mel_shape"):
        if key not in obj:
            raise ValueError(f"Model bundle missing key: {key}")
    return obj


def _resize_2d_nearest(x: np.ndarray, shape: Tuple[int, int]) -> np.ndarray:
    h, w = x.shape
    th, tw = shape
    if (h, w) == (th, tw):
        return x.astype("float32", copy=False)
    yi = np.linspace(0, h - 1, th).round().astype(int)
    xi = np.linspace(0, w - 1, tw).round().astype(int)
    return x[np.ix_(yi, xi)].astype("float32", copy=False)


def _load_mel_from_webp(path: Path, *, expected_shape: Tuple[int, int]) -> np.ndarray:
    try:
        from PIL import Image  # type: ignore
    except Exception as e:
        raise RuntimeError("Pillow is required for WEBP inference input (pip install pillow)") from e
    img = Image.open(path).convert("L")
    # image width maps to time frames, height maps to mel bins
    img = img.resize((expected_shape[1], expected_shape[0]))
    arr = np.asarray(img, dtype="float32") / 255.0
    return arr


def _load_mel_from_wav(path: Path, *, mel_cfg: Dict[str, Any], expected_shape: Tuple[int, int]) -> np.ndarray:
    sample_rate = int(mel_cfg.get("sample_rate", 16000))
    mono = bool(mel_cfg.get("mono", True))
    target_seconds = float(mel_cfg.get("target_seconds", 4.0))
    n_fft = int(mel_cfg.get("n_fft", 1024))
    win_length = int(mel_cfg.get("win_length", 1024))
    hop_length = int(mel_cfg.get("hop_length", 256))
    n_mels = int(mel_cfg.get("n_mels", expected_shape[0]))
    fmin = float(mel_cfg.get("fmin", 20.0))
    fmax = float(mel_cfg.get("fmax", sample_rate / 2.0))
    power = float(mel_cfg.get("power", 2.0))
    log_eps = float(mel_cfg.get("log_eps", 1e-10))
    to_db = bool(mel_cfg.get("to_db", False))
    mel_normalization = str(mel_cfg.get("mel_normalization", "legacy"))

    y, sr_in, _ = read_wav_with_meta(path, decoder="soundfile", sample_rate=sample_rate, mono=mono)
    y = ensure_mono(y) if mono else np.asarray(y, dtype="float32")
    y = resample_if_needed(y, int(sr_in), sample_rate)
    y, _ = fix_length(y, target_n=int(round(target_seconds * sample_rate)), pad_short=True, truncate_long=True)
    if y is None:
        raise RuntimeError("Failed to pad/truncate wav to target length")
    mel_filter = make_mel_filterbank(sr=sample_rate, n_fft=n_fft, n_mels=n_mels, fmin=fmin, fmax=fmax)
    mel = waveform_to_logmel(
        y,
        sr=sample_rate,
        n_fft=n_fft,
        win_length=win_length,
        hop_length=hop_length,
        mel_filter=mel_filter,
        power=power,
        log_eps=log_eps,
        to_db=to_db,
        mel_normalization=mel_normalization,
    )
    if mel.shape != expected_shape:
        mel = _resize_2d_nearest(mel, expected_shape)
    return mel.astype("float32", copy=False)


def _load_mel_input(
    *,
    bundle: Dict[str, Any],
    wav_path: Optional[Path] = None,
    webp_path: Optional[Path] = None,
    mel_npy_path: Optional[Path] = None,
    mel_npz_path: Optional[Path] = None,
    mel_npz_key: str = "mel",
    mel_npz_index: int = 0,
) -> np.ndarray:
    expected_shape = (int(bundle["mel_shape"]["n_mels"]), int(bundle["mel_shape"]["n_frames"]))
    provided = [wav_path is not None, webp_path is not None, mel_npy_path is not None, mel_npz_path is not None]
    if sum(provided) != 1:
        raise ValueError("Provide exactly one of wav_path/webp_path/mel_npy_path/mel_npz_path")

    if wav_path is not None:
        return _load_mel_from_wav(wav_path, mel_cfg=dict(bundle.get("mel_config") or {}), expected_shape=expected_shape)
    if webp_path is not None:
        return _load_mel_from_webp(webp_path, expected_shape=expected_shape)
    if mel_npy_path is not None:
        arr = np.load(str(mel_npy_path))
    else:
        z = np.load(str(mel_npz_path))
        key = mel_npz_key if mel_npz_key in z.files else z.files[0]
        arr = z[key]
        if arr.ndim == 3:
            arr = arr[int(mel_npz_index)]
    arr = np.asarray(arr, dtype="float32")
    if arr.ndim != 2:
        raise ValueError(f"Mel input must be 2D after selection, got {arr.shape}")
    if arr.shape == (expected_shape[1], expected_shape[0]):
        arr = arr.T
    if arr.shape != expected_shape:
        arr = _resize_2d_nearest(arr, expected_shape)
    return arr.astype("float32", copy=False)


def predict_audio_pca_svm(
    model_path: Path,
    *,
    wav_path: Optional[Path] = None,
    webp_path: Optional[Path] = None,
    mel_npy_path: Optional[Path] = None,
    mel_npz_path: Optional[Path] = None,
    mel_npz_key: str = "mel",
    mel_npz_index: int = 0,
) -> Dict[str, Any]:
    bundle = load_audio_pca_svm_bundle(model_path)
    mel = _load_mel_input(
        bundle=bundle,
        wav_path=wav_path,
        webp_path=webp_path,
        mel_npy_path=mel_npy_path,
        mel_npz_path=mel_npz_path,
        mel_npz_key=mel_npz_key,
        mel_npz_index=int(mel_npz_index),
    )
    x = mel.reshape(1, -1).astype("float32", copy=False)
    scaler = bundle.get("input_scaler")
    if scaler is not None:
        x = scaler.transform(x)
    z = bundle["pca"].transform(x)
    svm = bundle["svm"]
    pred = svm.predict(z)
    out: Dict[str, Any] = {
        "task": str(bundle.get("task", "binary")),
        "predicted_index": int(pred[0]),
        "pca_projection": [float(v) for v in z[0].tolist()],
        "mel_shape_used": [int(mel.shape[0]), int(mel.shape[1])],
    }
    if hasattr(svm, "predict_proba"):
        proba = svm.predict_proba(z)[0]
        out["probabilities"] = [float(v) for v in proba.tolist()]
        if str(bundle.get("task")) == "binary":
            out["score_positive"] = float(proba[1])
            y_meta = bundle.get("y_meta") or {}
            if "positive_label" in y_meta:
                out["positive_label"] = y_meta["positive_label"]
    if str(bundle.get("task")) == "multiclass":
        y_meta = bundle.get("y_meta") or {}
        classes = y_meta.get("classes")
        if isinstance(classes, list) and 0 <= int(pred[0]) < len(classes):
            out["predicted_label"] = str(classes[int(pred[0])])
    elif str(bundle.get("task")) == "binary":
        out["predicted_label"] = "positive" if int(pred[0]) == 1 else "negative"
    return out
