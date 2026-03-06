from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .audio_pca_svm import _attach_split_labels, _coerce_target, _normalize_split_value

try:
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler
except Exception as e:
    raise SystemExit("Missing scikit-learn. Install: pip install scikit-learn") from e


@dataclass(frozen=True)
class AudioPretrainedEmbeddingResult:
    out_dir: Path
    metrics_path: Path
    frozen_head_path: Path
    finetuned_head_path: Optional[Path]


class _PannsBackend:
    """
    PANNs backend via `panns_inference`.

    Notes:
    - Frozen-embedding stage is robust and uses AudioTagging.inference().
    - Partial fine-tune stage relies on access to `AudioTagging.model` and may vary
      by panns_inference version. We fail fast with clear errors when unsupported.
    """

    def __init__(self, *, device: str = "cuda") -> None:
        try:
            from panns_inference import AudioTagging  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "PANNs backend requires panns_inference. Install: pip install panns-inference"
            ) from e

        self.sample_rate = 32000
        self._tagger = AudioTagging(checkpoint_path=None, device=device)
        self._model = getattr(self._tagger, "model", None)

    def extract_embedding_np(self, waveform_batch: np.ndarray) -> np.ndarray:
        clipwise, embedding = self._tagger.inference(waveform_batch)
        _ = clipwise
        emb = np.asarray(embedding, dtype=np.float32)
        if emb.ndim > 2:
            emb = emb.reshape(emb.shape[0], -1)
        return emb

    def supports_finetune(self) -> bool:
        return self._model is not None

    def model_for_finetune(self):
        if self._model is None:
            raise RuntimeError("PANNs fine-tune unavailable: missing AudioTagging.model")
        return self._model


class _WaveDataset:
    def __init__(
        self,
        paths: Sequence[str],
        labels: np.ndarray,
        *,
        target_sr: int,
        target_seconds: float,
    ) -> None:
        self.paths = [str(p) for p in paths]
        self.labels = np.asarray(labels)
        self.target_sr = int(target_sr)
        self.target_seconds = float(target_seconds)

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, idx: int) -> Tuple[np.ndarray, np.ndarray]:
        w = _load_waveform(
            Path(self.paths[idx]),
            target_sr=int(self.target_sr),
            target_seconds=float(self.target_seconds),
        )
        y = self.labels[idx]
        return w.astype(np.float32, copy=False), np.asarray(y)


def _load_waveform(path: Path, *, target_sr: int, target_seconds: float) -> np.ndarray:
    try:
        from scipy import signal  # type: ignore
        from scipy.io import wavfile  # type: ignore
    except Exception as e:
        raise RuntimeError("Missing scipy for audio loading. Install: pip install scipy") from e

    sr, y = wavfile.read(str(path))
    y = np.asarray(y)
    if y.ndim == 2:
        y = y.mean(axis=1)

    if np.issubdtype(y.dtype, np.integer):
        max_val = float(np.iinfo(y.dtype).max)
        if max_val <= 0:
            max_val = 1.0
        y = y.astype(np.float32) / max_val
    else:
        y = y.astype(np.float32)

    if int(sr) != int(target_sr):
        y = signal.resample_poly(y, int(target_sr), int(sr)).astype(np.float32, copy=False)

    n_target = int(round(float(target_seconds) * int(target_sr)))
    if n_target <= 0:
        return y
    if len(y) < n_target:
        out = np.zeros((n_target,), dtype=np.float32)
        out[: len(y)] = y
        y = out
    elif len(y) > n_target:
        y = y[:n_target]
    return y.astype(np.float32, copy=False)


def _metrics_dict(y_true: np.ndarray, y_pred: np.ndarray, *, task: str) -> Dict[str, Any]:
    avg = "binary" if task == "binary" else "macro"
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1": float(f1_score(y_true, y_pred, average=avg, zero_division=0)),
        "precision": float(precision_score(y_true, y_pred, average=avg, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, average=avg, zero_division=0)),
    }


