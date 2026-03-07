from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .audio_pca_svm import _attach_split_labels, _coerce_target, _normalize_split_value
from .audio_pretrained_embeddings import _PannsBackend, _coerce_audio_path_column, _extract_embeddings

try:
    from sklearn.decomposition import PCA
    from sklearn.metrics import confusion_matrix
    from sklearn.metrics import f1_score, precision_score, r2_score, recall_score
except Exception as e:
    raise SystemExit("Missing scikit-learn. Install: pip install scikit-learn") from e


@dataclass(frozen=True)
class AudioPretrainedEmbeddingMultitaskResult:
    out_dir: Path
    metrics_path: Path
    model_path: Path


def _coerce_binary_targets(
    df: pd.DataFrame,
    *,
    target_cols: Sequence[str],
    positive_threshold: float,
    positive_label: str,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    cols = [str(c).strip() for c in target_cols if str(c).strip()]
    if not cols:
        raise ValueError("target_cols cannot be empty")
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing target columns: {', '.join(missing)}")

    Y = np.zeros((len(df), len(cols)), dtype=np.float32)
    for j, c in enumerate(cols):
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            v = pd.to_numeric(s, errors="coerce").fillna(0.0).to_numpy(dtype=np.float32)
            y = (v >= float(positive_threshold)).astype(np.float32)
        else:
            lab = str(positive_label).strip().lower()
            y = s.astype(str).str.strip().str.lower().eq(lab).astype(np.float32).to_numpy()
        Y[:, j] = y
    return Y, {"task": "multilabel", "target_cols": cols, "positive_threshold": float(positive_threshold)}


def _select_plc_feature_columns(
    df: pd.DataFrame,
    *,
    target_cols: Sequence[str],
    split_col: str,
    dataset_id_col: str,
    split_manifest_id_col: str,
    explicit_cols: Optional[Sequence[str]],
    include_duty_cols: bool,
) -> List[str]:
    default_exclude_regex = [
        # Counter/time-like leak-prone columns.
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
        # Segment/source metadata (non-physical, often leak source/session details).
        r"^source_",
        r"^segment_",
        r"^window_seconds$",
        r"^n_rows$",
        # State/proxy features that are too close to targets.
        r"^state_",
        r"^state__",
        r"^warnword",
        r"^overlap_s_",
        r"^quiet_full$",
        r"^is_transition_segment$",
        r"^transition_count$",
        r"run__transitions$",
        r"__transitions$",
    ]
    excl_regs = [re.compile(p, flags=re.IGNORECASE) for p in default_exclude_regex]

    if explicit_cols:
        cols = [str(c).strip() for c in explicit_cols if str(c).strip()]
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"aux_pca_feature_cols missing columns: {', '.join(missing)}")
        keep = []
        for c in cols:
            s = pd.to_numeric(df[c], errors="coerce")
            if int(s.notna().sum()) <= 0:
                continue
            if float(s.std(skipna=True)) <= 0.0:
                continue
            keep.append(c)
        if not keep:
            raise ValueError("Explicit aux PLC feature list had no valid non-constant numeric columns")
        return keep

    excluded = {
        str(split_col),
        str(dataset_id_col),
        str(split_manifest_id_col),
        "mel_shard_local_index",
    }
    excluded.update(str(c) for c in target_cols)

    cols: List[str] = []
    for c in df.columns:
        cs = str(c)
        if cs in excluded:
            continue
        lc = cs.lower()
        if "label" in lc:
            continue
        if (not include_duty_cols) and lc.endswith("_duty"):
            continue
        if any(r.search(cs) for r in excl_regs):
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            s = pd.to_numeric(df[c], errors="coerce")
            if int(s.notna().sum()) <= 0:
                continue
            if float(s.std(skipna=True)) <= 0.0:
                continue
            cols.append(cs)
    if not cols:
        raise ValueError("No valid numeric PLC columns for aux PCA")
    return cols


