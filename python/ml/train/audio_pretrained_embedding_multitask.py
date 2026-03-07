from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .audio_pca_svm import _attach_split_labels, _normalize_split_value
from .audio_pretrained_embeddings import _PannsBackend, _coerce_audio_path_column, _extract_embeddings

try:
    from sklearn.decomposition import PCA
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


def fit_audio_pretrained_embedding_multitask(
    df: pd.DataFrame,
    out_dir: Path,
    *,
    target_cols: Sequence[str],
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
    y_bin, y_meta = _coerce_binary_targets(
        df,
        target_cols=target_cols,
        positive_threshold=float(positive_threshold),
        positive_label=str(positive_label),
    )
    df1, split_ser, split_source = _attach_split_labels(
        df,
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
    Y = np.asarray(y_bin[np.asarray(keep_mask.to_numpy(), dtype=bool)], dtype=np.float32)
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
            target_cols=list(target_cols),
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
    model = _Model(X_emb.shape[1], hidden, z_dim, Y.shape[1], plc_dim, float(encoder_dropout))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    print(f"[device] embedding_multitask using {device}", flush=True)

    Xt = torch.from_numpy(np.asarray(X_emb, dtype=np.float32))
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
    huber = nn.SmoothL1Loss()
    optim = torch.optim.AdamW(model.parameters(), lr=float(learning_rate), weight_decay=float(weight_decay))

    def _predict(dl):
        model.eval()
        y_true, y_pred = [], []
        with torch.no_grad():
            for xb, yb, _zb in dl:
                xb = xb.to(device)
                logits, _z, _p = model(xb)
                yp = (torch.sigmoid(logits) >= 0.5).float()
                y_true.append(yb.numpy())
                y_pred.append(yp.cpu().numpy())
        if not y_true:
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
        test_exact = None
        if ep % eval_every == 0 or ep == n_epochs:
            yt, yp = _predict(test_dl)
            test_exact = float(np.mean(np.all(yt == yp, axis=1))) if len(yt) else 0.0
        history.append(
            {
                "epoch": int(ep),
                "loss": avg_loss,
                "test_exact_match": test_exact,
                "lr": float(optim.param_groups[0]["lr"]),
            }
        )
        ttxt = "NA" if test_exact is None else f"{test_exact:.4f}"
        print(f"[epoch {ep:03d}/{n_epochs}] loss={avg_loss:.6f} test_exact_match={ttxt} lr={float(optim.param_groups[0]['lr']):.6g}", flush=True)

    ytr_t, ytr_p = _predict(DataLoader(TensorDataset(Xt[idx_train], Yt[idx_train], Zpann_t[idx_train]), batch_size=int(batch_size)))
    yte_t, yte_p = _predict(test_dl)
    yva_t, yva_p = _predict(val_dl) if len(idx_val) else (np.zeros((0, Y.shape[1])), np.zeros((0, Y.shape[1])))

    def _split_metrics(yt: np.ndarray, yp: np.ndarray) -> Dict[str, Any]:
        if len(yt) <= 0:
            return {}
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

    model_path = out_dir / "audio_pretrained_embedding_multitask.pt"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "input_dim": int(X_emb.shape[1]),
            "hidden": hidden,
            "z_dim": int(z_dim),
            "n_targets": int(Y.shape[1]),
            "target_cols": list(y_meta["target_cols"]),
            "pann_pca_weight": float(pann_pca_weight),
            "aux_plc_weight": float(aux_plc_weight),
        },
        str(model_path),
    )

    metrics = {
        "task": "multitask_2hot",
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
        "train_metrics": _split_metrics(ytr_t, ytr_p),
        "test_metrics": _split_metrics(yte_t, yte_p),
        "val_metrics": _split_metrics(yva_t, yva_p) if len(idx_val) else {},
        "metrics_by_source": {"test": by_source_test},
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
        },
    }
    metrics_path = out_dir / "audio_pretrained_embedding_multitask_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return AudioPretrainedEmbeddingMultitaskResult(out_dir=out_dir, metrics_path=metrics_path, model_path=model_path)