def _metrics_by_source(
    *,
    y_true_all: np.ndarray,
    y_pred_all: np.ndarray,
    source_all: pd.Series,
    idx: np.ndarray,
    task: str,
    labels: Optional[List[int]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if len(idx) == 0:
        return out
    src = source_all.iloc[idx].astype(str).fillna("unknown")
    for s in sorted(src.unique().tolist()):
        m = src.to_numpy() == s
        if not np.any(m):
            continue
        yt = np.asarray(y_true_all[idx][m], dtype=np.int64)
        yp = np.asarray(y_pred_all[idx][m], dtype=np.int64)
        mm = _metrics_dict(yt, yp, task=task)
        mm["n_rows"] = int(np.sum(m))
        mm["confusion_matrix"] = confusion_matrix(yt, yp, labels=labels).tolist() if labels else confusion_matrix(yt, yp).tolist()
        out[str(s)] = mm
    return out


def _extract_embeddings(
    *,
    backend: _PannsBackend,
    paths: Sequence[str],
    batch_size: int,
    target_seconds: float,
    num_workers: int = 0,
    log_every: int = 0,
) -> np.ndarray:
    out_chunks: List[np.ndarray] = []
    n_total = int(len(paths))
    if n_total <= 0:
        raise ValueError("No paths provided for embedding extraction")
    bsz = max(1, int(batch_size))
    n_batches = int(math.ceil(n_total / float(bsz)))
    nw = max(0, int(num_workers))
    log_n = max(0, int(log_every))

    def _load_one(p: str) -> np.ndarray:
        return _load_waveform(Path(p), target_sr=backend.sample_rate, target_seconds=float(target_seconds))

    if nw <= 1:
        for bi in range(n_batches):
            i0 = bi * bsz
            i1 = min(n_total, i0 + bsz)
            batch_paths = paths[i0:i1]
            waves = [_load_one(p) for p in batch_paths]
            wb = np.stack(waves, axis=0).astype(np.float32, copy=False)
            out_chunks.append(backend.extract_embedding_np(wb))
            done = int(i1)
            if log_n > 0 and (done % log_n == 0 or done == n_total):
                print(f"[embed] extracted {done}/{n_total} clips", flush=True)
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=nw) as ex:
            for bi in range(n_batches):
                i0 = bi * bsz
                i1 = min(n_total, i0 + bsz)
                batch_paths = paths[i0:i1]
                waves = list(ex.map(_load_one, batch_paths))
                wb = np.stack(waves, axis=0).astype(np.float32, copy=False)
                out_chunks.append(backend.extract_embedding_np(wb))
                done = int(i1)
                if log_n > 0 and (done % log_n == 0 or done == n_total):
                    print(f"[embed] extracted {done}/{n_total} clips workers={nw}", flush=True)

    if not out_chunks:
        raise ValueError("No embeddings extracted. Verify audio paths.")
    emb = np.concatenate(out_chunks, axis=0)
    if emb.ndim != 2:
        emb = emb.reshape(emb.shape[0], -1)
    return emb.astype(np.float32, copy=False)


def _unfreeze_last_n_modules(model, n_modules: int) -> List[str]:
    names: List[str] = []
    for _, p in model.named_parameters():
        p.requires_grad = False

    children = list(model.named_children())
    if children:
        use = children[-max(1, int(n_modules)) :]
        for name, mod in use:
            names.append(str(name))
            for p in mod.parameters():
                p.requires_grad = True
        return names

    params = list(model.named_parameters())
    use = params[-max(1, int(n_modules)) :]
    for name, p in use:
        names.append(str(name))
        p.requires_grad = True
    return names


def _coerce_audio_path_column(df: pd.DataFrame, audio_path_col: str) -> pd.Series:
    c = str(audio_path_col).strip()
    if c and c in df.columns:
        s = df[c].astype("string")
    else:
        fallback = next((k for k in ("segment_path", "audio_path", "wav_path", "path") if k in df.columns), None)
        if fallback is None:
            raise ValueError(
                "No audio path column found. Pass --audio-path-col and ensure dataset has path strings."
            )
        s = df[fallback].astype("string")
    mask = s.notna() & (s.astype(str).str.len() > 0)
    if int(mask.sum()) <= 0:
        raise ValueError("No non-empty audio paths in dataset")
    return s.astype(str)


def fit_audio_pretrained_embedding_experiment(
    df: pd.DataFrame,
    out_dir: Path,
    *,
    backend_name: str = "panns",
    target_col: str = "primary_class",
    task: str = "multiclass",
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
    frozen_hidden_sizes: str = "256,128",
    frozen_max_iter: int = 200,
    frozen_alpha: float = 1e-4,
    run_partial_finetune: bool = True,
    finetune_epochs: int = 5,
    finetune_batch_size: int = 8,
    finetune_num_workers: int = 0,
    finetune_lr_head: float = 1e-3,
    finetune_lr_backbone: float = 1e-5,
    finetune_unfreeze_modules: int = 1,
    finetune_amp: bool = True,
) -> AudioPretrainedEmbeddingResult:
    out_dir.mkdir(parents=True, exist_ok=True)

    df0, y, y_meta = _coerce_target(df, target_col=target_col, task=task, positive_label=positive_label)
    df1, split_ser, split_source = _attach_split_labels(
        df0,
        split_manifest_df=split_manifest_df,
        split_col=str(split_col),
        dataset_id_col=str(dataset_id_col),
        split_manifest_id_col=str(split_manifest_id_col),
    )
    if split_ser is None:
        raise ValueError("Harness requires explicit split labels (train/test/val). Provide --split-manifest or split column.")

    split_norm = split_ser.map(_normalize_split_value).astype("string")
    keep_mask = split_norm.isin(["train", "test", "val"])
    if int(keep_mask.sum()) <= 0:
        raise ValueError("No rows mapped to train/test/val")

    df2 = df1.loc[keep_mask].reset_index(drop=True)
    y2 = np.asarray(y[np.asarray(keep_mask.to_numpy(), dtype=bool)])
    split2 = split_norm.loc[keep_mask].reset_index(drop=True)

    path_ser = _coerce_audio_path_column(df2, audio_path_col)
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

    backend_key = str(backend_name).strip().lower()
    if backend_key != "panns":
        raise ValueError("Only backend='panns' is implemented in this harness version")
    backend = _PannsBackend(device="cuda")
    print(
        f"[backend] panns sample_rate={backend.sample_rate} "
        f"extract_batch_size={int(extract_batch_size)} extract_num_workers={int(extract_num_workers)}",
        flush=True,
    )

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

    h = [int(x.strip()) for x in str(frozen_hidden_sizes).split(",") if x.strip()]
    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X_emb[idx_train])
    X_te = scaler.transform(X_emb[idx_test])
    X_va = scaler.transform(X_emb[idx_val]) if len(idx_val) else np.zeros((0, X_emb.shape[1]), dtype=np.float32)

    clf = MLPClassifier(
        hidden_layer_sizes=tuple(h) if h else (256, 128),
        activation="relu",
        alpha=float(frozen_alpha),
        max_iter=int(frozen_max_iter),
        random_state=int(random_state),
        early_stopping=True,
        n_iter_no_change=10,
        validation_fraction=0.1,
    )
    clf.fit(X_tr, y2[idx_train])

    y_pred_all = np.zeros((len(df2),), dtype=np.int64)
    y_pred_all[idx_train] = clf.predict(X_tr)
    y_pred_all[idx_test] = clf.predict(X_te)
    if len(idx_val):
        y_pred_all[idx_val] = clf.predict(X_va)

    labels = sorted(np.unique(y2).astype(int).tolist())
    frozen_metrics = {
        "train": _metrics_dict(y2[idx_train], y_pred_all[idx_train], task=task),
        "test": _metrics_dict(y2[idx_test], y_pred_all[idx_test], task=task),
        "val": _metrics_dict(y2[idx_val], y_pred_all[idx_val], task=task) if len(idx_val) else {},
        "by_source": {
            "train": _metrics_by_source(
                y_true_all=y2,
                y_pred_all=y_pred_all,
                source_all=src_series,
                idx=idx_train,
                task=task,
                labels=labels,
            ),
            "test": _metrics_by_source(
                y_true_all=y2,
                y_pred_all=y_pred_all,
                source_all=src_series,
                idx=idx_test,
                task=task,
                labels=labels,
            ),
            "val": _metrics_by_source(
                y_true_all=y2,
                y_pred_all=y_pred_all,
                source_all=src_series,
                idx=idx_val,
                task=task,
                labels=labels,
            )
            if len(idx_val)
            else {},
        },
    }

    frozen_head_path = out_dir / "frozen_mlp_head.joblib"
    try:
        import joblib  # type: ignore

        joblib.dump(
            {
                "scaler": scaler,
                "classifier": clf,
                "task": task,
                "target_col": target_col,
                "y_meta": y_meta,
                "backend": "panns",
                "emb_cache": str(emb_cache),
            },
            str(frozen_head_path),
        )
    except Exception as e:
        raise RuntimeError("Failed to save frozen head artifact") from e

    finetuned_head_path: Optional[Path] = None
    finetune_metrics: Dict[str, Any] = {"status": "skipped"}

    if bool(run_partial_finetune):
        if not backend.supports_finetune():
            finetune_metrics = {
                "status": "unavailable",
                "reason": "PANNs wrapper does not expose trainable model in this environment.",
            }
        else:
            try:
                import torch  # type: ignore
                import torch.nn as nn  # type: ignore
                from torch.utils.data import DataLoader, Dataset  # type: ignore
            except Exception as e:
                raise RuntimeError("Partial fine-tune requires torch. Install: pip install torch") from e

            class _TorchWaveDataset(Dataset):
                def __init__(self, base_ds: _WaveDataset):
                    self.base = base_ds

                def __len__(self):
                    return len(self.base)

                def __getitem__(self, idx: int):
                    x, yv = self.base[idx]
                    return torch.from_numpy(x), torch.tensor(yv, dtype=torch.long)

            model_backbone = backend.model_for_finetune()
            model_backbone.train()
            unfrozen = _unfreeze_last_n_modules(model_backbone, int(finetune_unfreeze_modules))

            # Probe embedding dim.
            with torch.no_grad():
                dummy = torch.zeros((1, int(round(float(target_seconds) * backend.sample_rate))), dtype=torch.float32)
                out_probe = model_backbone(dummy)
                if isinstance(out_probe, dict):
                    emb_probe = out_probe.get("embedding", None)
                elif isinstance(out_probe, (tuple, list)) and len(out_probe) >= 2:
                    emb_probe = out_probe[1]
                else:
                    emb_probe = None
                if emb_probe is None:
                    raise RuntimeError(
                        "Could not obtain embedding tensor from PANNs model output for fine-tune."
                    )
                if emb_probe.ndim > 2:
                    emb_probe = emb_probe.reshape(emb_probe.shape[0], -1)
                emb_dim = int(emb_probe.shape[1])

            n_classes = int(len(np.unique(y2)))
            head = nn.Linear(emb_dim, n_classes)

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            model_backbone = model_backbone.to(device)
            head = head.to(device)
            use_amp = bool(finetune_amp) and (device.type == "cuda")
            scaler = torch.cuda.amp.GradScaler(enabled=use_amp)
            print(
                f"[finetune] device={device} amp={use_amp} "
                f"batch_size={int(finetune_batch_size)} num_workers={int(finetune_num_workers)}",
                flush=True,
            )

            train_ds = _WaveDataset(
                [path_ser.iloc[i] for i in idx_train],
                y2[idx_train],
                target_sr=backend.sample_rate,
                target_seconds=float(target_seconds),
            )
            test_ds = _WaveDataset(
                [path_ser.iloc[i] for i in idx_test],
                y2[idx_test],
                target_sr=backend.sample_rate,
                target_seconds=float(target_seconds),
            )
            val_ds = _WaveDataset(
                [path_ser.iloc[i] for i in idx_val],
                y2[idx_val],
                target_sr=backend.sample_rate,
                target_seconds=float(target_seconds),
            )

            dl_workers = max(0, int(finetune_num_workers))
            dl_kwargs: Dict[str, Any] = {
                "num_workers": dl_workers,
                "pin_memory": (device.type == "cuda"),
            }
            if dl_workers > 0:
                dl_kwargs["persistent_workers"] = True
            train_dl = DataLoader(_TorchWaveDataset(train_ds), batch_size=int(finetune_batch_size), shuffle=True, **dl_kwargs)
            test_dl = DataLoader(_TorchWaveDataset(test_ds), batch_size=int(finetune_batch_size), shuffle=False, **dl_kwargs)
            val_dl = DataLoader(_TorchWaveDataset(val_ds), batch_size=int(finetune_batch_size), shuffle=False, **dl_kwargs)

            # Head gets higher LR; partially-unfrozen backbone gets low LR.
            bb_params = [p for p in model_backbone.parameters() if p.requires_grad]
            params = []
            if bb_params:
                params.append({"params": bb_params, "lr": float(finetune_lr_backbone)})
            params.append({"params": list(head.parameters()), "lr": float(finetune_lr_head)})
            optim = torch.optim.AdamW(params, weight_decay=1e-4)
            criterion = nn.CrossEntropyLoss()

            def _forward_emb(xb):
                out = model_backbone(xb)
                if isinstance(out, dict):
                    emb = out.get("embedding", None)
                elif isinstance(out, (tuple, list)) and len(out) >= 2:
                    emb = out[1]
                else:
                    emb = None
                if emb is None:
                    raise RuntimeError("Fine-tune forward failed: missing embedding in model output")
                if emb.ndim > 2:
                    emb = emb.reshape(emb.shape[0], -1)
                return emb

            for _ep in range(int(finetune_epochs)):
                model_backbone.train()
                head.train()
                ep_loss_sum = 0.0
                ep_rows = 0
                for xb, yb in train_dl:
                    xb = xb.to(device, non_blocking=True)
                    yb = yb.to(device, non_blocking=True)
                    optim.zero_grad(set_to_none=True)
                    with torch.cuda.amp.autocast(enabled=use_amp):
                        emb = _forward_emb(xb)
                        logits = head(emb)
                        loss = criterion(logits, yb)
                    scaler.scale(loss).backward()
                    scaler.step(optim)
                    scaler.update()
                    bsz = int(yb.shape[0])
                    ep_loss_sum += float(loss.detach().cpu().item()) * bsz
                    ep_rows += bsz
                avg_loss = float(ep_loss_sum / max(1, ep_rows))
                print(
                    f"[finetune][epoch {_ep + 1:03d}/{int(finetune_epochs)}] loss={avg_loss:.6f}",
                    flush=True,
                )

            def _pred(dl) -> np.ndarray:
                model_backbone.eval()
                head.eval()
                outp: List[np.ndarray] = []
                with torch.no_grad():
                    for xb, _yb in dl:
                        xb = xb.to(device, non_blocking=True)
                        emb = _forward_emb(xb)
                        logits = head(emb)
                        yp = torch.argmax(logits, dim=1).cpu().numpy().astype(np.int64)
                        outp.append(yp)
                if not outp:
                    return np.zeros((0,), dtype=np.int64)
                return np.concatenate(outp, axis=0)

            yp_tr = _pred(train_dl)
            yp_te = _pred(test_dl)
            yp_va = _pred(val_dl) if len(idx_val) else np.zeros((0,), dtype=np.int64)

            y_pred_ft_all = np.zeros((len(df2),), dtype=np.int64)
            y_pred_ft_all[idx_train] = yp_tr
            y_pred_ft_all[idx_test] = yp_te
            if len(idx_val):
                y_pred_ft_all[idx_val] = yp_va

            finetune_metrics = {
                "status": "ok",
                "unfrozen_modules": unfrozen,
                "train": _metrics_dict(y2[idx_train], y_pred_ft_all[idx_train], task=task),
                "test": _metrics_dict(y2[idx_test], y_pred_ft_all[idx_test], task=task),
                "val": _metrics_dict(y2[idx_val], y_pred_ft_all[idx_val], task=task) if len(idx_val) else {},
                "by_source": {
                    "train": _metrics_by_source(
                        y_true_all=y2,
                        y_pred_all=y_pred_ft_all,
                        source_all=src_series,
                        idx=idx_train,
                        task=task,
                        labels=labels,
                    ),
                    "test": _metrics_by_source(
                        y_true_all=y2,
                        y_pred_all=y_pred_ft_all,
                        source_all=src_series,
                        idx=idx_test,
                        task=task,
                        labels=labels,
                    ),
                    "val": _metrics_by_source(
                        y_true_all=y2,
                        y_pred_all=y_pred_ft_all,
                        source_all=src_series,
                        idx=idx_val,
                        task=task,
                        labels=labels,
                    )
                    if len(idx_val)
                    else {},
                },
            }

            finetuned_head_path = out_dir / "partial_finetune_head.pt"
            torch.save(
                {
                    "head_state_dict": head.state_dict(),
                    "n_classes": int(n_classes),
                    "backend": "panns",
                    "target_seconds": float(target_seconds),
                    "sample_rate": int(backend.sample_rate),
                },
                str(finetuned_head_path),
            )

    metrics = {
        "backend": backend_name,
        "task": task,
        "target_col": target_col,
        "split_source": split_source,
        "n_rows": int(len(df2)),
        "n_train": int(len(idx_train)),
        "n_test": int(len(idx_test)),
        "n_val": int(len(idx_val)),
        "class_map": y_meta.get("classes", None),
        "frozen_mlp": frozen_metrics,
        "partial_finetune": finetune_metrics,
    }

    metrics_path = out_dir / "audio_pretrained_embedding_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return AudioPretrainedEmbeddingResult(
        out_dir=out_dir,
        metrics_path=metrics_path,
        frozen_head_path=frozen_head_path,
        finetuned_head_path=finetuned_head_path,
    )
