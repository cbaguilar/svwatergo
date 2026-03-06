from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .audio_pca_svm import (
    _attach_split_labels,
    _coerce_target,
    _load_mel_from_wav,
    _metrics_dict,
    _normalize_split_value,
    _sample_rows,
)
from .audio_model_minicnn import build_tiny_cnn_model
from .audio_model_resnet import build_small_resnet_model

try:
    from sklearn.decomposition import PCA
    from sklearn.metrics import confusion_matrix
    from sklearn.model_selection import train_test_split
except Exception as e:
    raise SystemExit("Missing scikit-learn. Install: pip install scikit-learn") from e


@dataclass(frozen=True)
class AudioTinyCNNResult:
    model_path: Path
    metrics_path: Path
    projection_path: Path


def _require_torch():
    try:
        import torch  # type: ignore
        import torch.nn as nn  # type: ignore
        from torch.utils.data import DataLoader, TensorDataset  # type: ignore
    except Exception as e:
        msg = str(e)
        if "cannot enable executable stack" in msg and "libtorch_cpu.so" in msg:
            raise RuntimeError(
                "Torch is installed but failed to load native libs: "
                f"{msg}. This is commonly an executable-stack policy issue. "
                "Try clearing execstack on torch libs, e.g. "
                "`execstack -c $CONDA_PREFIX/lib/python*/site-packages/torch/lib/*.so`."
            ) from e
        raise RuntimeError(f"Torch import failed: {msg}") from e
    return torch, nn, DataLoader, TensorDataset


