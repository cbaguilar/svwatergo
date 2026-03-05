from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

try:
    from sklearn.decomposition import PCA
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


class _TinyCNN:
    def __init__(self, nn, out_dim: int):
        self.model = nn.Sequential(
            nn.Conv2d(1, 8, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(8, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((4, 8)),
            nn.Flatten(),
            nn.Linear(16 * 4 * 8, 32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, int(out_dim)),
        )


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
        y_cols.append((s.to_numpy(dtype=np.float32) > float(positive_threshold)).astype(np.float32))
    if int(keep_mask.sum()) <= 0:
        raise ValueError("No valid rows for multilabel target after coercion")
    out = out.loc[keep_mask].reset_index(drop=True)
    Y = np.stack([col[keep_mask] for col in y_cols], axis=1).astype(np.float32)
    y_meta: Dict[str, Any] = {
        "task": "multilabel",
        "target_cols": [str(c) for c in target_cols],
        "positive_rule": f"value > {float(positive_threshold)}",
        "classes": [str(c) for c in target_cols],
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
) -> AudioTinyCNNResult:
    torch, nn, DataLoader, TensorDataset = _require_torch()
    _seed_torch(torch, int(random_state))
    device = _select_device(torch)
    out_dir.mkdir(parents=True, exist_ok=True)

    if class_weight not in (None, "balanced"):
        raise ValueError("class_weight must be None or 'balanced'")
    df = _sample_rows(df, int(limit), str(sample_mode))
    task = str(task)
    if task == "multilabel":
        cols = list(target_cols) if target_cols else ["overlap_s_producing", "overlap_s_delivering"]
        df, y_ml, y_meta = _coerce_multilabel_target(df, target_cols=cols, positive_threshold=float(positive_threshold))
        y = y_ml
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
        stratify = (y if (task != "multilabel" and len(np.unique(y)) > 1) else None)
        idx_train, idx_test = train_test_split(
            idx,
            test_size=float(test_size),
            random_state=int(random_state),
            stratify=stratify,
        )
        split_for_projection = pd.Series(["train"] * len(df), index=df.index, dtype="string")
        split_for_projection.iloc[idx_test] = "test"

    if task != "multilabel":
        if len(np.unique(y[idx_train])) < 2:
            raise ValueError("Train split has only one class after filtering; cannot train classifier.")
    else:
        if int(np.sum(y[idx_train], axis=0).max()) <= 0:
            raise ValueError("Train split has no positive multilabel targets.")

    X_train = torch.tensor(X[idx_train], dtype=torch.float32)
    X_test = torch.tensor(X[idx_test], dtype=torch.float32)
    X_val = torch.tensor(X[idx_val], dtype=torch.float32)
    if task == "multilabel":
        y_train = torch.tensor(y[idx_train], dtype=torch.float32)
        y_test = torch.tensor(y[idx_test], dtype=torch.float32)
        y_val = torch.tensor(y[idx_val], dtype=torch.float32)
    else:
        y_train = torch.tensor(y[idx_train], dtype=torch.long)
        y_test = torch.tensor(y[idx_test], dtype=torch.long)
        y_val = torch.tensor(y[idx_val], dtype=torch.long)

    train_dl = DataLoader(TensorDataset(X_train, y_train), batch_size=int(batch_size), shuffle=True)
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
    tiny = _TinyCNN(nn, out_dim=out_dim)
    model = tiny.model.to(device)

    loss_kwargs = _balanced_loss_kwargs(
        torch=torch,
        y_train=y[idx_train],
        task=task,
        class_weight=class_weight,
    )
    if task == "binary":
        criterion = nn.BCEWithLogitsLoss(**loss_kwargs)
    elif task == "multilabel":
        if class_weight == "balanced":
            y_tr = y[idx_train].astype(np.float32)
            pos = np.sum(y_tr, axis=0)
            neg = y_tr.shape[0] - pos
            pos_w = np.where(pos > 0, neg / np.maximum(pos, 1.0), 1.0).astype(np.float32)
            criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(pos_w, dtype=torch.float32))
        else:
            criterion = nn.BCEWithLogitsLoss()
    else:
        criterion = nn.CrossEntropyLoss(**loss_kwargs)

    optim = torch.optim.AdamW(model.parameters(), lr=float(learning_rate), weight_decay=float(weight_decay))

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
                else:
                    prob = torch.softmax(logits, dim=1)
                    pred = torch.argmax(prob, dim=1)
                    y_pred.extend(pred.cpu().numpy().tolist())
                y_true.extend(yb.cpu().numpy().tolist())
        y_true_np = np.asarray(y_true)
        y_pred_np = np.asarray(y_pred)
        if task in ("binary", "multilabel"):
            y_score_np = np.asarray(y_score)
        else:
            y_score_np = None
        return y_true_np, y_pred_np, y_score_np

    n_epochs = int(epochs)
    log_every = max(1, int(log_every))
    for ep in range(1, n_epochs + 1):
        model.train()
        loss_sum = 0.0
        n_samples = 0
        for xb, yb in train_dl:
            xb = xb.to(device)
            yb = yb.to(device)
            optim.zero_grad(set_to_none=True)
            logits = model(xb)
            if task == "binary":
                loss = criterion(logits.view(-1), yb.float())
            elif task == "multilabel":
                loss = criterion(logits, yb)
            else:
                loss = criterion(logits, yb)
            loss.backward()
            optim.step()
            bsz = int(yb.shape[0])
            loss_sum += float(loss.detach().cpu().item()) * bsz
            n_samples += bsz

        if (not quiet) and (ep % log_every == 0 or ep == n_epochs):
            avg_loss = (loss_sum / max(1, n_samples))
            y_train_true_ep, y_train_pred_ep, _ = _predict(train_dl)
            y_test_true_ep, y_test_pred_ep, _ = _predict(test_dl)
            if task == "multilabel":
                train_acc = float(np.mean(np.all(y_train_true_ep == y_train_pred_ep, axis=1))) if len(y_train_true_ep) else 0.0
                test_acc = float(np.mean(np.all(y_test_true_ep == y_test_pred_ep, axis=1))) if len(y_test_true_ep) else 0.0
            else:
                train_acc = float((y_train_true_ep == y_train_pred_ep).mean()) if len(y_train_true_ep) else 0.0
                test_acc = float((y_test_true_ep == y_test_pred_ep).mean()) if len(y_test_true_ep) else 0.0
            print(
                f"[epoch {ep:03d}/{n_epochs}] loss={avg_loss:.6f} train_acc={train_acc:.4f} test_acc={test_acc:.4f}",
                flush=True,
            )

    y_train_true, y_train_pred, y_train_score = _predict(train_dl)
    y_test_true, y_test_pred, y_test_score = _predict(test_dl)
    y_val_true, y_val_pred, y_val_score = _predict(val_dl)

    # Store a small "projection" parquet analogous to pca_svm train_projection.parquet.
    # Run full-dataset inference in minibatches to avoid OOM on larger runs.
    model.eval()
    if task == "binary":
        score_parts: List[np.ndarray] = []
        pred_parts: List[np.ndarray] = []
        with torch.no_grad():
            for i0 in range(0, X.shape[0], int(batch_size)):
                i1 = min(X.shape[0], i0 + int(batch_size))
                xb = torch.tensor(X[i0:i1], dtype=torch.float32, device=device)
                logits = model(xb).view(-1)
                score = torch.sigmoid(logits).cpu().numpy()
                pred = (score >= 0.5).astype("int64")
                score_parts.append(score)
                pred_parts.append(pred)
        score_all = np.concatenate(score_parts, axis=0)
        pred_all = np.concatenate(pred_parts, axis=0)
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
    else:
        score_parts: List[np.ndarray] = []
        pred_parts = []
        with torch.no_grad():
            for i0 in range(0, X.shape[0], int(batch_size)):
                i1 = min(X.shape[0], i0 + int(batch_size))
                xb = torch.tensor(X[i0:i1], dtype=torch.float32, device=device)
                logits = model(xb)
                score = torch.sigmoid(logits).cpu().numpy()
                pred = (score >= 0.5).astype("int64")
                score_parts.append(score)
                pred_parts.append(pred)
        score_all = np.concatenate(score_parts, axis=0)
        pred_all = np.concatenate(pred_parts, axis=0)

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
        proj_df["y_true"] = y[:, 0].astype("int64")
        proj_df["y_pred"] = pred_all[:, 0].astype("int64")
        for j, name in enumerate(list(y_meta.get("classes") or [])):
            proj_df[f"y_true_{name}"] = y[:, j].astype("int64")
            proj_df[f"y_pred_{name}"] = pred_all[:, j].astype("int64")
            proj_df[f"score_{name}"] = score_all[:, j].astype("float64")
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
            "y_meta": y_meta,
            "state_dict": model.state_dict(),
            "n_classes": int(n_classes),
            "output_dim": int(out_dim),
            "mel_shape": {"n_mels": int(n_mels), "n_frames": int(n_frames)},
            "mel_config": mel_config or {},
            "n_rows": int(len(df)),
            "train_idx": idx_train.tolist(),
            "test_idx": idx_test.tolist(),
            "val_idx": idx_val.tolist(),
            "split_source": str(split_source),
            "arch": {"kind": "tiny_cnn_v1"},
        },
        model_path,
    )

    if task == "multilabel":
        class_counts = {
            str(name): int(np.sum(y[:, i]))
            for i, name in enumerate(list(y_meta.get("classes") or []))
        }
        train_metrics = _metrics_multilabel(
            y_true=y_train_true.astype(np.int64),
            y_pred=y_train_pred.astype(np.int64),
            y_score=y_train_score.astype(np.float64) if y_train_score is not None else None,
            class_names=list(y_meta.get("classes") or []),
        )
        test_metrics = _metrics_multilabel(
            y_true=y_test_true.astype(np.int64),
            y_pred=y_test_pred.astype(np.int64),
            y_score=y_test_score.astype(np.float64) if y_test_score is not None else None,
            class_names=list(y_meta.get("classes") or []),
        )
        val_metrics = (
            _metrics_multilabel(
                y_true=y_val_true.astype(np.int64),
                y_pred=y_val_pred.astype(np.int64),
                y_score=y_val_score.astype(np.float64) if y_val_score is not None else None,
                class_names=list(y_meta.get("classes") or []),
            )
            if len(y_val_true)
            else {}
        )
    else:
        class_counts = {str(int(k)): int(v) for k, v in pd.Series(y).value_counts().sort_index().items()}
        train_metrics = _metrics_dict(y_train_true, y_train_pred, y_train_score, task=task)
        test_metrics = _metrics_dict(y_test_true, y_test_pred, y_test_score, task=task)
        val_metrics = _metrics_dict(y_val_true, y_val_pred, y_val_score, task=task) if len(y_val_true) else {}

    metrics = {
        "task": task,
        "target_col": target_col,
        "target_cols": (list(target_cols) if target_cols else None),
        "positive_threshold": float(positive_threshold),
        "y_meta": y_meta,
        "n_rows": int(len(df)),
        "n_train": int(len(idx_train)),
        "n_test": int(len(idx_test)),
        "n_val": int(len(idx_val)),
        "split_source": str(split_source),
        "class_counts": class_counts,
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
        "val_metrics": val_metrics,
        "train_params": {
            "epochs": int(epochs),
            "batch_size": int(batch_size),
            "learning_rate": float(learning_rate),
            "weight_decay": float(weight_decay),
            "class_weight": (str(class_weight) if class_weight else None),
            "limit": int(limit),
            "sample_mode": str(sample_mode),
            "log_every": int(log_every),
            "quiet": bool(quiet),
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
    tiny = _TinyCNN(nn, out_dim=out_dim)
    tiny.model.load_state_dict(obj["state_dict"])
    tiny.model.eval()
    obj["_model"] = tiny.model
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
    x = torch.tensor(mel[None, None, :, :], dtype=torch.float32, device=device)
    model = bundle["_model"].to(device)
    model.eval()
    with torch.no_grad():
        logits = model(x)
        task = str(bundle.get("task", "binary"))
        if task == "binary":
            prob = torch.sigmoid(logits.view(-1))[0].item()
            pred = 1 if prob >= 0.5 else 0
            out = {
                "bundle_type": "audio_tiny_cnn",
                "task": "binary",
                "predicted_index": int(pred),
                "predicted_label": "positive" if pred == 1 else "negative",
                "score_positive": float(prob),
                "probabilities": [float(1.0 - prob), float(prob)],
                "mel_shape_used": [int(mel.shape[0]), int(mel.shape[1])],
            }
        elif task == "multilabel":
            prob = torch.sigmoid(logits)[0].cpu().numpy()
            pred = (prob >= 0.5).astype("int64")
            classes = list((bundle.get("y_meta") or {}).get("classes") or [])
            if not classes:
                classes = [f"class_{i}" for i in range(int(prob.shape[0]))]
            out = {
                "bundle_type": "audio_tiny_cnn",
                "task": "multilabel",
                "predicted_multi_hot": [int(v) for v in pred.tolist()],
                "probabilities": [float(v) for v in prob.tolist()],
                "classes": [str(c) for c in classes],
                "scores_by_class": {str(classes[i]): float(prob[i]) for i in range(len(classes))},
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