def _fit_pca_targets(
    X: np.ndarray,
    idx_train: np.ndarray,
    *,
    n_components: int,
    variance_ratio: float,
    random_state: int,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    Xf = np.asarray(X, dtype=np.float32)
    if Xf.ndim != 2:
        Xf = Xf.reshape(Xf.shape[0], -1)
    mu = Xf[idx_train].mean(axis=0, keepdims=True)
    sd = Xf[idx_train].std(axis=0, keepdims=True)
    sd = np.where(sd > 0, sd, 1.0)
    Xn = ((Xf - mu) / sd).astype(np.float32, copy=False)

    var_ratio = float(variance_ratio)
    if var_ratio > 0.0 and var_ratio <= 1.0:
        pca = PCA(n_components=var_ratio, svd_solver="full", random_state=int(random_state))
    else:
        n_max = int(min(int(n_components), Xn[idx_train].shape[0], Xn[idx_train].shape[1]))
        if n_max < 1:
            raise ValueError("Not enough rows/features to fit PCA")
        pca = PCA(n_components=n_max, random_state=int(random_state))
    pca.fit(Xn[idx_train])
    Z = pca.transform(Xn).astype(np.float32, copy=False)
    meta = {
        "mean": mu.squeeze(0).astype(np.float32),
        "std": sd.squeeze(0).astype(np.float32),
        "components": np.asarray(pca.components_, dtype=np.float32),
        "explained_variance": np.asarray(getattr(pca, "explained_variance_", []), dtype=np.float32),
        "explained_variance_ratio": np.asarray(getattr(pca, "explained_variance_ratio_", []), dtype=np.float32),
        "n_components": int(Z.shape[1]),
        "variance_ratio_captured": float(np.sum(getattr(pca, "explained_variance_ratio_", np.asarray([], dtype=np.float64)))),
    }
    return Z, meta


def _combo_label(bits: np.ndarray, target_cols: Sequence[str]) -> str:
    cols = [str(c) for c in target_cols]
    vals = [int(v) for v in np.asarray(bits).astype(int).tolist()]
    if len(cols) == 2:
        c0 = cols[0].lower()
        c1 = cols[1].lower()
        if "ropumprun" in c0 and "deliveryrun" in c1:
            p0 = "producing" if vals[0] == 1 else "not_producing"
            p1 = "delivering" if vals[1] == 1 else "not_delivering"
            return f"{p0}|{p1}"
    return "|".join(f"{c}={v}" for c, v in zip(cols, vals))


def _build_confusion_payload(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    target_cols: Sequence[str],
) -> Dict[str, Any]:
    if len(y_true) <= 0:
        return {"labels": [], "matrix": [], "n_rows": 0, "per_target": {}}

    yt = np.asarray(y_true).astype(int)
    yp = np.asarray(y_pred).astype(int)
    true_labels = [_combo_label(row, target_cols) for row in yt]
    pred_labels = [_combo_label(row, target_cols) for row in yp]
    labels = sorted(set(true_labels) | set(pred_labels))
    cm = confusion_matrix(true_labels, pred_labels, labels=labels)

    per_target: Dict[str, Any] = {}
    for j, c in enumerate(target_cols):
        ytj = yt[:, j]
        ypj = yp[:, j]
        cmj = confusion_matrix(ytj, ypj, labels=[0, 1])
        tn, fp, fn, tp = [int(x) for x in cmj.reshape(-1).tolist()]
        precision = float(tp / max(1, tp + fp))
        recall = float(tp / max(1, tp + fn))
        f1 = float((2.0 * precision * recall) / max(1e-12, precision + recall))
        acc = float((tp + tn) / max(1, int(len(ytj))))
        per_target[str(c)] = {
            "labels": [0, 1],
            "matrix": cmj.tolist(),
            "accuracy": acc,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": int(np.sum(ytj == 1)),
        }

    return {
        "labels": labels,
        "matrix": cm.tolist(),
        "n_rows": int(len(yt)),
        "per_target": per_target,
    }


def _plot_confusion_png(
    *,
    labels: Sequence[str],
    matrix: Sequence[Sequence[int]],
    title: str,
    out_png: Path,
) -> bool:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:
        return False
    if not labels:
        return False
    cm = np.asarray(matrix, dtype=np.int64)
    if cm.size == 0:
        return False
    fig, ax = plt.subplots(1, 1, figsize=(6.8, 5.8), constrained_layout=True)
    im = ax.imshow(cm, cmap="Blues")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set_title(str(title))
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_xticks(np.arange(len(labels)))
    ax.set_yticks(np.arange(len(labels)))
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    ax.set_yticklabels(labels, fontsize=8)
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, str(int(cm[i, j])), ha="center", va="center", fontsize=8, color="black")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=160)
    plt.close(fig)
    return True