def _seed_torch(torch, seed: int) -> None:
    torch.manual_seed(int(seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(seed))
    try:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    except Exception:
        pass


def _select_device(torch):
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _balanced_loss_kwargs(
    *,
    torch,
    y_train: np.ndarray,
    task: str,
    class_weight: Optional[str],
) -> Dict[str, Any]:
    if class_weight != "balanced":
        return {}
    if task == "binary":
        n_pos = int(np.sum(y_train == 1))
        n_neg = int(np.sum(y_train == 0))
        if n_pos <= 0:
            return {}
        pos_w = float(n_neg / max(1, n_pos))
        return {"pos_weight": torch.tensor(pos_w, dtype=torch.float32)}

    classes, counts = np.unique(y_train, return_counts=True)
    if len(classes) <= 1:
        return {}
    total = float(np.sum(counts))
    n_cls = float(len(classes))
    w = np.zeros(int(np.max(classes)) + 1, dtype=np.float32)
    for c, cnt in zip(classes.tolist(), counts.tolist()):
        if cnt > 0:
            w[int(c)] = total / (n_cls * float(cnt))
    return {"weight": torch.tensor(w, dtype=torch.float32)}


def _move_loss_kwargs_to_device(loss_kwargs: Dict[str, Any], device) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in loss_kwargs.items():
        if hasattr(v, "to"):
            out[k] = v.to(device)
        else:
            out[k] = v
    return out


def _load_mels_from_manifest_rows(df: pd.DataFrame) -> np.ndarray:
    grouped = df.groupby("mel_shard_path", sort=False)
    chunks = []
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


def _cmvn_per_clip_per_freq(X_mel: np.ndarray, *, eps: float = 1e-6) -> np.ndarray:
    """
    CMVN over time per clip/frequency bin.
    Input shape: (N, M, T)
    """
    X = np.asarray(X_mel, dtype=np.float32)
    if X.ndim != 3:
        raise ValueError(f"CMVN expects 3D mel tensor, got {X.shape}")
    mu = X.mean(axis=2, keepdims=True)
    sigma = X.std(axis=2, keepdims=True)
    return ((X - mu) / (sigma + float(eps))).astype("float32", copy=False)


def _global_mel_norm(
    X_mel: np.ndarray,
    *,
    mean: float,
    std: float,
    eps: float = 1e-6,
) -> np.ndarray:
    X = np.asarray(X_mel, dtype=np.float32)
    s = float(std)
    if not np.isfinite(s) or s <= 0.0:
        s = 1.0
    return ((X - float(mean)) / (s + float(eps))).astype("float32", copy=False)


def _build_model(nn, *, out_dim: int, model_arch: str):
    arch = str(model_arch).strip().lower()
    if arch in ("tiny", "tiny_cnn", "tiny_cnn_v1"):
        return build_tiny_cnn_model(nn, out_dim=out_dim), "tiny_cnn_v1"
    if arch in ("resnet", "resnet_small", "resnet_small_v1"):
        return build_small_resnet_model(nn, out_dim=out_dim), "resnet_small_v1"
    raise ValueError(f"Unknown model_arch: {model_arch!r}")


def _forward_logits_and_embedding(model, xb, *, arch_kind: str):
    kind = str(arch_kind)
    if kind == "tiny_cnn_v1":
        emb = model[:-1](xb)
        logits = model[-1](emb)
        return logits, emb
    if kind == "resnet_small_v1":
        x = model.stem(xb)
        x = model._run_block(model.b1, x)
        x = model._run_block(model.b2, x)
        x = model._run_block(model.b3, x)
        emb = model.head[:-1](x)
        logits = model.head[-1](emb)
        return logits, emb
    logits = model(xb)
    return logits, None


def _select_aux_window_feature_columns(
    df: pd.DataFrame,
    *,
    target_col: str,
    target_cols: Optional[List[str]],
    split_col: str,
    dataset_id_col: str,
    split_manifest_id_col: str,
    explicit_cols: Optional[List[str]],
) -> List[str]:
    # Mirror window_pca defaults for monotonic/counter-ish columns and extend
    # with time-like fields that can leak ordering/session position.
    default_exclude_regex = [
        r"^total",
        r"^daily",
        r"^powermeter__(?!d1$)",
        r"__last$",
        r"(^|__)time($|__|_)",
        r"(^|__)timestamp($|__|_)",
        r"(^|__)date($|__|_)",
        r"(^|__)hour($|__|_)",
        r"(^|__)minute($|__|_)",
        r"(^|__)second($|__|_)",
        r"(^|__)elapsed($|__|_)",
        r"(^|__)uptime($|__|_)",
        r"(^|__)age($|__|_)",
        r"(^|__)seq($|__|_)",
        r"(^|__)index($|__|_)",
    ]
    excl_regs = [re.compile(p, flags=re.IGNORECASE) for p in default_exclude_regex]

    if explicit_cols:
        missing = [c for c in explicit_cols if c not in df.columns]
        if missing:
            raise ValueError(f"aux_pca_feature_cols missing columns: {', '.join(missing)}")
        cols = list(explicit_cols)
    else:
        cols = []
        excluded = {
            str(target_col),
            str(split_col),
            str(dataset_id_col),
            str(split_manifest_id_col),
            "mel_shard_local_index",
        }
        excluded.update(str(c) for c in (target_cols or []))
        for c in df.columns:
            cs = str(c)
            if cs in excluded:
                continue
            lc = cs.lower()
            if "label" in lc or lc.endswith("_duty"):
                continue
            if any(r.search(cs) for r in excl_regs):
                continue
            if pd.api.types.is_numeric_dtype(df[c]):
                cols.append(cs)
    if not cols:
        raise ValueError("No numeric window feature columns available for aux PCA target.")
    keep: List[str] = []
    for c in cols:
        s = pd.to_numeric(df[c], errors="coerce")
        if int(s.notna().sum()) <= 0:
            continue
        if float(s.std(skipna=True)) <= 0.0:
            continue
        keep.append(str(c))
    if not keep:
        raise ValueError("All aux PCA feature columns were empty or constant.")
    return keep


def _coerce_multilabel_target(
    df: pd.DataFrame,
    *,
    target_cols: List[str],
    positive_threshold: float,
) -> Tuple[pd.DataFrame, np.ndarray, Dict[str, Any]]:
    out = df.copy()
    if not target_cols:
        raise ValueError("multilabel target_cols cannot be empty")
    missing = [c for c in target_cols if c not in out.columns]
    if missing:
        raise ValueError(f"Missing multilabel target columns: {', '.join(missing)}")
    y_cols: List[np.ndarray] = []
    keep_mask = np.ones(len(out), dtype=bool)
    for c in target_cols:
        s = pd.to_numeric(out[c], errors="coerce")
        keep_mask &= s.notna().to_numpy()
        # Use soft duty targets in [0,1] for multilabel BCE training.
        y_cols.append(np.clip(s.to_numpy(dtype=np.float32), 0.0, 1.0))
    if int(keep_mask.sum()) <= 0:
        raise ValueError("No valid rows for multilabel target after coercion")
    out = out.loc[keep_mask].reset_index(drop=True)
    Y = np.stack([col[keep_mask] for col in y_cols], axis=1).astype(np.float32)
    y_meta: Dict[str, Any] = {
        "task": "multilabel",
        "target_cols": [str(c) for c in target_cols],
        "target_mode": "soft_duty",
        "value_range": [0.0, 1.0],
        "positive_rule_for_metrics": f"value >= {float(positive_threshold)}",
        "classes": [str(c) for c in target_cols],
    }
    return out, Y, y_meta


def _coerce_multiregression_target(
    df: pd.DataFrame,
    *,
    target_cols: List[str],
) -> Tuple[pd.DataFrame, np.ndarray, Dict[str, Any]]:
    out = df.copy()
    if not target_cols:
        raise ValueError("multiregression target_cols cannot be empty")
    missing = [c for c in target_cols if c not in out.columns]
    if missing:
        raise ValueError(f"Missing multiregression target columns: {', '.join(missing)}")
    y_cols: List[np.ndarray] = []
    keep_mask = np.ones(len(out), dtype=bool)
    for c in target_cols:
        s = pd.to_numeric(out[c], errors="coerce")
        keep_mask &= s.notna().to_numpy()
        y_cols.append(np.clip(s.to_numpy(dtype=np.float32), 0.0, 1.0))
    if int(keep_mask.sum()) <= 0:
        raise ValueError("No valid rows for multiregression target after coercion")
    out = out.loc[keep_mask].reset_index(drop=True)
    Y = np.stack([col[keep_mask] for col in y_cols], axis=1).astype(np.float32)
    y_meta: Dict[str, Any] = {
        "task": "multiregression",
        "target_cols": [str(c) for c in target_cols],
        "classes": [str(c) for c in target_cols],
        "value_range": [0.0, 1.0],
    }
    return out, Y, y_meta


def _metrics_multilabel(
    *,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: Optional[np.ndarray],
    class_names: List[str],
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    per_label: Dict[str, Any] = {}
    f1_vals: List[float] = []
    prec_vals: List[float] = []
    rec_vals: List[float] = []
    for j, name in enumerate(class_names):
        yt = y_true[:, j].astype(np.int64)
        yp = y_pred[:, j].astype(np.int64)
        ys = y_score[:, j] if y_score is not None else None
        m = _metrics_dict(yt, yp, ys, task="binary")
        per_label[str(name)] = m
        f1_vals.append(float(m.get("f1", 0.0)))
        prec_vals.append(float(m.get("precision", 0.0)))
        rec_vals.append(float(m.get("recall", 0.0)))
    out["per_label"] = per_label
    out["macro_f1"] = float(np.mean(f1_vals)) if f1_vals else 0.0
    out["macro_precision"] = float(np.mean(prec_vals)) if prec_vals else 0.0
    out["macro_recall"] = float(np.mean(rec_vals)) if rec_vals else 0.0
    out["exact_match_accuracy"] = float(np.mean(np.all(y_true == y_pred, axis=1))) if len(y_true) else 0.0
    return out


def _metrics_multiregression(
    *,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    class_names: List[str],
) -> Dict[str, Any]:
    yt = np.asarray(y_true, dtype=np.float64)
    yp = np.asarray(y_pred, dtype=np.float64)
    out: Dict[str, Any] = {}
    per_target: Dict[str, Any] = {}
    maes: List[float] = []
    rmses: List[float] = []
    for j, name in enumerate(class_names):
        e = yp[:, j] - yt[:, j]
        mae = float(np.mean(np.abs(e))) if len(e) else 0.0
        rmse = float(np.sqrt(np.mean(np.square(e)))) if len(e) else 0.0
        per_target[str(name)] = {"mae": mae, "rmse": rmse}
        maes.append(mae)
        rmses.append(rmse)
    out["per_target"] = per_target
    out["mae_mean"] = float(np.mean(maes)) if maes else 0.0
    out["rmse_mean"] = float(np.mean(rmses)) if rmses else 0.0
    return out


def _apply_binary_threshold(scores: np.ndarray, threshold: float) -> np.ndarray:
    s = np.asarray(scores, dtype=np.float64).reshape(-1)
    return (s >= float(threshold)).astype(np.int64)


def _binary_prf(yt: np.ndarray, yp: np.ndarray) -> Dict[str, float]:
    y_true = np.asarray(yt, dtype=np.int64).reshape(-1)
    y_pred = np.asarray(yp, dtype=np.int64).reshape(-1)
    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    prec = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    rec = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1 = float((2.0 * prec * rec) / (prec + rec)) if (prec + rec) > 0 else 0.0
    return {"precision": prec, "recall": rec, "f1": f1}


def _normalize_primary_class_alias(v: str) -> str:
    return str(v).strip()


def _build_stratify_labels(
    *,
    df: pd.DataFrame,
    y: np.ndarray,
    task: str,
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
    if task in ("multilabel", "multiregression"):
        return None
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


def _tune_binary_threshold(
    y_true: np.ndarray,
    y_score: np.ndarray,
    *,
    default_threshold: float = 0.5,
    n_steps: int = 201,
) -> Dict[str, Any]:
    yt = np.asarray(y_true, dtype=np.int64).reshape(-1)
    ys = np.asarray(y_score, dtype=np.float64).reshape(-1)
    if len(yt) == 0 or len(ys) == 0 or len(yt) != len(ys):
        return {
            "threshold": float(default_threshold),
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "n_rows": int(len(yt)),
            "status": "default_no_data",
        }

    best: Dict[str, Any] = {
        "threshold": float(default_threshold),
        "precision": 0.0,
        "recall": 0.0,
        "f1": -1.0,
    }
    for t in np.linspace(0.0, 1.0, int(max(2, n_steps))):
        yp = _apply_binary_threshold(ys, float(t))
        m = _binary_prf(yt, yp)
        cand = {
            "threshold": float(t),
            "precision": float(m["precision"]),
            "recall": float(m["recall"]),
            "f1": float(m["f1"]),
        }
        # Max F1, then precision, then recall, then threshold (higher = fewer FPs).
        key_cand = (cand["f1"], cand["precision"], cand["recall"], cand["threshold"])
        key_best = (best["f1"], best["precision"], best["recall"], best["threshold"])
        if key_cand > key_best:
            best = cand

    best["n_rows"] = int(len(yt))
    best["status"] = "tuned"
    return best


def _predict_from_scores(
    *,
    task: str,
    y_score: Optional[np.ndarray],
    thresholds: Optional[List[float]] = None,
    default_threshold: float = 0.5,
) -> Optional[np.ndarray]:
    if y_score is None:
        return None
    if task == "binary":
        thr = float(thresholds[0]) if thresholds else float(default_threshold)
        return _apply_binary_threshold(y_score, thr)
    if task == "multilabel":
        ys = np.asarray(y_score, dtype=np.float64)
        if ys.ndim != 2:
            raise ValueError(f"Expected 2D multilabel scores, got {ys.shape}")
        if thresholds and len(thresholds) == ys.shape[1]:
            thr = np.asarray(thresholds, dtype=np.float64).reshape(1, -1)
        else:
            thr = np.full((1, ys.shape[1]), float(default_threshold), dtype=np.float64)
        return (ys >= thr).astype(np.int64)
    return None


def _exact_match_acc(y_true: Optional[np.ndarray], y_pred: Optional[np.ndarray], *, task: str) -> float:
    if y_true is None or y_pred is None:
        return 0.0
    yt = np.asarray(y_true)
    yp = np.asarray(y_pred)
    if yt.shape[0] == 0 or yp.shape[0] == 0:
        return 0.0
    if task == "multilabel":
        return float(np.mean(np.all(yt == yp, axis=1)))
    return float(np.mean(yt == yp))


def _metrics_by_source(
    *,
    task: str,
    y_true_all: np.ndarray,
    y_pred_all: np.ndarray,
    y_score_all: Optional[np.ndarray],
    source_all: pd.Series,
    idx: np.ndarray,
    class_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if idx is None or len(idx) == 0:
        return out
    src_split = source_all.iloc[idx].astype(str).fillna("unknown")
    if src_split.empty:
        return out
    for src in sorted(src_split.unique().tolist()):
        m = src_split.to_numpy() == src
        if not np.any(m):
            continue
        y_true = y_true_all[idx][m]
        y_pred = y_pred_all[idx][m]
        y_score = y_score_all[idx][m] if y_score_all is not None else None
        if task == "multilabel":
            metrics = _metrics_multilabel(
                y_true=np.asarray(y_true, dtype=np.int64),
                y_pred=np.asarray(y_pred, dtype=np.int64),
                y_score=np.asarray(y_score, dtype=np.float64) if y_score is not None else None,
                class_names=list(class_names or []),
            )
        elif task == "multiregression":
            metrics = _metrics_multiregression(
                y_true=np.asarray(y_true, dtype=np.float64),
                y_pred=np.asarray(y_pred, dtype=np.float64),
                class_names=list(class_names or []),
            )
        else:
            metrics = _metrics_dict(
                np.asarray(y_true),
                np.asarray(y_pred),
                np.asarray(y_score) if y_score is not None else None,
                task=task,
            )
        metrics["n_rows"] = int(np.sum(m))
        out[str(src)] = metrics
    return out


def _confusion_counts(cm: np.ndarray) -> Dict[str, int]:
    m = np.asarray(cm, dtype=np.int64)
    total = int(np.sum(m))
    if m.shape == (2, 2):
        tn = int(m[0, 0])
        fp = int(m[0, 1])
        fn = int(m[1, 0])
        tp = int(m[1, 1])
        return {"tn": tn, "fp": fp, "fn": fn, "tp": tp, "total": total}
    return {"total": total}


def _plot_confusion_grid(
    *,
    entries: List[Tuple[str, np.ndarray, int]],
    label_names: List[str],
    title: str,
    out_png: Path,
) -> bool:
    if not entries:
        return False
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:
        return False

    n = len(entries)
    ncols = 3 if n >= 3 else n
    nrows = int(np.ceil(float(n) / float(max(1, ncols))))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.8 * ncols, 4.2 * nrows), dpi=130)
    if not isinstance(axes, np.ndarray):
        axes_arr = np.asarray([axes], dtype=object)
    else:
        axes_arr = axes.reshape(-1)

    vmax = max(float(np.max(cm)) for _, cm, _ in entries) if entries else 1.0
    vmax = max(vmax, 1.0)
    for i, (src, cm, n_rows) in enumerate(entries):
        ax = axes_arr[i]
        mat = np.asarray(cm, dtype=np.int64)
        ax.imshow(mat, cmap="Blues", vmin=0.0, vmax=vmax)
        ax.set_title(f"{src}\nn={n_rows}", fontsize=9)
        ax.set_xlabel("Pred")
        ax.set_ylabel("True")
        ticks = np.arange(len(label_names))
        ax.set_xticks(ticks)
        ax.set_yticks(ticks)
        ax.set_xticklabels(label_names, rotation=45, ha="right", fontsize=8)
        ax.set_yticklabels(label_names, fontsize=8)
        for r in range(mat.shape[0]):
            for c in range(mat.shape[1]):
                v = int(mat[r, c])
                color = "white" if v > (0.55 * vmax) else "black"
                ax.text(c, r, str(v), ha="center", va="center", fontsize=8, color=color)
    for j in range(len(entries), len(axes_arr)):
        axes_arr[j].axis("off")

    fig.suptitle(title)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)
    return True


def _build_confusion_by_source(
    *,
    task: str,
    y_true_all: np.ndarray,
    y_pred_all: np.ndarray,
    source_all: pd.Series,
    split_indices: Dict[str, np.ndarray],
    class_names: List[str],
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    src_all = source_all.astype(str).fillna("unknown").reset_index(drop=True)
    for split_name, idx in split_indices.items():
        split_out: Dict[str, Any] = {}
        idx_use = np.asarray(idx, dtype=np.int64)
        if idx_use.size == 0:
            out[split_name] = split_out
            continue
        src_split = src_all.iloc[idx_use]
        for src in sorted(src_split.unique().tolist()):
            m = (src_split.to_numpy() == src)
            if not np.any(m):
                continue
            yt = np.asarray(y_true_all[idx_use][m])
            yp = np.asarray(y_pred_all[idx_use][m])
            if task == "multilabel":
                per_label: Dict[str, Any] = {}
                for j, name in enumerate(class_names):
                    cm = confusion_matrix(
                        yt[:, j].astype(np.int64),
                        yp[:, j].astype(np.int64),
                        labels=[0, 1],
                    ).astype(np.int64)
                    per_label[str(name)] = {
                        "labels": ["0", "1"],
                        "matrix": cm.tolist(),
                        "counts": _confusion_counts(cm),
                    }
                split_out[str(src)] = {"n_rows": int(np.sum(m)), "per_label": per_label}
            else:
                if task == "binary":
                    labels = [0, 1]
                    label_names = class_names if len(class_names) == 2 else ["0", "1"]
                else:
                    labels = list(range(max(1, len(class_names))))
                    label_names = class_names if class_names else [str(v) for v in labels]
                cm = confusion_matrix(
                    yt.astype(np.int64),
                    yp.astype(np.int64),
                    labels=labels,
                ).astype(np.int64)
                split_out[str(src)] = {
                    "n_rows": int(np.sum(m)),
                    "labels": [str(x) for x in label_names],
                    "matrix": cm.tolist(),
                    "counts": _confusion_counts(cm),
                }
        out[split_name] = split_out
    return out


def _per_class_metrics_from_confusion(
    *,
    cm: np.ndarray,
    label_names: List[str],
) -> Dict[str, Any]:
    m = np.asarray(cm, dtype=np.int64)
    total = int(np.sum(m))
    out: Dict[str, Any] = {}
    for i, name in enumerate(label_names):
        tp = int(m[i, i]) if i < m.shape[0] and i < m.shape[1] else 0
        fn = int(np.sum(m[i, :]) - tp) if i < m.shape[0] else 0
        fp = int(np.sum(m[:, i]) - tp) if i < m.shape[1] else 0
        tn = int(total - tp - fn - fp)
        precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        recall = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = float((2.0 * precision * recall) / (precision + recall)) if (precision + recall) > 0 else 0.0
        accuracy = float((tp + tn) / total) if total > 0 else 0.0
        out[str(name)] = {
            "support": int(tp + fn),
            "tp": int(tp),
            "fp": int(fp),
            "fn": int(fn),
            "tn": int(tn),
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
            "accuracy": float(accuracy),
            # "success" here is class recall: correctly recovered examples of this class.
            "success_rate": float(recall),
        }
    return out


def fit_audio_tiny_cnn(
    df: pd.DataFrame,
    out_dir: Path,
    *,
    target_col: str = "ropumprun_label",
    task: str = "binary",
    target_cols: Optional[List[str]] = None,
    positive_threshold: float = 0.0,
    positive_label: str = "on",
    limit: int = 0,
    sample_mode: str = "random",
    test_size: float = 0.2,
    random_state: int = 42,
    epochs: int = 12,
    batch_size: int = 64,
    learning_rate: float = 1e-3,
    weight_decay: float = 1e-4,
    class_weight: Optional[str] = None,
    log_every: int = 1,
    quiet: bool = False,
    mel_config: Optional[Dict[str, Any]] = None,
    split_manifest_df: Optional[pd.DataFrame] = None,
    split_col: str = "split",
    dataset_id_col: str = "sample_id",
    split_manifest_id_col: str = "sample_id",
    split_stratify_col: str = "",
    model_arch: str = "tiny_cnn",
    oversample_class_col: str = "primary_class",
    oversample_classes: Optional[Sequence[str]] = None,
    oversample_multiplier: int = 1,
    lr_drop_epochs: Optional[List[int]] = None,
    lr_drop_gamma: float = 0.5,
    lr_plateau: bool = False,
    lr_plateau_factor: float = 0.5,
    lr_plateau_patience: int = 2,
    aux_target_pca: bool = False,
    aux_pca_feature_source: str = "window_cols",
    aux_pca_feature_cols: Optional[List[str]] = None,
    aux_pca_components: int = 8,
    aux_pca_variance_ratio: float = 0.0,
    aux_pca_weight: float = 0.1,
) -> AudioTinyCNNResult:
    torch, nn, DataLoader, TensorDataset = _require_torch()
    _seed_torch(torch, int(random_state))
    device = _select_device(torch)
    print(f"[device] audio_cnn using {device}", flush=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    if class_weight not in (None, "balanced"):
        raise ValueError("class_weight must be None or 'balanced'")
    aux_enabled = bool(aux_target_pca)
    aux_feature_source = str(aux_pca_feature_source).strip().lower()
    if aux_feature_source not in ("window_cols", "mel_flat"):
        raise ValueError("aux_pca_feature_source must be 'window_cols' or 'mel_flat'")
    if float(aux_pca_weight) < 0.0:
        raise ValueError("aux_pca_weight must be >= 0")
    if float(aux_pca_variance_ratio) < 0.0 or float(aux_pca_variance_ratio) > 1.0:
        raise ValueError("aux_pca_variance_ratio must be in [0,1]")
    if int(aux_pca_components) < 1:
        raise ValueError("aux_pca_components must be >= 1")
    df = _sample_rows(df, int(limit), str(sample_mode))
    task = str(task)
    multilabel_truth_threshold = float(positive_threshold)
    if task == "multilabel":
        cols = list(target_cols) if target_cols else ["overlap_s_producing", "overlap_s_delivering"]
        df, y_ml, y_meta = _coerce_multilabel_target(df, target_cols=cols, positive_threshold=float(positive_threshold))
        y = y_ml
    elif task == "multiregression":
        cols = list(target_cols) if target_cols else ["ropumprun_duty", "deliveryrun_duty"]
        df, y_reg, y_meta = _coerce_multiregression_target(df, target_cols=cols)
        y = y_reg
    else:
        df, y, y_meta = _coerce_target(df, target_col=target_col, task=task, positive_label=positive_label)
    df, split_ser, split_source = _attach_split_labels(
        df,
        split_manifest_df=split_manifest_df,
        split_col=str(split_col),
        dataset_id_col=str(dataset_id_col),
        split_manifest_id_col=str(split_manifest_id_col),
    )
    if len(df) < 8:
        raise ValueError("Not enough labeled rows to train tiny CNN.")

    X_mel = _load_mels_from_manifest_rows(df).astype("float32", copy=False)
    use_cmvn = bool((mel_config or {}).get("cmvn", False))
    if use_cmvn:
        X_mel = _cmvn_per_clip_per_freq(X_mel)
    n_mels = int(X_mel.shape[1])
    n_frames = int(X_mel.shape[2])
    X = X_mel[:, None, :, :]  # (N,1,M,T)

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
        X_mel = X_mel[np.asarray(keep_mask.to_numpy(), dtype=bool)]
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
            task=task,
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

    source_col = next((c for c in ("audio_source", "source_name", "source") if c in df.columns), None)
    source_series = (
        df[source_col].astype("string").fillna("unknown")
        if source_col is not None
        else pd.Series(["unknown"] * len(df), dtype="string")
    )

    if task not in ("multilabel", "multiregression"):
        if len(np.unique(y[idx_train])) < 2:
            raise ValueError("Train split has only one class after filtering; cannot train classifier.")
    else:
        if task == "multilabel" and int(np.sum(y[idx_train], axis=0).max()) <= 0:
            raise ValueError("Train split has no positive multilabel targets.")

    idx_train_fit, oversample_meta = _oversample_train_indices(
        df=df,
        idx_train=idx_train,
        oversample_class_col=str(oversample_class_col),
        oversample_classes=list(oversample_classes) if oversample_classes else None,
        oversample_multiplier=int(oversample_multiplier),
        random_state=int(random_state),
    )

    mel_global_norm: Dict[str, Any] = {"enabled": False}
    use_global_norm = bool((mel_config or {}).get("train_mel_global_norm", False))
    global_norm_eps = float((mel_config or {}).get("train_mel_global_norm_eps", 1e-6))
    if use_global_norm:
        train_view = np.asarray(X_mel[idx_train], dtype=np.float32)
        mean = float(np.mean(train_view, dtype=np.float64))
        std = float(np.std(train_view, dtype=np.float64))
        X_mel = _global_mel_norm(X_mel, mean=mean, std=std, eps=global_norm_eps)
        mel_global_norm = {
            "enabled": True,
            "fit_split": "train",
            "mean": float(mean),
            "std": float(std),
            "eps": float(global_norm_eps),
        }
        if not quiet:
            print(
                "[mel_global_norm] "
                f"mean={mean:.6g} std={std:.6g} eps={float(global_norm_eps):.2e}",
                flush=True,
            )

    aux_targets_all: Optional[np.ndarray] = None
    aux_meta: Dict[str, Any] = {"enabled": bool(aux_enabled)}
    if aux_enabled:
        if aux_feature_source == "mel_flat":
            X_aux_features = X_mel.reshape(X_mel.shape[0], -1).astype(np.float32, copy=False)
            aux_feature_cols_used: List[str] = [f"mel_flat_{i}" for i in range(int(X_aux_features.shape[1]))]
        else:
            aux_feature_cols_used = _select_aux_window_feature_columns(
                df,
                target_col=str(target_col),
                target_cols=list(target_cols) if target_cols else None,
                split_col=str(split_col),
                dataset_id_col=str(dataset_id_col),
                split_manifest_id_col=str(split_manifest_id_col),
                explicit_cols=list(aux_pca_feature_cols) if aux_pca_feature_cols else None,
            )
            feat_df = df[aux_feature_cols_used].apply(pd.to_numeric, errors="coerce")
            train_means = feat_df.iloc[idx_train].mean(axis=0, skipna=True)
            feat_df = feat_df.fillna(train_means)
            X_aux_features = feat_df.to_numpy(dtype=np.float32)

        if X_aux_features.shape[0] != len(df):
            raise ValueError("Aux feature row count mismatch")
        x_mean = np.mean(X_aux_features[idx_train], axis=0, dtype=np.float64)
        x_std = np.std(X_aux_features[idx_train], axis=0, dtype=np.float64)
        x_std = np.where(x_std > 1e-12, x_std, 1.0)
        X_aux_norm = ((X_aux_features - x_mean.reshape(1, -1)) / x_std.reshape(1, -1)).astype(np.float32, copy=False)

        var_ratio = float(aux_pca_variance_ratio)
        if var_ratio > 0.0:
            pca = PCA(n_components=float(var_ratio), svd_solver="full", random_state=int(random_state))
        else:
            n_max = int(min(int(aux_pca_components), X_aux_norm[idx_train].shape[0], X_aux_norm[idx_train].shape[1]))
            if n_max < 1:
                raise ValueError("Not enough train rows/features to fit aux PCA target.")
            pca = PCA(n_components=n_max, random_state=int(random_state))
        pca.fit(X_aux_norm[idx_train])
        aux_targets_all = pca.transform(X_aux_norm).astype(np.float32, copy=False)

        aux_pca_model_path = out_dir / "aux_target_pca_model.npz"
        np.savez(
            str(aux_pca_model_path),
            mean=x_mean.astype(np.float32),
            std=x_std.astype(np.float32),
            components=np.asarray(pca.components_, dtype=np.float32),
            explained_variance=np.asarray(getattr(pca, "explained_variance_", []), dtype=np.float32),
            explained_variance_ratio=np.asarray(getattr(pca, "explained_variance_ratio_", []), dtype=np.float32),
            feature_cols=np.asarray(aux_feature_cols_used, dtype=object),
        )
        aux_meta = {
            "enabled": True,
            "feature_source": str(aux_feature_source),
            "feature_cols": aux_feature_cols_used,
            "n_features": int(X_aux_features.shape[1]),
            "n_components": int(aux_targets_all.shape[1]),
            "variance_ratio_requested": float(var_ratio),
            "variance_ratio_captured": float(np.sum(getattr(pca, "explained_variance_ratio_", np.asarray([], dtype=np.float64)))),
            "weight": float(aux_pca_weight),
            "artifact_path": str(aux_pca_model_path),
            "fit_split": "train",
        }
        if not quiet:
            print(
                "[aux_pca] "
                f"source={aux_meta['feature_source']} "
                f"n_features={aux_meta['n_features']} "
                f"n_components={aux_meta['n_components']} "
                f"var={aux_meta['variance_ratio_captured']:.4f} "
                f"weight={aux_meta['weight']:.4f}",
                flush=True,
            )

    X_train_fit = torch.tensor(X[idx_train_fit], dtype=torch.float32)
    X_train = torch.tensor(X[idx_train], dtype=torch.float32)
    X_test = torch.tensor(X[idx_test], dtype=torch.float32)
    X_val = torch.tensor(X[idx_val], dtype=torch.float32)
    if task in ("multilabel", "multiregression"):
        y_train_fit = torch.tensor(y[idx_train_fit], dtype=torch.float32)
        y_train = torch.tensor(y[idx_train], dtype=torch.float32)
        y_test = torch.tensor(y[idx_test], dtype=torch.float32)
        y_val = torch.tensor(y[idx_val], dtype=torch.float32)
    else:
        y_train_fit = torch.tensor(y[idx_train_fit], dtype=torch.long)
        y_train = torch.tensor(y[idx_train], dtype=torch.long)
        y_test = torch.tensor(y[idx_test], dtype=torch.long)
        y_val = torch.tensor(y[idx_val], dtype=torch.long)

    if aux_targets_all is not None:
        y_aux_train_fit = torch.tensor(aux_targets_all[idx_train_fit], dtype=torch.float32)
        train_dl = DataLoader(TensorDataset(X_train_fit, y_train_fit, y_aux_train_fit), batch_size=int(batch_size), shuffle=True)
    else:
        train_dl = DataLoader(TensorDataset(X_train_fit, y_train_fit), batch_size=int(batch_size), shuffle=True)
    train_eval_dl = DataLoader(TensorDataset(X_train, y_train), batch_size=int(batch_size), shuffle=False)
    test_dl = DataLoader(TensorDataset(X_test, y_test), batch_size=int(batch_size), shuffle=False)
    val_dl = DataLoader(TensorDataset(X_val, y_val), batch_size=int(batch_size), shuffle=False)

    if task == "binary":
        n_classes = 2
        out_dim = 1
    elif task == "multiclass":
        n_classes = int(len(np.unique(y)))
        out_dim = n_classes
    else:
        n_classes = int(y.shape[1])
        out_dim = n_classes
    model, arch_kind = _build_model(nn, out_dim=out_dim, model_arch=str(model_arch))
    model = model.to(device)
    aux_head = None
    aux_criterion = None
    if aux_targets_all is not None:
        emb_probe = torch.zeros((1, 1, int(n_mels), int(n_frames)), dtype=torch.float32, device=device)
        with torch.no_grad():
            _, emb = _forward_logits_and_embedding(model, emb_probe, arch_kind=str(arch_kind))
        if emb is None:
            raise ValueError(f"Aux PCA target is enabled, but architecture {arch_kind} does not expose embeddings.")
        aux_head = nn.Linear(int(emb.shape[1]), int(aux_targets_all.shape[1])).to(device)
        aux_criterion = nn.SmoothL1Loss()

    loss_kwargs = _balanced_loss_kwargs(
        torch=torch,
        y_train=y[idx_train],
        task=task,
        class_weight=class_weight,
    )
    loss_kwargs = _move_loss_kwargs_to_device(loss_kwargs, device)
    if task == "binary":
        criterion = nn.BCEWithLogitsLoss(**loss_kwargs)
    elif task == "multilabel":
        if class_weight == "balanced":
            y_tr = (y[idx_train] >= multilabel_truth_threshold).astype(np.float32)
            pos = np.sum(y_tr, axis=0)
            neg = y_tr.shape[0] - pos
            pos_w = np.where(pos > 0, neg / np.maximum(pos, 1.0), 1.0).astype(np.float32)
            criterion = nn.BCEWithLogitsLoss(
                pos_weight=torch.tensor(pos_w, dtype=torch.float32, device=device)
            )
        else:
            criterion = nn.BCEWithLogitsLoss()
    elif task == "multiregression":
        criterion = nn.SmoothL1Loss()
    else:
        criterion = nn.CrossEntropyLoss(**loss_kwargs)

    optim_params = list(model.parameters()) + (list(aux_head.parameters()) if aux_head is not None else [])
    optim = torch.optim.AdamW(optim_params, lr=float(learning_rate), weight_decay=float(weight_decay))
    drop_epochs = set(int(e) for e in (lr_drop_epochs or []) if int(e) > 0)
    plateau_sched = None
    if bool(lr_plateau):
        plateau_sched = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optim,
            mode="max",
            factor=float(lr_plateau_factor),
            patience=int(lr_plateau_patience),
            threshold=1e-4,
            min_lr=1e-6,
        )

    def _predict(dl):
        model.eval()
        y_true: List[int] = []
        y_pred: List[int] = []
        y_score: List[float] = []
        with torch.no_grad():
            for xb, yb in dl:
                xb = xb.to(device)
                logits = model(xb)
                if task == "binary":
                    score = torch.sigmoid(logits.view(-1))
                    pred = (score >= 0.5).long()
                    y_score.extend(score.cpu().numpy().tolist())
                    y_pred.extend(pred.cpu().numpy().tolist())
                elif task == "multilabel":
                    score = torch.sigmoid(logits)
                    pred = (score >= 0.5).float()
                    y_score.extend(score.cpu().numpy().tolist())
                    y_pred.extend(pred.cpu().numpy().tolist())
                elif task == "multiregression":
                    score = torch.sigmoid(logits)
                    y_score.extend(score.cpu().numpy().tolist())
                    y_pred.extend(score.cpu().numpy().tolist())
                else:
                    prob = torch.softmax(logits, dim=1)
                    pred = torch.argmax(prob, dim=1)
                    y_pred.extend(pred.cpu().numpy().tolist())
                y_true.extend(yb.cpu().numpy().tolist())
        y_true_np = np.asarray(y_true)
        y_pred_np = np.asarray(y_pred)
        if task in ("binary", "multilabel", "multiregression"):
            y_score_np = np.asarray(y_score)
        else:
            y_score_np = None
        return y_true_np, y_pred_np, y_score_np

    def _binarize_multilabel_truth(y_true_arr: np.ndarray) -> np.ndarray:
        yt = np.asarray(y_true_arr, dtype=np.float64)
        if yt.ndim != 2:
            raise ValueError(f"Expected 2D multilabel truth, got {yt.shape}")
        return (yt >= multilabel_truth_threshold).astype(np.int64)

    n_epochs = int(epochs)
    log_every = max(1, int(log_every))
    for ep in range(1, n_epochs + 1):
        model.train()
        if aux_head is not None:
            aux_head.train()
        loss_sum = 0.0
        aux_loss_sum = 0.0
        n_samples = 0
        for batch in train_dl:
            if len(batch) == 3:
                xb, yb, y_auxb = batch
                y_auxb = y_auxb.to(device)
            else:
                xb, yb = batch
                y_auxb = None
            xb = xb.to(device)
            yb = yb.to(device)
            optim.zero_grad(set_to_none=True)
            logits, emb = _forward_logits_and_embedding(model, xb, arch_kind=str(arch_kind))
            if task == "binary":
                main_loss = criterion(logits.view(-1), yb.float())
            elif task == "multilabel":
                main_loss = criterion(logits, yb)
            elif task == "multiregression":
                main_loss = criterion(torch.sigmoid(logits), yb)
            else:
                main_loss = criterion(logits, yb)
            aux_loss = None
            if aux_head is not None and aux_criterion is not None and y_auxb is not None:
                if emb is None:
                    raise RuntimeError("Embedding missing for aux head forward pass.")
                aux_pred = aux_head(emb)
                aux_loss = aux_criterion(aux_pred, y_auxb)
                loss = main_loss + float(aux_pca_weight) * aux_loss
            else:
                loss = main_loss
            loss.backward()
            optim.step()
            bsz = int(yb.shape[0])
            loss_sum += float(loss.detach().cpu().item()) * bsz
            if aux_loss is not None:
                aux_loss_sum += float(aux_loss.detach().cpu().item()) * bsz
            n_samples += bsz

        avg_loss = (loss_sum / max(1, n_samples))
        need_eval = bool(plateau_sched is not None) or (ep in drop_epochs) or ((not quiet) and (ep % log_every == 0 or ep == n_epochs))
        if need_eval:
            y_train_true_ep, y_train_pred_ep, _ = _predict(train_eval_dl)
            y_test_true_ep, y_test_pred_ep, _ = _predict(test_dl)
            if task == "multilabel":
                y_train_true_bin_ep = _binarize_multilabel_truth(y_train_true_ep)
                y_test_true_bin_ep = _binarize_multilabel_truth(y_test_true_ep)
                train_acc = (
                    float(np.mean(np.all(y_train_true_bin_ep == y_train_pred_ep, axis=1))) if len(y_train_true_ep) else 0.0
                )
                test_acc = (
                    float(np.mean(np.all(y_test_true_bin_ep == y_test_pred_ep, axis=1))) if len(y_test_true_ep) else 0.0
                )
            elif task == "multiregression":
                train_acc = float(np.mean(np.abs(y_train_true_ep - y_train_pred_ep))) if len(y_train_true_ep) else 0.0
                test_acc = float(np.mean(np.abs(y_test_true_ep - y_test_pred_ep))) if len(y_test_true_ep) else 0.0
            else:
                train_acc = float((y_train_true_ep == y_train_pred_ep).mean()) if len(y_train_true_ep) else 0.0
                test_acc = float((y_test_true_ep == y_test_pred_ep).mean()) if len(y_test_true_ep) else 0.0
            if ep in drop_epochs:
                for pg in optim.param_groups:
                    pg["lr"] = max(1e-6, float(pg["lr"]) * float(lr_drop_gamma))
                if not quiet:
                    print(f"[lr] epoch={ep} manual_drop_gamma={float(lr_drop_gamma):.4f} lr={float(optim.param_groups[0]['lr']):.6g}", flush=True)
            if plateau_sched is not None:
                plateau_metric = -float(test_acc) if task == "multiregression" else float(test_acc)
                plateau_sched.step(plateau_metric)
                if not quiet:
                    metric_name = "test_mae" if task == "multiregression" else "test_acc"
                    print(f"[lr] epoch={ep} plateau_metric={metric_name} value={test_acc:.4f} lr={float(optim.param_groups[0]['lr']):.6g}", flush=True)
        if (not quiet) and (ep % log_every == 0 or ep == n_epochs):
            if task == "multilabel":
                print(
                    f"[epoch {ep:03d}/{n_epochs}] loss={avg_loss:.6f} "
                    f"aux_loss={(aux_loss_sum / max(1, n_samples)):.6f} "
                    f"train_exact_match={train_acc:.4f} "
                    f"test_exact_match={test_acc:.4f} "
                    f"lr={float(optim.param_groups[0]['lr']):.6g}",
                    flush=True,
                )
            elif task == "multiregression":
                print(
                    f"[epoch {ep:03d}/{n_epochs}] loss={avg_loss:.6f} "
                    f"aux_loss={(aux_loss_sum / max(1, n_samples)):.6f} "
                    f"train_mae={train_acc:.4f} "
                    f"test_mae={test_acc:.4f} "
                    f"lr={float(optim.param_groups[0]['lr']):.6g}",
                    flush=True,
                )
            else:
                print(
                    f"[epoch {ep:03d}/{n_epochs}] loss={avg_loss:.6f} "
                    f"aux_loss={(aux_loss_sum / max(1, n_samples)):.6f} "
                    f"train_acc={train_acc:.4f} "
                    f"test_acc={test_acc:.4f} "
                    f"lr={float(optim.param_groups[0]['lr']):.6g}",
                    flush=True,
                )

    y_train_true, y_train_pred_raw, y_train_score = _predict(train_eval_dl)
    y_test_true, y_test_pred_raw, y_test_score = _predict(test_dl)
    y_val_true, y_val_pred_raw, y_val_score = _predict(val_dl)
    if task == "multilabel":
        y_train_true_bin = _binarize_multilabel_truth(y_train_true)
        y_test_true_bin = _binarize_multilabel_truth(y_test_true)
        y_val_true_bin = _binarize_multilabel_truth(y_val_true) if len(y_val_true) else np.asarray([], dtype=np.int64)

    threshold_default = 0.5
    threshold_source = "default"
    tuned_thresholds: List[float] = [float(threshold_default)]
    threshold_report: Dict[str, Any] = {
        "default_threshold": float(threshold_default),
        "source_split": "default",
    }
    if task in ("binary", "multilabel"):
        if len(y_val_true) > 0 and y_val_score is not None:
            y_ref_true = y_val_true_bin if task == "multilabel" else y_val_true
            y_ref_score = y_val_score
            threshold_source = "val"
        elif len(y_test_true) > 0 and y_test_score is not None:
            y_ref_true = y_test_true_bin if task == "multilabel" else y_test_true
            y_ref_score = y_test_score
            threshold_source = "test_fallback"
        else:
            y_ref_true = None
            y_ref_score = None

        if y_ref_true is not None and y_ref_score is not None:
            if task == "binary":
                best = _tune_binary_threshold(
                    y_ref_true,
                    y_ref_score,
                    default_threshold=float(threshold_default),
                )
                tuned_thresholds = [float(best["threshold"])]
                threshold_report = {
                    "default_threshold": float(threshold_default),
                    "source_split": str(threshold_source),
                    "mode": "binary",
                    "selected": best,
                }
            else:
                class_names = list(y_meta.get("classes") or [f"class_{i}" for i in range(int(y_ref_score.shape[1]))])
                tuned_thresholds = []
                per_label: Dict[str, Any] = {}
                for j, name in enumerate(class_names):
                    best = _tune_binary_threshold(
                        y_ref_true[:, j],
                        y_ref_score[:, j],
                        default_threshold=float(threshold_default),
                    )
                    tuned_thresholds.append(float(best["threshold"]))
                    per_label[str(name)] = best
                threshold_report = {
                    "default_threshold": float(threshold_default),
                    "source_split": str(threshold_source),
                    "mode": "multilabel",
                    "per_label": per_label,
                }
        else:
            if task == "multilabel":
                tuned_thresholds = [float(threshold_default)] * int(y.shape[1])
            threshold_report["source_split"] = "default_no_scores"
    elif task == "multiregression":
        tuned_thresholds = [float(positive_threshold)] * int(y.shape[1])
        threshold_report = {
            "default_threshold": float(positive_threshold),
            "source_split": "fixed_from_positive_threshold",
            "mode": "multiregression",
        }

    if task in ("binary", "multilabel"):
        y_train_pred = _predict_from_scores(task=task, y_score=y_train_score, thresholds=tuned_thresholds, default_threshold=threshold_default)
        y_test_pred = _predict_from_scores(task=task, y_score=y_test_score, thresholds=tuned_thresholds, default_threshold=threshold_default)
        y_val_pred = _predict_from_scores(task=task, y_score=y_val_score, thresholds=tuned_thresholds, default_threshold=threshold_default)
        if not quiet:
            y_train_acc_true = y_train_true_bin if task == "multilabel" else y_train_true
            y_test_acc_true = y_test_true_bin if task == "multilabel" else y_test_true
            y_val_acc_true = y_val_true_bin if task == "multilabel" else y_val_true
            train_acc_tuned = _exact_match_acc(y_train_acc_true, y_train_pred, task=task)
            test_acc_tuned = _exact_match_acc(y_test_acc_true, y_test_pred, task=task)
            val_acc_tuned = _exact_match_acc(y_val_acc_true, y_val_pred, task=task) if len(y_val_true) else 0.0
            print(
                "[threshold] "
                f"source={threshold_report.get('source_split', 'default')} "
                f"thresholds={','.join(f'{v:.4f}' for v in tuned_thresholds)} "
                f"train_acc={train_acc_tuned:.4f} "
                f"test_acc={test_acc_tuned:.4f} "
                f"val_acc={val_acc_tuned:.4f}",
                flush=True,
            )
    else:
        y_train_pred = y_train_pred_raw
        y_test_pred = y_test_pred_raw
        y_val_pred = y_val_pred_raw

    # Store a small "projection" parquet analogous to pca_svm train_projection.parquet.
    # Run full-dataset inference in minibatches to avoid OOM on larger runs.
    model.eval()
    if task == "binary":
        score_parts: List[np.ndarray] = []
        with torch.no_grad():
            for i0 in range(0, X.shape[0], int(batch_size)):
                i1 = min(X.shape[0], i0 + int(batch_size))
                xb = torch.tensor(X[i0:i1], dtype=torch.float32, device=device)
                logits = model(xb).view(-1)
                score = torch.sigmoid(logits).cpu().numpy()
                score_parts.append(score)
        score_all = np.concatenate(score_parts, axis=0)
        pred_all = _predict_from_scores(
            task=task,
            y_score=score_all,
            thresholds=tuned_thresholds,
            default_threshold=threshold_default,
        )
    elif task == "multiclass":
        prob_parts: List[np.ndarray] = []
        pred_parts: List[np.ndarray] = []
        with torch.no_grad():
            for i0 in range(0, X.shape[0], int(batch_size)):
                i1 = min(X.shape[0], i0 + int(batch_size))
                xb = torch.tensor(X[i0:i1], dtype=torch.float32, device=device)
                logits = model(xb)
                prob = torch.softmax(logits, dim=1).cpu().numpy()
                pred = np.argmax(prob, axis=1).astype("int64")
                prob_parts.append(prob)
                pred_parts.append(pred)
        prob_all = np.concatenate(prob_parts, axis=0)
        pred_all = np.concatenate(pred_parts, axis=0)
    elif task == "multilabel":
        score_parts: List[np.ndarray] = []
        with torch.no_grad():
            for i0 in range(0, X.shape[0], int(batch_size)):
                i1 = min(X.shape[0], i0 + int(batch_size))
                xb = torch.tensor(X[i0:i1], dtype=torch.float32, device=device)
                logits = model(xb)
                score = torch.sigmoid(logits).cpu().numpy()
                score_parts.append(score)
        score_all = np.concatenate(score_parts, axis=0)
        pred_all = _predict_from_scores(
            task=task,
            y_score=score_all,
            thresholds=tuned_thresholds,
            default_threshold=threshold_default,
        )
    else:  # multiregression
        score_parts: List[np.ndarray] = []
        with torch.no_grad():
            for i0 in range(0, X.shape[0], int(batch_size)):
                i1 = min(X.shape[0], i0 + int(batch_size))
                xb = torch.tensor(X[i0:i1], dtype=torch.float32, device=device)
                logits = model(xb)
                score = torch.sigmoid(logits).cpu().numpy()
                score_parts.append(score)
        score_all = np.concatenate(score_parts, axis=0)
        pred_all = score_all.astype("float32", copy=False)

    # Add PCA coordinates (from flattened mel tensors) so the existing 4-panel
    # renderer can plot tiny-CNN runs with the same schema.
    X_flat = X_mel.reshape(X_mel.shape[0], -1).astype("float32", copy=False)
    n_comp = int(min(3, X_flat.shape[0], X_flat.shape[1]))
    if n_comp >= 1:
        pca = PCA(n_components=n_comp, random_state=int(random_state))
        Z = pca.fit_transform(X_flat)
    else:
        Z = np.zeros((X_flat.shape[0], 0), dtype="float32")

    proj_df = df.reset_index(drop=True).copy()
    proj_df["pca1"] = Z[:, 0] if Z.shape[1] >= 1 else 0.0
    proj_df["pca2"] = Z[:, 1] if Z.shape[1] >= 2 else 0.0
    proj_df["pca3"] = Z[:, 2] if Z.shape[1] >= 3 else 0.0
    proj_df["split"] = split_for_projection.reset_index(drop=True)
    if task == "multilabel":
        # Keep compatibility columns while exposing full multilabel outputs.
        y_bin_all = (y >= multilabel_truth_threshold).astype("int64")
        proj_df["y_true"] = y_bin_all[:, 0].astype("int64")
        proj_df["y_pred"] = pred_all[:, 0].astype("int64")
        for j, name in enumerate(list(y_meta.get("classes") or [])):
            proj_df[f"duty_true_{name}"] = y[:, j].astype("float64")
            proj_df[f"y_true_{name}"] = y_bin_all[:, j].astype("int64")
            proj_df[f"y_pred_{name}"] = pred_all[:, j].astype("int64")
            proj_df[f"score_{name}"] = score_all[:, j].astype("float64")
    elif task == "multiregression":
        classes = list(y_meta.get("classes") or [f"class_{i}" for i in range(int(pred_all.shape[1]))])
        thresh = float(positive_threshold)
        proj_df["y_true"] = (y[:, 0] >= thresh).astype("int64")
        proj_df["y_pred"] = (pred_all[:, 0] >= thresh).astype("int64")
        for j, name in enumerate(classes):
            proj_df[f"duty_true_{name}"] = y[:, j].astype("float64")
            proj_df[f"duty_pred_{name}"] = pred_all[:, j].astype("float64")
            proj_df[f"score_{name}"] = pred_all[:, j].astype("float64")
            proj_df[f"y_true_{name}"] = (y[:, j] >= thresh).astype("int64")
            proj_df[f"y_pred_{name}"] = (pred_all[:, j] >= thresh).astype("int64")
    else:
        proj_df["y_true"] = y.astype("int64")
        proj_df["y_pred"] = pred_all.astype("int64")
    if task == "binary":
        proj_df["score_positive"] = score_all.astype("float64")
    elif task == "multiclass":
        for j in range(prob_all.shape[1]):
            proj_df[f"score_class_{j}"] = prob_all[:, j].astype("float64")
    projection_path = out_dir / "train_projection.parquet"
    proj_df.to_parquet(projection_path, index=False)

    model_path = out_dir / "audio_tiny_cnn_model.pt"
    torch.save(
        {
            "bundle_type": "audio_tiny_cnn",
            "bundle_version": 1,
            "task": task,
            "target_col": target_col,
            "target_cols": (list(target_cols) if target_cols else None),
            "positive_threshold": float(positive_threshold),
            "multilabel_truth_threshold": float(multilabel_truth_threshold) if task == "multilabel" else None,
            "inference_threshold_default": float(threshold_default),
            "inference_thresholds": [float(v) for v in tuned_thresholds],
            "threshold_tuning": threshold_report,
            "y_meta": y_meta,
            "state_dict": model.state_dict(),
            "n_classes": int(n_classes),
            "output_dim": int(out_dim),
            "mel_shape": {"n_mels": int(n_mels), "n_frames": int(n_frames)},
            "mel_config": mel_config or {},
            "mel_global_norm": mel_global_norm,
            "n_rows": int(len(df)),
            "train_idx": idx_train.tolist(),
            "train_fit_idx": idx_train_fit.tolist(),
            "test_idx": idx_test.tolist(),
            "val_idx": idx_val.tolist(),
            "split_source": str(split_source),
            "split_stratify_col": str(split_stratify_col),
            "oversample": oversample_meta,
            "arch": {"kind": str(arch_kind)},
            "aux_target_pca": aux_meta,
        },
        model_path,
    )

    if task == "multilabel":
        class_counts = {
            str(name): int(np.sum(y[:, i] >= multilabel_truth_threshold))
            for i, name in enumerate(list(y_meta.get("classes") or []))
        }
        train_metrics = _metrics_multilabel(
            y_true=y_train_true_bin.astype(np.int64),
            y_pred=y_train_pred.astype(np.int64),
            y_score=y_train_score.astype(np.float64) if y_train_score is not None else None,
            class_names=list(y_meta.get("classes") or []),
        )
        test_metrics = _metrics_multilabel(
            y_true=y_test_true_bin.astype(np.int64),
            y_pred=y_test_pred.astype(np.int64),
            y_score=y_test_score.astype(np.float64) if y_test_score is not None else None,
            class_names=list(y_meta.get("classes") or []),
        )
        val_metrics = (
            _metrics_multilabel(
                y_true=y_val_true_bin.astype(np.int64),
                y_pred=y_val_pred.astype(np.int64),
                y_score=y_val_score.astype(np.float64) if y_val_score is not None else None,
                class_names=list(y_meta.get("classes") or []),
            )
            if len(y_val_true)
            else {}
        )
    elif task == "multiregression":
        classes = list(y_meta.get("classes") or [])
        class_counts = {
            str(name): int(np.sum(y[:, i] >= float(positive_threshold)))
            for i, name in enumerate(classes)
        }
        train_metrics = _metrics_multiregression(
            y_true=np.asarray(y_train_true, dtype=np.float64),
            y_pred=np.asarray(y_train_pred, dtype=np.float64),
            class_names=classes,
        )
        test_metrics = _metrics_multiregression(
            y_true=np.asarray(y_test_true, dtype=np.float64),
            y_pred=np.asarray(y_test_pred, dtype=np.float64),
            class_names=classes,
        )
        val_metrics = (
            _metrics_multiregression(
                y_true=np.asarray(y_val_true, dtype=np.float64),
                y_pred=np.asarray(y_val_pred, dtype=np.float64),
                class_names=classes,
            )
            if len(y_val_true)
            else {}
        )
        train_metrics["thresholded"] = _metrics_multilabel(
            y_true=(np.asarray(y_train_true, dtype=np.float64) >= float(positive_threshold)).astype(np.int64),
            y_pred=(np.asarray(y_train_pred, dtype=np.float64) >= float(positive_threshold)).astype(np.int64),
            y_score=np.asarray(y_train_pred, dtype=np.float64),
            class_names=classes,
        )
        test_metrics["thresholded"] = _metrics_multilabel(
            y_true=(np.asarray(y_test_true, dtype=np.float64) >= float(positive_threshold)).astype(np.int64),
            y_pred=(np.asarray(y_test_pred, dtype=np.float64) >= float(positive_threshold)).astype(np.int64),
            y_score=np.asarray(y_test_pred, dtype=np.float64),
            class_names=classes,
        )
        if len(y_val_true):
            val_metrics["thresholded"] = _metrics_multilabel(
                y_true=(np.asarray(y_val_true, dtype=np.float64) >= float(positive_threshold)).astype(np.int64),
                y_pred=(np.asarray(y_val_pred, dtype=np.float64) >= float(positive_threshold)).astype(np.int64),
                y_score=np.asarray(y_val_pred, dtype=np.float64),
                class_names=classes,
            )
    else:
        class_counts = {str(int(k)): int(v) for k, v in pd.Series(y).value_counts().sort_index().items()}
        train_metrics = _metrics_dict(y_train_true, y_train_pred, y_train_score, task=task)
        test_metrics = _metrics_dict(y_test_true, y_test_pred, y_test_score, task=task)
        val_metrics = _metrics_dict(y_val_true, y_val_pred, y_val_score, task=task) if len(y_val_true) else {}

    if task in ("binary", "multilabel", "multiregression"):
        y_score_all_for_source = score_all
    else:
        y_score_all_for_source = None
    by_source = {
        "column": str(source_col) if source_col is not None else "unknown",
        "train": _metrics_by_source(
            task=task,
            y_true_all=(np.asarray(y) >= multilabel_truth_threshold).astype(np.int64) if task == "multilabel" else np.asarray(y),
            y_pred_all=np.asarray(pred_all),
            y_score_all=np.asarray(y_score_all_for_source) if y_score_all_for_source is not None else None,
            source_all=source_series.reset_index(drop=True),
            idx=idx_train,
            class_names=list(y_meta.get("classes") or []),
        ),
        "test": _metrics_by_source(
            task=task,
            y_true_all=(np.asarray(y) >= multilabel_truth_threshold).astype(np.int64) if task == "multilabel" else np.asarray(y),
            y_pred_all=np.asarray(pred_all),
            y_score_all=np.asarray(y_score_all_for_source) if y_score_all_for_source is not None else None,
            source_all=source_series.reset_index(drop=True),
            idx=idx_test,
            class_names=list(y_meta.get("classes") or []),
        ),
        "val": _metrics_by_source(
            task=task,
            y_true_all=(np.asarray(y) >= multilabel_truth_threshold).astype(np.int64) if task == "multilabel" else np.asarray(y),
            y_pred_all=np.asarray(pred_all),
            y_score_all=np.asarray(y_score_all_for_source) if y_score_all_for_source is not None else None,
            source_all=source_series.reset_index(drop=True),
            idx=idx_val,
            class_names=list(y_meta.get("classes") or []),
        )
        if len(idx_val)
        else {},
    }
    if not quiet and by_source.get("test"):
        src_lines = []
        for src, m in sorted(by_source["test"].items()):
            acc = m.get("exact_match_accuracy", m.get("accuracy", None))
            if acc is not None:
                src_lines.append(f"{src}:{float(acc):.4f}")
            elif "mae_mean" in m:
                src_lines.append(f"{src}:mae={float(m['mae_mean']):.4f}")
        if src_lines:
            print("[by_source:test] " + " ".join(src_lines), flush=True)

    class_names_for_conf: List[str]
    if task == "multilabel":
        class_names_for_conf = list(y_meta.get("classes") or [f"class_{i}" for i in range(int(y.shape[1]))])
    elif task == "binary":
        class_names_for_conf = [str(v) for v in (y_meta.get("classes") or ["0", "1"])]
        if len(class_names_for_conf) != 2:
            class_names_for_conf = ["0", "1"]
    elif task == "multiclass":
        class_names_for_conf = [str(v) for v in (y_meta.get("classes") or [str(i) for i in range(int(n_classes))])]
    else:
        class_names_for_conf = []

    y_true_all_for_source = (
        (np.asarray(y) >= multilabel_truth_threshold).astype(np.int64)
        if task == "multilabel"
        else np.asarray(y)
    )
    confusions_by_source: Dict[str, Any] = {}
    confusion_artifacts: Dict[str, Any] = {}
    confusion_by_split: Dict[str, Any] = {}
    if task in ("binary", "multiclass", "multilabel"):
        confusions_by_source = _build_confusion_by_source(
            task=task,
            y_true_all=np.asarray(y_true_all_for_source),
            y_pred_all=np.asarray(pred_all),
            source_all=source_series.reset_index(drop=True),
            split_indices={
                "train": np.asarray(idx_train, dtype=np.int64),
                "test": np.asarray(idx_test, dtype=np.int64),
                "val": np.asarray(idx_val, dtype=np.int64),
            },
            class_names=class_names_for_conf,
        )
        conf_json_path = out_dir / "confusion_by_source.json"
        conf_json_path.write_text(json.dumps(confusions_by_source, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        confusion_artifacts["json"] = str(conf_json_path)

        conf_dir = out_dir / "confusion_by_source"
        conf_dir.mkdir(parents=True, exist_ok=True)
        atlas_paths: Dict[str, Any] = {}
        if task == "multilabel":
            for split_name, split_map in confusions_by_source.items():
                if not isinstance(split_map, dict) or not split_map:
                    continue
                label_paths: Dict[str, str] = {}
                for label_name in class_names_for_conf:
                    entries: List[Tuple[str, np.ndarray, int]] = []
                    for src, src_obj in split_map.items():
                        per_label = src_obj.get("per_label", {})
                        node = per_label.get(str(label_name), {})
                        mat = np.asarray(node.get("matrix", [[0, 0], [0, 0]]), dtype=np.int64)
                        n_rows = int(src_obj.get("n_rows", int(np.sum(mat))))
                        entries.append((str(src), mat, n_rows))
                    out_png = conf_dir / f"{split_name}_{label_name}_atlas.png"
                    ok = _plot_confusion_grid(
                        entries=entries,
                        label_names=["0", "1"],
                        title=f"{split_name} confusion by source ({label_name})",
                        out_png=out_png,
                    )
                    if ok:
                        label_paths[str(label_name)] = str(out_png)
                if label_paths:
                    atlas_paths[str(split_name)] = label_paths
        else:
            label_names = class_names_for_conf if class_names_for_conf else ["0", "1"]
            for split_name, split_map in confusions_by_source.items():
                if not isinstance(split_map, dict) or not split_map:
                    continue
                entries = [
                    (str(src), np.asarray(src_obj.get("matrix", [[0, 0], [0, 0]]), dtype=np.int64), int(src_obj.get("n_rows", 0)))
                    for src, src_obj in split_map.items()
                ]
                out_png = conf_dir / f"{split_name}_atlas.png"
                ok = _plot_confusion_grid(
                    entries=entries,
                    label_names=[str(v) for v in label_names],
                    title=f"{split_name} confusion by source",
                    out_png=out_png,
                )
                if ok:
                    atlas_paths[str(split_name)] = str(out_png)
        if atlas_paths:
            confusion_artifacts["atlases"] = atlas_paths
            if not quiet:
                print(f"[confusion_by_source] atlases={len(atlas_paths)} dir={conf_dir}", flush=True)

    if task in ("binary", "multiclass"):
        labels = [0, 1] if task == "binary" else list(range(max(1, len(class_names_for_conf))))
        split_arrays = {
            "train": (np.asarray(y_train_true, dtype=np.int64), np.asarray(y_train_pred, dtype=np.int64)),
            "test": (np.asarray(y_test_true, dtype=np.int64), np.asarray(y_test_pred, dtype=np.int64)),
            "val": (np.asarray(y_val_true, dtype=np.int64), np.asarray(y_val_pred, dtype=np.int64)),
        }
        conf_png_paths: Dict[str, str] = {}
        for split_name, (yt, yp) in split_arrays.items():
            if yt.size <= 0 or yp.size <= 0:
                continue
            cm = confusion_matrix(yt, yp, labels=labels).astype(np.int64)
            per_class = _per_class_metrics_from_confusion(cm=cm, label_names=[str(v) for v in class_names_for_conf])
            confusion_by_split[split_name] = {
                "labels": [str(v) for v in class_names_for_conf],
                "matrix": cm.tolist(),
                "counts": _confusion_counts(cm),
                "per_class": per_class,
            }

            out_png = out_dir / f"confusion_matrix_{split_name}.png"
            ok = _plot_confusion_grid(
                entries=[("all_sources", cm, int(yt.size))],
                label_names=[str(v) for v in class_names_for_conf],
                title=f"{split_name} confusion matrix",
                out_png=out_png,
            )
            if ok:
                conf_png_paths[split_name] = str(out_png)

        if conf_png_paths:
            confusion_artifacts["split_png"] = conf_png_paths

        if not quiet and "test" in confusion_by_split:
            t = confusion_by_split["test"]
            print(
                "[confusion:test] "
                f"labels={t.get('labels', [])} "
                f"matrix={t.get('matrix', [])}",
                flush=True,
            )
            for name, m in t.get("per_class", {}).items():
                print(
                    "[per_class:test] "
                    f"class={name} "
                    f"success={float(m.get('success_rate', 0.0)):.4f} "
                    f"precision={float(m.get('precision', 0.0)):.4f} "
                    f"recall={float(m.get('recall', 0.0)):.4f} "
                    f"f1={float(m.get('f1', 0.0)):.4f} "
                    f"support={int(m.get('support', 0))}",
                    flush=True,
                )

    metrics = {
        "task": task,
        "target_col": target_col,
        "target_cols": (list(target_cols) if target_cols else None),
        "positive_threshold": float(positive_threshold),
        "multilabel_truth_threshold": float(multilabel_truth_threshold) if task == "multilabel" else None,
        "inference_threshold_default": float(threshold_default),
        "inference_thresholds": [float(v) for v in tuned_thresholds] if task in ("binary", "multilabel", "multiregression") else None,
        "threshold_tuning": threshold_report if task in ("binary", "multilabel", "multiregression") else {},
        "y_meta": y_meta,
        "n_rows": int(len(df)),
        "n_train": int(len(idx_train)),
        "n_train_fit": int(len(idx_train_fit)),
        "n_test": int(len(idx_test)),
        "n_val": int(len(idx_val)),
        "split_source": str(split_source),
        "split_stratify_col": str(split_stratify_col),
        "oversample": oversample_meta,
        "class_counts": class_counts,
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
        "val_metrics": val_metrics,
        "metrics_by_source": by_source,
        "confusion_by_split": confusion_by_split,
        "confusion_by_source": confusions_by_source,
        "confusion_artifacts": confusion_artifacts,
        "aux_target_pca": aux_meta,
        "mel_global_norm": mel_global_norm,
        "train_params": {
            "model_arch": str(arch_kind),
            "epochs": int(epochs),
            "batch_size": int(batch_size),
            "learning_rate": float(learning_rate),
            "lr_drop_epochs": sorted([int(e) for e in drop_epochs]),
            "lr_drop_gamma": float(lr_drop_gamma),
            "lr_plateau": bool(lr_plateau),
            "lr_plateau_factor": float(lr_plateau_factor),
            "lr_plateau_patience": int(lr_plateau_patience),
            "weight_decay": float(weight_decay),
            "class_weight": (str(class_weight) if class_weight else None),
            "limit": int(limit),
            "sample_mode": str(sample_mode),
            "log_every": int(log_every),
            "quiet": bool(quiet),
            "aux_target_pca_enabled": bool(aux_meta.get("enabled", False)),
            "aux_pca_feature_source": str(aux_feature_source),
            "aux_pca_components": int(aux_pca_components),
            "aux_pca_variance_ratio": float(aux_pca_variance_ratio),
            "aux_pca_weight": float(aux_pca_weight),
        },
    }
    metrics_path = out_dir / "audio_tiny_cnn_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return AudioTinyCNNResult(model_path=model_path, metrics_path=metrics_path, projection_path=projection_path)


def load_audio_tiny_cnn_bundle(model_path: Path) -> Dict[str, Any]:
    torch, nn, _, _ = _require_torch()
    obj = torch.load(model_path, map_location="cpu")
    if not isinstance(obj, dict):
        raise ValueError("Tiny CNN bundle must be a dict")
    if str(obj.get("bundle_type", "")) != "audio_tiny_cnn":
        raise ValueError("Not an audio_tiny_cnn bundle")
    for key in ("state_dict", "mel_shape", "n_classes"):
        if key not in obj:
            raise ValueError(f"Tiny CNN bundle missing key: {key}")
    n_classes = int(obj["n_classes"])
    out_dim = int(obj.get("output_dim", 1 if str(obj.get("task", "binary")) == "binary" else n_classes))
    state_dict = obj["state_dict"]
    arch_kind = str(((obj.get("arch") or {}).get("kind")) or "").strip()

    # Backward/robust compatibility: infer architecture from key patterns when metadata is missing.
    sd_keys = [str(k) for k in getattr(state_dict, "keys", lambda: [])()]
    looks_resnet = any(k.startswith("stem.") or k.startswith("b1.") or k.startswith("head.") for k in sd_keys)
    looks_tiny = any(k.startswith("0.") or k.startswith("3.") or k.startswith("7.") for k in sd_keys)

    candidates: List[str] = []
    if arch_kind:
        candidates.append(arch_kind)
    if looks_resnet:
        candidates.append("resnet_small_v1")
    if looks_tiny:
        candidates.append("tiny_cnn_v1")
    if not candidates:
        candidates = ["tiny_cnn_v1", "resnet_small_v1"]
    # Preserve order, dedupe.
    ordered = list(dict.fromkeys(candidates))

    last_err: Optional[Exception] = None
    model = None
    for cand in ordered:
        try:
            m, _ = _build_model(nn, out_dim=out_dim, model_arch=cand)
            m.load_state_dict(state_dict)
            model = m
            arch_kind = cand
            break
        except Exception as exc:  # pragma: no cover - fallback path
            last_err = exc
            continue
    if model is None:
        raise ValueError(
            f"Failed to load tiny_cnn bundle architecture. "
            f"candidates={ordered}, first_state_keys={sd_keys[:8]}, error={last_err}"
        ) from last_err

    model.eval()
    obj["_model"] = model
    obj.setdefault("arch", {})
    if isinstance(obj["arch"], dict):
        obj["arch"]["kind"] = str(arch_kind)
    return obj


def _load_mel_input_for_cnn(
    *,
    bundle: Dict[str, Any],
    wav_path: Optional[Path] = None,
    mel_npy_path: Optional[Path] = None,
    mel_npz_path: Optional[Path] = None,
    mel_npz_key: str = "mel",
    mel_npz_index: int = 0,
) -> np.ndarray:
    expected_shape = (int(bundle["mel_shape"]["n_mels"]), int(bundle["mel_shape"]["n_frames"]))
    provided = [wav_path is not None, mel_npy_path is not None, mel_npz_path is not None]
    if sum(provided) != 1:
        raise ValueError("Provide exactly one of wav_path/mel_npy_path/mel_npz_path")

    if wav_path is not None:
        return _load_mel_from_wav(wav_path, mel_cfg=dict(bundle.get("mel_config") or {}), expected_shape=expected_shape)

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
        # nearest-neighbor resize for shape mismatch
        h, w = arr.shape
        th, tw = expected_shape
        yi = np.linspace(0, h - 1, th).round().astype(int)
        xi = np.linspace(0, w - 1, tw).round().astype(int)
        arr = arr[np.ix_(yi, xi)]
    return arr.astype("float32", copy=False)


def predict_audio_tiny_cnn(
    model_path: Path,
    *,
    wav_path: Optional[Path] = None,
    mel_npy_path: Optional[Path] = None,
    mel_npz_path: Optional[Path] = None,
    mel_npz_key: str = "mel",
    mel_npz_index: int = 0,
) -> Dict[str, Any]:
    torch, _, _, _ = _require_torch()
    device = _select_device(torch)
    bundle = load_audio_tiny_cnn_bundle(model_path)
    mel = _load_mel_input_for_cnn(
        bundle=bundle,
        wav_path=wav_path,
        mel_npy_path=mel_npy_path,
        mel_npz_path=mel_npz_path,
        mel_npz_key=mel_npz_key,
        mel_npz_index=int(mel_npz_index),
    )
    if bool((bundle.get("mel_config") or {}).get("cmvn", False)):
        mel = _cmvn_per_clip_per_freq(mel[None, :, :])[0]
    gnorm = bundle.get("mel_global_norm") or {}
    if bool(gnorm.get("enabled", False)):
        mel = _global_mel_norm(
            mel,
            mean=float(gnorm.get("mean", 0.0)),
            std=float(gnorm.get("std", 1.0)),
            eps=float(gnorm.get("eps", 1e-6)),
        )
    x = torch.tensor(mel[None, None, :, :], dtype=torch.float32, device=device)
    model = bundle["_model"].to(device)
    model.eval()
    with torch.no_grad():
        logits = model(x)
        task = str(bundle.get("task", "binary"))
        default_thr = float(bundle.get("inference_threshold_default", 0.5))
        bundle_thresholds = bundle.get("inference_thresholds")
        thr_list: List[float] = []
        if isinstance(bundle_thresholds, (list, tuple)):
            thr_list = [float(v) for v in bundle_thresholds]
        if task == "binary":
            prob = torch.sigmoid(logits.view(-1))[0].item()
            thr = float(thr_list[0]) if thr_list else float(default_thr)
            pred = 1 if prob >= thr else 0
            out = {
                "bundle_type": "audio_tiny_cnn",
                "task": "binary",
                "predicted_index": int(pred),
                "predicted_label": "positive" if pred == 1 else "negative",
                "score_positive": float(prob),
                "probabilities": [float(1.0 - prob), float(prob)],
                "threshold_used": float(thr),
                "mel_shape_used": [int(mel.shape[0]), int(mel.shape[1])],
            }
        elif task == "multilabel":
            prob = torch.sigmoid(logits)[0].cpu().numpy()
            classes = list((bundle.get("y_meta") or {}).get("classes") or [])
            if not classes:
                classes = [f"class_{i}" for i in range(int(prob.shape[0]))]
            if len(thr_list) != len(classes):
                thr_list = [float(default_thr)] * len(classes)
            pred = (prob >= np.asarray(thr_list, dtype=np.float64)).astype("int64")
            out = {
                "bundle_type": "audio_tiny_cnn",
                "task": "multilabel",
                "predicted_multi_hot": [int(v) for v in pred.tolist()],
                "probabilities": [float(v) for v in prob.tolist()],
                "classes": [str(c) for c in classes],
                "scores_by_class": {str(classes[i]): float(prob[i]) for i in range(len(classes))},
                "thresholds_by_class": {str(classes[i]): float(thr_list[i]) for i in range(len(classes))},
                "predicted_labels": [str(classes[i]) for i in range(len(classes)) if int(pred[i]) == 1],
                "mel_shape_used": [int(mel.shape[0]), int(mel.shape[1])],
            }
        elif task == "multiregression":
            duty = torch.sigmoid(logits)[0].cpu().numpy()
            classes = list((bundle.get("y_meta") or {}).get("classes") or [])
            if not classes:
                classes = [f"class_{i}" for i in range(int(duty.shape[0]))]
            if len(thr_list) != len(classes):
                thr_list = [float(default_thr)] * len(classes)
            pred = (duty >= np.asarray(thr_list, dtype=np.float64)).astype("int64")
            out = {
                "bundle_type": "audio_tiny_cnn",
                "task": "multiregression",
                "classes": [str(c) for c in classes],
                "duties": [float(v) for v in duty.tolist()],
                "duties_by_class": {str(classes[i]): float(duty[i]) for i in range(len(classes))},
                "thresholds_by_class": {str(classes[i]): float(thr_list[i]) for i in range(len(classes))},
                "predicted_multi_hot": [int(v) for v in pred.tolist()],
                "predicted_labels": [str(classes[i]) for i in range(len(classes)) if int(pred[i]) == 1],
                "mel_shape_used": [int(mel.shape[0]), int(mel.shape[1])],
            }
        else:
            prob = torch.softmax(logits, dim=1)[0].cpu().numpy()
            pred = int(np.argmax(prob))
            out = {
                "bundle_type": "audio_tiny_cnn",
                "task": "multiclass",
                "predicted_index": pred,
                "probabilities": [float(v) for v in prob.tolist()],
                "mel_shape_used": [int(mel.shape[0]), int(mel.shape[1])],
            }
            y_meta = bundle.get("y_meta") or {}
            classes = y_meta.get("classes")
            if isinstance(classes, list) and 0 <= pred < len(classes):
                out["predicted_label"] = str(classes[pred])
    return out