def _r2_payload(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    yt = np.asarray(y_true, dtype=np.float64)
    yp = np.asarray(y_pred, dtype=np.float64)
    if yt.shape != yp.shape or yt.size == 0:
        return {"r2_mean": None, "r2_per_component": []}
    if yt.ndim == 1:
        yt = yt.reshape(-1, 1)
        yp = yp.reshape(-1, 1)
    per = []
    for j in range(int(yt.shape[1])):
        try:
            per.append(float(r2_score(yt[:, j], yp[:, j])))
        except Exception:
            per.append(float("nan"))
    finite = [v for v in per if np.isfinite(v)]
    mean = float(np.mean(finite)) if finite else float("nan")
    return {
        "r2_mean": (mean if np.isfinite(mean) else None),
        "r2_per_component": [float(v) if np.isfinite(v) else None for v in per],
    }


def fit_audio_pretrained_embedding_multitask(
    df: pd.DataFrame,
    out_dir: Path,
    *,
    task_mode: str = "multiclass",
    target_col: str = "primary_class",
    target_cols: Optional[Sequence[str]] = None,
    positive_threshold: float = 0.5,
    positive_label: str = "on",
    split_manifest_df: Optional[pd.DataFrame] = None,
    split_col: str = "split",
    dataset_id_col: str = "sample_id",
    split_manifest_id_col: str = "sample_id",
    audio_path_col: str = "segment_path",
    random_state: int = 42,
    target_seconds: float = 10.0,
    extract_batch_size: int = 16,
    extract_num_workers: int = 0,
    extract_log_every: int = 0,
    encoder_hidden: str = "512,256",
    encoder_dropout: float = 0.2,
    epochs: int = 40,
    batch_size: int = 128,
    learning_rate: float = 1e-3,
    weight_decay: float = 1e-4,
    eval_every: int = 5,
    aux_plc_pca: bool = True,
    aux_plc_feature_cols: Optional[Sequence[str]] = None,
    aux_plc_include_duty_cols: bool = False,
    aux_plc_components: int = 8,
    aux_plc_variance_ratio: float = 0.0,
    aux_plc_weight: float = 0.3,
    pann_pca_components: int = 8,
    pann_pca_variance_ratio: float = 0.0,
    pann_pca_weight: float = 1.0,
) -> AudioPretrainedEmbeddingMultitaskResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    mode = str(task_mode).strip().lower()
    if mode not in ("multiclass", "multilabel"):
        raise ValueError("task_mode must be one of: multiclass, multilabel")
    if mode == "multiclass":
        df0, y_raw, y_meta = _coerce_target(
            df,
            target_col=str(target_col),
            task="multiclass",
            positive_label=str(positive_label),
        )
        y_all = np.asarray(y_raw, dtype=np.int64)
    else:
        cols = list(target_cols or [])
        if not cols:
            cols = ["ropumprun_duty", "deliveryrun_duty"]
        y_raw, y_meta = _coerce_binary_targets(
            df,
            target_cols=cols,
            positive_threshold=float(positive_threshold),
            positive_label=str(positive_label),
        )
        df0 = df.copy()
        y_all = np.asarray(y_raw, dtype=np.float32)
    df1, split_ser, split_source = _attach_split_labels(
        df0,
        split_manifest_df=split_manifest_df,
        split_col=str(split_col),
        dataset_id_col=str(dataset_id_col),
        split_manifest_id_col=str(split_manifest_id_col),
    )
    if split_ser is None:
        raise ValueError("Need explicit split labels. Provide split manifest or split column.")
    split_norm = split_ser.map(_normalize_split_value).astype("string")
    keep_mask = split_norm.isin(["train", "test", "val"])
    if int(keep_mask.sum()) <= 0:
        raise ValueError("No rows mapped to train/test/val")

    df2 = df1.loc[keep_mask].reset_index(drop=True)
    if mode == "multiclass":
        Y = np.asarray(y_all[np.asarray(keep_mask.to_numpy(), dtype=bool)], dtype=np.int64)
    else:
        Y = np.asarray(y_all[np.asarray(keep_mask.to_numpy(), dtype=bool)], dtype=np.float32)
    split2 = split_norm.loc[keep_mask].reset_index(drop=True)
    path_ser = _coerce_audio_path_column(df2, str(audio_path_col))

    idx_all = np.arange(len(df2), dtype=np.int64)
    idx_train = idx_all[split2.to_numpy() == "train"]
    idx_test = idx_all[split2.to_numpy() == "test"]
    idx_val = idx_all[split2.to_numpy() == "val"]
    if len(idx_train) < 2 or len(idx_test) < 1:
        raise ValueError("Need non-empty train and test splits")

    src_col = next((c for c in ("audio_source", "source_name", "source") if c in df2.columns), None)
    src_series = (
        df2[src_col].astype("string").fillna("unknown")
        if src_col is not None
        else pd.Series(["unknown"] * len(df2), dtype="string")
    )

    backend = _PannsBackend(device="cuda")
    emb_cache = out_dir / "embeddings_panns.npz"
    if emb_cache.exists():
        z = np.load(str(emb_cache))
        X_emb = np.asarray(z["embeddings"], dtype=np.float32)
        print(f"[embed] cache hit -> {emb_cache} shape={tuple(X_emb.shape)}", flush=True)
    else:
        print(f"[embed] cache miss -> extracting {len(path_ser)} clips", flush=True)
        X_emb = _extract_embeddings(
            backend=backend,
            paths=path_ser.tolist(),
            batch_size=int(extract_batch_size),
            target_seconds=float(target_seconds),
            num_workers=int(extract_num_workers),
            log_every=int(extract_log_every),
        )
        np.savez_compressed(str(emb_cache), embeddings=X_emb)
        print(f"[embed] saved cache -> {emb_cache} shape={tuple(X_emb.shape)}", flush=True)

    Z_pann, pann_meta = _fit_pca_targets(
        X_emb,
        idx_train,
        n_components=int(pann_pca_components),
        variance_ratio=float(pann_pca_variance_ratio),
        random_state=int(random_state),
    )
    np.savez(
        str(out_dir / "pann_embedding_pca_model.npz"),
        mean=pann_meta["mean"],
        std=pann_meta["std"],
        components=pann_meta["components"],
        explained_variance=pann_meta["explained_variance"],
        explained_variance_ratio=pann_meta["explained_variance_ratio"],
    )

    Z_plc = None
    plc_meta: Dict[str, Any] = {"enabled": False}
    if bool(aux_plc_pca):
        plc_cols = _select_plc_feature_columns(
            df2,
            target_cols=(list(y_meta.get("target_cols") or []) if mode == "multilabel" else [str(target_col)]),
            split_col=str(split_col),
            dataset_id_col=str(dataset_id_col),
            split_manifest_id_col=str(split_manifest_id_col),
            explicit_cols=aux_plc_feature_cols,
            include_duty_cols=bool(aux_plc_include_duty_cols),
        )
        X_plc = df2[plc_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(dtype=np.float32)
        Z_plc, plc_fit_meta = _fit_pca_targets(
            X_plc,
            idx_train,
            n_components=int(aux_plc_components),
            variance_ratio=float(aux_plc_variance_ratio),
            random_state=int(random_state),
        )
        np.savez(
            str(out_dir / "plc_aux_pca_model.npz"),
            mean=plc_fit_meta["mean"],
            std=plc_fit_meta["std"],
            components=plc_fit_meta["components"],
            explained_variance=plc_fit_meta["explained_variance"],
            explained_variance_ratio=plc_fit_meta["explained_variance_ratio"],
            feature_cols=np.asarray(plc_cols, dtype=object),
        )
        plc_meta = {
            "enabled": True,
            "feature_cols": plc_cols,
            "n_features": int(len(plc_cols)),
            "n_components": int(plc_fit_meta["n_components"]),
            "variance_ratio_captured": float(plc_fit_meta["variance_ratio_captured"]),
            "weight": float(aux_plc_weight),
        }

    try:
        import torch  # type: ignore
        import torch.nn as nn  # type: ignore
        from torch.utils.data import DataLoader, TensorDataset  # type: ignore
    except Exception as e:
        raise RuntimeError("This trainer requires torch. Install: pip install torch") from e

    class _Model(nn.Module):
        def __init__(self, in_dim: int, hidden: List[int], z_dim: int, y_dim: int, plc_dim: int, drop: float):
            super().__init__()
            layers: List[nn.Module] = []
            d = int(in_dim)
            for h in hidden:
                layers.extend([nn.Linear(d, int(h)), nn.ReLU(), nn.Dropout(float(drop))])
                d = int(h)
            self.encoder = nn.Sequential(*layers) if layers else nn.Identity()
            self.z = nn.Linear(d, int(z_dim))
            self.cls = nn.Linear(int(z_dim), int(y_dim))
            self.plc = nn.Linear(int(z_dim), int(plc_dim)) if int(plc_dim) > 0 else None

        def forward(self, x):
            h = self.encoder(x)
            z = self.z(h)
            y = self.cls(z)
            p = self.plc(z) if self.plc is not None else None
            return y, z, p

    hidden = [int(x.strip()) for x in str(encoder_hidden).split(",") if x.strip()]
    z_dim = int(Z_pann.shape[1])
    plc_dim = int(Z_plc.shape[1]) if Z_plc is not None else 0
    y_dim = int(len(np.unique(Y))) if mode == "multiclass" else int(Y.shape[1])
    model = _Model(X_emb.shape[1], hidden, z_dim, y_dim, plc_dim, float(encoder_dropout))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    print(f"[device] embedding_multitask using {device}", flush=True)

    Xt = torch.from_numpy(np.asarray(X_emb, dtype=np.float32))
    if mode == "multiclass":
        Yt = torch.from_numpy(np.asarray(Y, dtype=np.int64))
    else:
        Yt = torch.from_numpy(np.asarray(Y, dtype=np.float32))
    Zpann_t = torch.from_numpy(np.asarray(Z_pann, dtype=np.float32))
    if Z_plc is not None:
        Zplc_t = torch.from_numpy(np.asarray(Z_plc, dtype=np.float32))
        ds_train = TensorDataset(Xt[idx_train], Yt[idx_train], Zpann_t[idx_train], Zplc_t[idx_train])
    else:
        ds_train = TensorDataset(Xt[idx_train], Yt[idx_train], Zpann_t[idx_train])
    ds_test = TensorDataset(Xt[idx_test], Yt[idx_test], Zpann_t[idx_test])
    ds_val = TensorDataset(Xt[idx_val], Yt[idx_val], Zpann_t[idx_val]) if len(idx_val) else TensorDataset(
        torch.zeros((0, Xt.shape[1])), torch.zeros((0, Yt.shape[1])), torch.zeros((0, Zpann_t.shape[1]))
    )
    train_dl = DataLoader(ds_train, batch_size=int(batch_size), shuffle=True)
    test_dl = DataLoader(ds_test, batch_size=int(batch_size), shuffle=False)
    val_dl = DataLoader(ds_val, batch_size=int(batch_size), shuffle=False)

    bce = nn.BCEWithLogitsLoss()
    ce = nn.CrossEntropyLoss()
    huber = nn.SmoothL1Loss()
    optim = torch.optim.AdamW(model.parameters(), lr=float(learning_rate), weight_decay=float(weight_decay))

    def _predict(dl):
        model.eval()
        y_true, y_pred = [], []
        with torch.no_grad():
            for xb, yb, _zb in dl:
                xb = xb.to(device)
                logits, _z, _p = model(xb)
                if mode == "multiclass":
                    yp = torch.argmax(logits, dim=1).long()
                    y_true.append(yb.numpy().astype(np.int64))
                    y_pred.append(yp.cpu().numpy().astype(np.int64))
                else:
                    yp = (torch.sigmoid(logits) >= 0.5).float()
                    y_true.append(yb.numpy())
                    y_pred.append(yp.cpu().numpy())
        if not y_true:
            if mode == "multiclass":
                return np.zeros((0,), dtype=np.int64), np.zeros((0,), dtype=np.int64)
            return np.zeros((0, Y.shape[1]), dtype=np.float32), np.zeros((0, Y.shape[1]), dtype=np.float32)
        return np.concatenate(y_true, axis=0), np.concatenate(y_pred, axis=0)

    history: List[Dict[str, Any]] = []
    n_epochs = int(epochs)
    eval_every = max(1, int(eval_every))
    for ep in range(1, n_epochs + 1):
        model.train()
        loss_sum = 0.0
        n_rows = 0
        for batch in train_dl:
            if len(batch) == 4:
                xb, yb, zpb, zlb = batch
                zlb = zlb.to(device)
            else:
                xb, yb, zpb = batch
                zlb = None
            xb = xb.to(device)
            yb = yb.to(device)
            zpb = zpb.to(device)
            optim.zero_grad(set_to_none=True)
            logits, zhat, plc_pred = model(xb)
            if mode == "multiclass":
                l_cls = ce(logits, yb.long())
            else:
                l_cls = bce(logits, yb)
            l_pann = huber(zhat, zpb)
            if zlb is not None and plc_pred is not None:
                l_plc = huber(plc_pred, zlb)
            else:
                l_plc = torch.tensor(0.0, device=device)
            loss = l_cls + float(pann_pca_weight) * l_pann + float(aux_plc_weight) * l_plc
            loss.backward()
            optim.step()
            bsz = int(yb.shape[0])
            loss_sum += float(loss.detach().cpu().item()) * bsz
            n_rows += bsz

        avg_loss = float(loss_sum / max(1, n_rows))
        test_metric = None
        if ep % eval_every == 0 or ep == n_epochs:
            yt, yp = _predict(test_dl)
            if mode == "multiclass":
                test_metric = float(np.mean(yt == yp)) if len(yt) else 0.0
            else:
                test_metric = float(np.mean(np.all(yt == yp, axis=1))) if len(yt) else 0.0
        history.append(
            {
                "epoch": int(ep),
                "loss": avg_loss,
                "test_metric": test_metric,
                "lr": float(optim.param_groups[0]["lr"]),
            }
        )
        ttxt = "NA" if test_metric is None else f"{test_metric:.4f}"
        metric_name = "test_acc" if mode == "multiclass" else "test_exact_match"
        print(f"[epoch {ep:03d}/{n_epochs}] loss={avg_loss:.6f} {metric_name}={ttxt} lr={float(optim.param_groups[0]['lr']):.6g}", flush=True)

    ytr_t, ytr_p = _predict(DataLoader(TensorDataset(Xt[idx_train], Yt[idx_train], Zpann_t[idx_train]), batch_size=int(batch_size)))
    yte_t, yte_p = _predict(test_dl)
    yva_t, yva_p = _predict(val_dl) if len(idx_val) else (np.zeros((0, Y.shape[1])), np.zeros((0, Y.shape[1])))

    # Export PANN-PCA true vs inferred embeddings (PC1/PC2) for visualization.
    model.eval()
    z_pred_parts: List[np.ndarray] = []
    plc_pred_parts: List[np.ndarray] = []
    with torch.no_grad():
        for i0 in range(0, Xt.shape[0], int(batch_size)):
            i1 = min(int(Xt.shape[0]), i0 + int(batch_size))
            xb = Xt[i0:i1].to(device)
            _logits, zhat, plc_hat = model(xb)
            z_pred_parts.append(zhat.cpu().numpy().astype(np.float32, copy=False))
            if plc_hat is not None:
                plc_pred_parts.append(plc_hat.cpu().numpy().astype(np.float32, copy=False))
    Z_pann_pred = np.concatenate(z_pred_parts, axis=0) if z_pred_parts else np.zeros_like(Z_pann)
    Z_plc_pred = np.concatenate(plc_pred_parts, axis=0) if plc_pred_parts else None

    pann_proj_path = out_dir / "pann_pca_true_vs_pred.parquet"
    pann_proj_df = df2.reset_index(drop=True).copy()
    pann_proj_df["split"] = split2.reset_index(drop=True)
    for j in range(int(Z_pann.shape[1])):
        jj = int(j + 1)
        pann_proj_df[f"pann_true_pc{jj}"] = Z_pann[:, j].astype("float64")
        pann_proj_df[f"pann_pred_pc{jj}"] = Z_pann_pred[:, j].astype("float64")
    pann_proj_df.to_parquet(pann_proj_path, index=False)

    pann_plot_path: Optional[Path] = None
    pann_plot_multicolor_path: Optional[Path] = None
    if int(Z_pann.shape[1]) >= 2:
        try:
            import matplotlib.pyplot as plt  # type: ignore

            fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.4), constrained_layout=True)
            src_vals = src_series.astype(str).fillna("unknown").to_numpy()
            src_labels = sorted(set(src_vals.tolist()))
            palette = plt.cm.tab20(np.linspace(0.0, 1.0, max(1, len(src_labels))))
            src_color = {lab: palette[i] for i, lab in enumerate(src_labels)}

            for lab in src_labels:
                m = src_vals == lab
                if int(np.sum(m)) <= 0:
                    continue
                axes[0].scatter(
                    Z_pann[m, 0],
                    Z_pann[m, 1],
                    s=8,
                    alpha=0.4,
                    c=[src_color[lab]],
                    label=str(lab),
                )
            axes[0].set_title("PANN PCA True (PC1 vs PC2)")
            axes[0].set_xlabel("true_pc1")
            axes[0].set_ylabel("true_pc2")
            axes[0].grid(alpha=0.2)

            for lab in src_labels:
                m = src_vals == lab
                if int(np.sum(m)) <= 0:
                    continue
                axes[1].scatter(
                    Z_pann_pred[m, 0],
                    Z_pann_pred[m, 1],
                    s=8,
                    alpha=0.4,
                    c=[src_color[lab]],
                    label=str(lab),
                )
            axes[1].set_title("PANN PCA Pred (PC1 vs PC2)")
            axes[1].set_xlabel("pred_pc1")
            axes[1].set_ylabel("pred_pc2")
            axes[1].grid(alpha=0.2)
            axes[1].legend(fontsize=8, loc="best")

            pann_plot_path = out_dir / "pann_pca_true_vs_pred_pc12.png"
            fig.savefig(pann_plot_path, dpi=160)
            plt.close(fig)

            # Additional grid with different color modes: source/state/duties.
            color_specs: List[Tuple[str, str, str]] = []
            color_specs.append(("source", "__source__", "categorical"))
            state_col = next(
                (c for c in ("state_mode", "primary_class", "state", "mode") if c in pann_proj_df.columns),
                None,
            )
            if state_col is not None:
                color_specs.append(("state", str(state_col), "categorical"))
            if "ropumprun_duty" in pann_proj_df.columns:
                color_specs.append(("ropumprun_duty", "ropumprun_duty", "numeric"))
            if "deliveryrun_duty" in pann_proj_df.columns:
                color_specs.append(("deliveryrun_duty", "deliveryrun_duty", "numeric"))

            ncols = max(1, int(len(color_specs)))
            fig2, axes2 = plt.subplots(2, ncols, figsize=(4.8 * ncols, 8.0), constrained_layout=True)
            if ncols == 1:
                axes2 = np.asarray(axes2).reshape(2, 1)

            def _plot_panel(ax, *, x: np.ndarray, y: np.ndarray, spec: Tuple[str, str, str], title_prefix: str) -> None:
                label, col, mode = spec
                if col == "__source__":
                    s = src_series.astype(str).fillna("unknown")
                else:
                    s = pann_proj_df[col]

                if mode == "categorical":
                    cats = s.astype(str).fillna("unknown")
                    labs = sorted(cats.unique().tolist())
                    pal = plt.cm.tab20(np.linspace(0.0, 1.0, max(1, len(labs))))
                    cmap = {lab: pal[i] for i, lab in enumerate(labs)}
                    for lab in labs:
                        m = (cats.to_numpy() == lab)
                        if int(np.sum(m)) <= 0:
                            continue
                        ax.scatter(x[m], y[m], s=8, alpha=0.4, c=[cmap[lab]], label=str(lab))
                    if len(labs) <= 12:
                        ax.legend(fontsize=7, loc="best")
                else:
                    v = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
                    finite = np.isfinite(v)
                    if finite.any():
                        lo = float(np.nanquantile(v[finite], 0.01))
                        hi = float(np.nanquantile(v[finite], 0.99))
                        if hi <= lo:
                            lo = float(np.nanmin(v[finite]))
                            hi = float(np.nanmax(v[finite]) + 1e-9)
                        vv = np.clip(v, lo, hi)
                        sc = ax.scatter(x, y, c=vv, s=8, alpha=0.45, cmap="viridis", vmin=lo, vmax=hi)
                        cb = fig2.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
                        cb.ax.tick_params(labelsize=7)
                    else:
                        ax.scatter(x, y, s=8, alpha=0.35, c="#777777")
                ax.set_title(f"{title_prefix} colored by {label}")
                ax.grid(alpha=0.2)

            for j, spec in enumerate(color_specs):
                ax_t = axes2[0, j]
                ax_p = axes2[1, j]
                _plot_panel(ax_t, x=Z_pann[:, 0], y=Z_pann[:, 1], spec=spec, title_prefix="True")
                _plot_panel(ax_p, x=Z_pann_pred[:, 0], y=Z_pann_pred[:, 1], spec=spec, title_prefix="Pred")
                ax_t.set_xlabel("true_pc1")
                ax_t.set_ylabel("true_pc2")
                ax_p.set_xlabel("pred_pc1")
                ax_p.set_ylabel("pred_pc2")

            pann_plot_multicolor_path = out_dir / "pann_pca_true_vs_pred_pc12_multicolor.png"
            fig2.savefig(pann_plot_multicolor_path, dpi=160)
            plt.close(fig2)
        except Exception:
            pann_plot_path = None
            pann_plot_multicolor_path = None

    def _split_metrics(yt: np.ndarray, yp: np.ndarray) -> Dict[str, Any]:
        if len(yt) <= 0:
            return {}
        if mode == "multiclass":
            acc = float(np.mean(yt == yp))
            return {
                "accuracy": acc,
                "f1_macro": float(f1_score(yt, yp, average="macro", zero_division=0)),
                "precision_macro": float(precision_score(yt, yp, average="macro", zero_division=0)),
                "recall_macro": float(recall_score(yt, yp, average="macro", zero_division=0)),
                "n_rows": int(len(yt)),
            }
        exact = float(np.mean(np.all(yt == yp, axis=1)))
        per_target = {}
        for j, c in enumerate(y_meta["target_cols"]):
            per_target[str(c)] = {"accuracy": float(np.mean(yt[:, j] == yp[:, j]))}
        return {"exact_match": exact, "per_target": per_target, "n_rows": int(len(yt))}

    by_source_test: Dict[str, Any] = {}
    if len(idx_test) > 0:
        src = src_series.iloc[idx_test].astype(str).fillna("unknown").to_numpy()
        for s in sorted(set(src.tolist())):
            m = src == s
            if int(np.sum(m)) <= 0:
                continue
            by_source_test[str(s)] = _split_metrics(yte_t[m], yte_p[m])

    if mode == "multiclass":
        class_labels = list(y_meta.get("classes") or [])
        label_ids = list(range(len(class_labels)))
        def _cm_mc(yt, yp):
            if len(yt) <= 0:
                return {"labels": class_labels, "matrix": [], "n_rows": 0}
            cm = confusion_matrix(yt, yp, labels=label_ids)
            return {"labels": class_labels, "matrix": cm.tolist(), "n_rows": int(len(yt))}
        confusion_by_split = {
            "train": _cm_mc(ytr_t, ytr_p),
            "test": _cm_mc(yte_t, yte_p),
            "val": (_cm_mc(yva_t, yva_p) if len(idx_val) else {}),
        }
    else:
        confusion_by_split = {
            "train": _build_confusion_payload(ytr_t, ytr_p, target_cols=y_meta["target_cols"]),
            "test": _build_confusion_payload(yte_t, yte_p, target_cols=y_meta["target_cols"]),
            "val": (_build_confusion_payload(yva_t, yva_p, target_cols=y_meta["target_cols"]) if len(idx_val) else {}),
        }
    confusion_by_source_test: Dict[str, Any] = {}
    if len(idx_test) > 0:
        src = src_series.iloc[idx_test].astype(str).fillna("unknown").to_numpy()
        for s in sorted(set(src.tolist())):
            m = src == s
            if int(np.sum(m)) <= 0:
                continue
            if mode == "multiclass":
                class_labels = list(y_meta.get("classes") or [])
                label_ids = list(range(len(class_labels)))
                cm = confusion_matrix(yte_t[m], yte_p[m], labels=label_ids)
                confusion_by_source_test[str(s)] = {
                    "labels": class_labels,
                    "matrix": cm.tolist(),
                    "n_rows": int(np.sum(m)),
                }
            else:
                confusion_by_source_test[str(s)] = _build_confusion_payload(
                    yte_t[m], yte_p[m], target_cols=y_meta["target_cols"]
                )

    conf_artifacts: Dict[str, Any] = {}
    conf_dir = out_dir / "confusion_multitask"
    test_conf = confusion_by_split.get("test") or {}
    if test_conf.get("labels"):
        out_png = conf_dir / "confusion_test_multiclass_exact.png"
        if _plot_confusion_png(
            labels=list(test_conf["labels"]),
            matrix=list(test_conf["matrix"]),
            title=("Test Confusion (multiclass)" if mode == "multiclass" else "Test Confusion (2-hot exact class)"),
            out_png=out_png,
        ):
            conf_artifacts["test_multiclass_exact_png"] = str(out_png)
    by_src_png: Dict[str, str] = {}
    for src_name, node in confusion_by_source_test.items():
        if not node.get("labels"):
            continue
        out_png = conf_dir / f"confusion_test_source_{src_name}.png"
        if _plot_confusion_png(
            labels=list(node["labels"]),
            matrix=list(node["matrix"]),
            title=f"Test Confusion (source={src_name})",
            out_png=out_png,
        ):
            by_src_png[str(src_name)] = str(out_png)
    if by_src_png:
        conf_artifacts["test_by_source_multiclass_exact_png"] = by_src_png

    model_path = out_dir / "audio_pretrained_embedding_multitask.pt"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "task_mode": str(mode),
            "input_dim": int(X_emb.shape[1]),
            "hidden": hidden,
            "z_dim": int(z_dim),
            "n_targets": (int(y_dim) if mode == "multiclass" else int(Y.shape[1])),
            "target_col": (str(target_col) if mode == "multiclass" else None),
            "target_cols": (list(y_meta.get("target_cols") or []) if mode == "multilabel" else None),
            "class_names": (list(y_meta.get("classes") or []) if mode == "multiclass" else None),
            "pann_pca_weight": float(pann_pca_weight),
            "aux_plc_weight": float(aux_plc_weight),
        },
        str(model_path),
    )

    metrics = {
        "task": ("multitask_multiclass" if mode == "multiclass" else "multitask_2hot"),
        "target_meta": y_meta,
        "backend": "panns_embeddings",
        "split_source": split_source,
        "n_rows": int(len(df2)),
        "n_train": int(len(idx_train)),
        "n_test": int(len(idx_test)),
        "n_val": int(len(idx_val)),
        "pann_pca": {
            "n_components": int(pann_meta["n_components"]),
            "variance_ratio_captured": float(pann_meta["variance_ratio_captured"]),
            "weight": float(pann_pca_weight),
        },
        "aux_plc_pca": plc_meta,
        "pca_alignment_metrics": {
            "pann_pca": _r2_payload(Z_pann, Z_pann_pred),
            "plc_pca": (_r2_payload(Z_plc, Z_plc_pred) if (Z_plc is not None and Z_plc_pred is not None) else None),
        },
        "train_metrics": _split_metrics(ytr_t, ytr_p),
        "test_metrics": _split_metrics(yte_t, yte_p),
        "val_metrics": _split_metrics(yva_t, yva_p) if len(idx_val) else {},
        "metrics_by_source": {"test": by_source_test},
        "confusion_by_split": confusion_by_split,
        "confusion_by_source": {"test": confusion_by_source_test},
        "epoch_history": history,
        "train_params": {
            "epochs": int(epochs),
            "batch_size": int(batch_size),
            "learning_rate": float(learning_rate),
            "weight_decay": float(weight_decay),
            "encoder_hidden": hidden,
            "encoder_dropout": float(encoder_dropout),
            "eval_every": int(eval_every),
        },
        "artifacts": {
            "model_path": str(model_path),
            "embedding_cache": str(emb_cache),
            "pann_pca_model": str(out_dir / "pann_embedding_pca_model.npz"),
            "plc_aux_pca_model": (str(out_dir / "plc_aux_pca_model.npz") if bool(aux_plc_pca) else None),
            "pann_true_vs_pred_parquet": str(pann_proj_path),
            "pann_true_vs_pred_plot_pc12": (str(pann_plot_path) if pann_plot_path is not None else None),
            "pann_true_vs_pred_plot_pc12_multicolor": (
                str(pann_plot_multicolor_path) if pann_plot_multicolor_path is not None else None
            ),
            "confusion": conf_artifacts,
        },
    }
    metrics_path = out_dir / "audio_pretrained_embedding_multitask_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return AudioPretrainedEmbeddingMultitaskResult(out_dir=out_dir, metrics_path=metrics_path, model_path=model_path)
