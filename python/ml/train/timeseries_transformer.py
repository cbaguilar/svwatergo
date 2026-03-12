from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def _require_torch():
    try:
        import torch  # type: ignore
        import torch.nn as nn  # type: ignore
        from torch.utils.data import DataLoader, Dataset  # type: ignore
    except Exception as e:
        raise RuntimeError(f"Torch import failed: {e}. Install with `pip install torch`.") from e
    return torch, nn, DataLoader, Dataset


@dataclass(frozen=True)
class TimeSeriesTransformerResult:
    model_path: Path
    metrics_path: Path
    config_path: Path


@dataclass(frozen=True)
class TimeSeriesTransformerBacktestResult:
    predictions: pd.DataFrame
    metrics: Dict[str, Any]
    feature_cols: List[str]


class _WindowDataset:
    def __init__(
        self,
        features: np.ndarray,
        end_idx: np.ndarray,
        lookback: int,
        horizon_steps: int,
        target_mode: str,
    ) -> None:
        self.features = np.asarray(features, dtype=np.float32)
        self.end_idx = np.asarray(end_idx, dtype=np.int64)
        self.lookback = int(lookback)
        self.horizon_steps = int(horizon_steps)
        self.target_mode = str(target_mode)

    def __len__(self) -> int:
        return int(self.end_idx.shape[0])

    def __getitem__(self, i: int) -> Tuple[np.ndarray, np.ndarray]:
        end = int(self.end_idx[i])
        x = self.features[end - self.lookback + 1 : end + 1]
        if self.target_mode == "last":
            y = self.features[end + self.horizon_steps]
        else:
            y = self.features[end + 1 : end + self.horizon_steps + 1].mean(axis=0)
        return x.astype(np.float32, copy=False), y.astype(np.float32, copy=False)


class _TransformerRegressor:
    def __init__(
        self,
        nn,
        *,
        input_dim: int,
        d_model: int,
        nhead: int,
        num_layers: int,
        dropout: float,
        ff_dim: int,
        max_lookback: int,
    ):
        class _Model(nn.Module):
            def __init__(self):
                super().__init__()
                self.in_proj = nn.Linear(input_dim, d_model)
                self.pos_emb = nn.Embedding(max_lookback, d_model)
                enc_layer = nn.TransformerEncoderLayer(
                    d_model=d_model,
                    nhead=nhead,
                    dim_feedforward=ff_dim,
                    dropout=dropout,
                    batch_first=True,
                    activation="gelu",
                )
                self.encoder = nn.TransformerEncoder(enc_layer, num_layers=num_layers)
                self.head = nn.Sequential(
                    nn.LayerNorm(d_model),
                    nn.Linear(d_model, d_model),
                    nn.GELU(),
                    nn.Dropout(dropout),
                    nn.Linear(d_model, input_dim),
                )

            def forward(self, x):
                import torch  # type: ignore

                b, t, _ = x.shape
                pos = torch.arange(t, device=x.device).unsqueeze(0).expand(b, t)
                h = self.in_proj(x) + self.pos_emb(pos)
                h = self.encoder(h)
                out = self.head(h[:, -1, :])
                return out

        self.model = _Model()


def _parse_duration_seconds(text: str) -> int:
    s = str(text).strip().lower()
    if not s:
        raise ValueError("Duration is empty")
    mult = 1
    if s.endswith("ms"):
        return max(1, int(round(float(s[:-2]) / 1000.0)))
    if s.endswith("s"):
        mult = 1
        s = s[:-1]
    elif s.endswith("m"):
        mult = 60
        s = s[:-1]
    elif s.endswith("h"):
        mult = 3600
        s = s[:-1]
    elif s.endswith("d"):
        mult = 86400
        s = s[:-1]
    return int(round(float(s) * mult))


def _infer_sample_period_seconds(ts: pd.Series) -> float:
    if np.issubdtype(ts.dtype, np.datetime64):
        v = ts.astype("int64").to_numpy(dtype=np.int64)
        diffs = np.diff(v)
        diffs = diffs[diffs > 0]
        if diffs.size == 0:
            raise ValueError("Cannot infer sample period from datetime timestamp column")
        return float(np.median(diffs) / 1e9)
    vals = pd.to_numeric(ts, errors="coerce").to_numpy(dtype=np.float64)
    diffs = np.diff(vals)
    diffs = diffs[np.isfinite(diffs) & (diffs > 0)]
    if diffs.size == 0:
        raise ValueError("Cannot infer sample period from numeric timestamp column")
    return float(np.median(diffs))


def _time_seconds(ts: pd.Series) -> np.ndarray:
    if np.issubdtype(ts.dtype, np.datetime64):
        return (ts.astype("int64").to_numpy(dtype=np.float64) / 1e9)
    return pd.to_numeric(ts, errors="coerce").to_numpy(dtype=np.float64)


def _build_end_indices(
    df: pd.DataFrame,
    *,
    timestamp_col: str,
    group_col: str,
    lookback: int,
    horizon_steps: int,
    stride: int,
    max_gap_seconds: float,
) -> Tuple[np.ndarray, np.ndarray]:
    times = _time_seconds(df[timestamp_col])
    groups = df[group_col].astype(str).to_numpy() if group_col else np.array(["__all__"] * len(df), dtype=object)

    out_idx: List[int] = []
    out_t: List[float] = []
    start = 0
    n = len(df)
    while start < n:
        g = groups[start]
        end = start + 1
        while end < n and groups[end] == g:
            end += 1

        seg_start = start
        if max_gap_seconds > 0:
            for i in range(start + 1, end):
                if not np.isfinite(times[i - 1]) or not np.isfinite(times[i]) or (times[i] - times[i - 1]) > max_gap_seconds:
                    _append_segment_indices(out_idx, out_t, times, seg_start, i, lookback, horizon_steps, stride)
                    seg_start = i
        _append_segment_indices(out_idx, out_t, times, seg_start, end, lookback, horizon_steps, stride)
        start = end

    if not out_idx:
        raise ValueError("No training samples constructed. Lower --lookback/--horizon or verify timestamp continuity.")
    return np.asarray(out_idx, dtype=np.int64), np.asarray(out_t, dtype=np.float64)


def _append_segment_indices(
    out_idx: List[int],
    out_t: List[float],
    times: np.ndarray,
    seg_start: int,
    seg_end: int,
    lookback: int,
    horizon_steps: int,
    stride: int,
) -> None:
    first_end = seg_start + lookback - 1
    last_end = seg_end - horizon_steps - 1
    if last_end < first_end:
        return
    for e in range(first_end, last_end + 1, max(1, stride)):
        out_idx.append(e)
        out_t.append(float(times[e + horizon_steps]))


def _split_by_time(times: np.ndarray, train_frac: float, val_frac: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    order = np.argsort(times)
    n = len(order)
    if n < 3:
        raise ValueError("Need at least 3 generated samples to build train/val/test splits")

    n_train = max(1, int(math.floor(n * train_frac)))
    n_val = max(1, int(math.floor(n * val_frac)))
    if n_train + n_val > n - 1:
        overflow = (n_train + n_val) - (n - 1)
        reduce_val = min(overflow, max(0, n_val - 1))
        n_val -= reduce_val
        overflow -= reduce_val
        if overflow > 0:
            n_train = max(1, n_train - overflow)

    tr = order[:n_train]
    va = order[n_train : n_train + n_val]
    te = order[n_train + n_val :]
    if va.size == 0 or te.size == 0:
        raise ValueError("Unable to create non-empty val/test split. Lower lookback/horizon or add more data.")
    return tr.astype(np.int64), va.astype(np.int64), te.astype(np.int64)


def _compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    err = y_pred - y_true
    mse = float(np.mean(np.square(err)))
    rmse = float(np.sqrt(mse))
    mae = float(np.mean(np.abs(err)))
    yt = y_true.reshape(-1)
    yp = y_pred.reshape(-1)
    y_mean = float(np.mean(yt))
    ss_res = float(np.sum((yt - yp) ** 2))
    ss_tot = float(np.sum((yt - y_mean) ** 2))
    r2 = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
    return {"mse": mse, "rmse": rmse, "mae": mae, "r2": r2}


def expected_plc_window_feature_columns(
    *,
    site: str,
    include_last: bool = False,
    include_transition_age: bool = True,
) -> List[str]:
    try:
        from python.analytics.window_features.specs import PIPELINES  # type: ignore
    except Exception as e:
        raise RuntimeError(
            f"Unable to import PLC window feature specs: {e}. "
            "Expected module: python.analytics.window_features.specs"
        ) from e

    site_key = str(site).strip().lower()
    spec = PIPELINES.get(site_key)
    if spec is None:
        raise ValueError(f"Unknown site {site!r}. Known sites: {sorted(PIPELINES)}")

    cols: List[str] = []
    for c in sorted(spec.continuous):
        cols.append(f"{c}__mean_tw")
        cols.append(f"{c}__d1")
        if include_last:
            cols.append(f"{c}__last")
    for b in sorted(spec.boolean):
        cols.append(f"{b}__duty")
        cols.append(f"{b}__transitions")
        if include_last:
            cols.append(f"{b}__last")
    for d in sorted(spec.discrete):
        cols.append(f"{d}__mode_tw")
        cols.append(f"{d}__transitions")
        if include_last:
            cols.append(f"{d}__last")

    if include_transition_age:
        cols.extend(
            [
                "state__sec_since_transition",
                "ropumprun__sec_since_transition",
                "deliveryrun__sec_since_transition",
            ]
        )
    return cols


def expected_plc_raw_feature_columns(*, site: str) -> List[str]:
    try:
        from python.analytics.window_features.specs import PIPELINES  # type: ignore
    except Exception as e:
        raise RuntimeError(
            f"Unable to import PLC specs: {e}. "
            "Expected module: python.analytics.window_features.specs"
        ) from e

    site_key = str(site).strip().lower()
    spec = PIPELINES.get(site_key)
    if spec is None:
        raise ValueError(f"Unknown site {site!r}. Known sites: {sorted(PIPELINES)}")
    return sorted(list(spec.continuous) + list(spec.boolean) + list(spec.discrete))


def fit_timeseries_transformer(
    df: pd.DataFrame,
    out_dir: Path,
    *,
    timestamp_col: str,
    feature_cols: Optional[Sequence[str]] = None,
    group_col: str = "",
    horizon: str = "1h",
    lookback: int = 256,
    stride: int = 1,
    max_gap_seconds: float = 0.0,
    target_mode: str = "mean",
    train_frac: float = 0.7,
    val_frac: float = 0.15,
    random_state: int = 42,
    batch_size: int = 128,
    epochs: int = 20,
    learning_rate: float = 1e-3,
    weight_decay: float = 1e-4,
    d_model: int = 128,
    nhead: int = 4,
    num_layers: int = 2,
    ff_dim: int = 256,
    dropout: float = 0.1,
    grad_clip: float = 1.0,
    dataloader_num_workers: int = 0,
    device: str = "auto",
    resume_from: Optional[Path] = None,
    save_every_epochs: int = 1,
    keep_epoch_checkpoints: bool = True,
) -> TimeSeriesTransformerResult:
    torch, nn, DataLoader, Dataset = _require_torch()

    if timestamp_col not in df.columns:
        raise ValueError(f"timestamp_col not found: {timestamp_col}")
    if group_col and group_col not in df.columns:
        raise ValueError(f"group_col not found: {group_col}")

    df2 = df.copy()
    if np.issubdtype(df2[timestamp_col].dtype, np.datetime64):
        pass
    else:
        maybe_dt = pd.to_datetime(df2[timestamp_col], errors="coerce", utc=True)
        if maybe_dt.notna().mean() > 0.9:
            df2[timestamp_col] = maybe_dt

    sort_cols = [group_col, timestamp_col] if group_col else [timestamp_col]
    df2 = df2.sort_values(sort_cols).reset_index(drop=True)

    if feature_cols:
        cols = [c for c in feature_cols if c in df2.columns]
        missing = [c for c in feature_cols if c not in df2.columns]
        if missing:
            raise ValueError(f"feature_cols missing from dataframe: {', '.join(missing)}")
    else:
        blocked = {timestamp_col}
        if group_col:
            blocked.add(group_col)
        cols = [c for c in df2.columns if c not in blocked and pd.api.types.is_numeric_dtype(df2[c])]
    if not cols:
        raise ValueError("No numeric feature columns available")

    feat = df2[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float32)
    valid_row = np.all(np.isfinite(feat), axis=1)
    if valid_row.mean() < 1.0:
        df2 = df2.loc[valid_row].reset_index(drop=True)
        feat = feat[valid_row]

    sample_period_seconds = _infer_sample_period_seconds(df2[timestamp_col])
    horizon_seconds = _parse_duration_seconds(horizon)
    horizon_steps = max(1, int(round(horizon_seconds / max(1e-9, sample_period_seconds))))

    end_idx, sample_times = _build_end_indices(
        df2,
        timestamp_col=timestamp_col,
        group_col=group_col,
        lookback=int(lookback),
        horizon_steps=int(horizon_steps),
        stride=int(stride),
        max_gap_seconds=float(max_gap_seconds),
    )

    tr_s, va_s, te_s = _split_by_time(sample_times, float(train_frac), float(val_frac))
    train_end = end_idx[tr_s]
    val_end = end_idx[va_s]
    test_end = end_idx[te_s]

    train_rows = np.unique(np.concatenate([np.arange(e - lookback + 1, e + 1) for e in train_end]))
    mu = feat[train_rows].mean(axis=0)
    sigma = feat[train_rows].std(axis=0)
    sigma = np.where(sigma > 1e-6, sigma, 1.0)
    feat_n = ((feat - mu) / sigma).astype(np.float32, copy=False)

    class WindowDataset(Dataset):
        def __init__(self, features, ends, lookback_v, horizon_steps_v, target_mode_v):
            self.impl = _WindowDataset(features, ends, lookback_v, horizon_steps_v, target_mode_v)

        def __len__(self):
            return len(self.impl)

        def __getitem__(self, i):
            return self.impl[i]

    train_ds = WindowDataset(feat_n, train_end, lookback, horizon_steps, target_mode)
    val_ds = WindowDataset(feat_n, val_end, lookback, horizon_steps, target_mode)
    test_ds = WindowDataset(feat_n, test_end, lookback, horizon_steps, target_mode)

    pin_memory = bool(torch.cuda.is_available())
    train_dl = DataLoader(train_ds, batch_size=int(batch_size), shuffle=True, num_workers=int(dataloader_num_workers), pin_memory=pin_memory)
    val_dl = DataLoader(val_ds, batch_size=int(batch_size), shuffle=False, num_workers=int(dataloader_num_workers), pin_memory=pin_memory)
    test_dl = DataLoader(test_ds, batch_size=int(batch_size), shuffle=False, num_workers=int(dataloader_num_workers), pin_memory=pin_memory)

    if device == "auto":
        dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        dev = torch.device(device)

    torch.manual_seed(int(random_state))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(random_state))

    model = _TransformerRegressor(
        nn,
        input_dim=feat_n.shape[1],
        d_model=int(d_model),
        nhead=int(nhead),
        num_layers=int(num_layers),
        dropout=float(dropout),
        ff_dim=int(ff_dim),
        max_lookback=int(lookback),
    ).model.to(dev)

    opt = torch.optim.AdamW(model.parameters(), lr=float(learning_rate), weight_decay=float(weight_decay))
    loss_fn = nn.MSELoss()

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_latest_path = out_dir / "timeseries_transformer_checkpoint_latest.pt"
    checkpoint_best_path = out_dir / "timeseries_transformer_checkpoint_best.pt"
    history_path = out_dir / "timeseries_transformer_learning_history.json"

    best = {"val_rmse": float("inf"), "state": None, "epoch": -1}
    history: List[Dict[str, Any]] = []
    start_epoch = 1

    resume_path = Path(resume_from) if resume_from else checkpoint_latest_path
    if resume_path.exists():
        ckpt = torch.load(resume_path, map_location="cpu", weights_only=False)
        if isinstance(ckpt, dict) and "model_state_dict" in ckpt and "optimizer_state_dict" in ckpt:
            model.load_state_dict(ckpt["model_state_dict"])
            opt.load_state_dict(ckpt["optimizer_state_dict"])
            history = list(ckpt.get("history", []))
            best_ck = ckpt.get("best", {})
            if isinstance(best_ck, dict):
                best["val_rmse"] = float(best_ck.get("val_rmse", best["val_rmse"]))
                best["epoch"] = int(best_ck.get("epoch", best["epoch"]))
                if "state" in best_ck and best_ck["state"] is not None:
                    best["state"] = best_ck["state"]
            start_epoch = int(ckpt.get("epoch", 0)) + 1
    elif history_path.exists():
        try:
            hist_obj = json.loads(history_path.read_text(encoding="utf-8"))
            if isinstance(hist_obj, list):
                history = hist_obj
        except Exception:
            pass

    def _eval(dloader):
        model.eval()
        ys = []
        yp = []
        with torch.no_grad():
            for xb, yb in dloader:
                xb = xb.to(dev)
                yb = yb.to(dev)
                pred = model(xb)
                ys.append(yb.detach().cpu().numpy())
                yp.append(pred.detach().cpu().numpy())
        if not ys:
            raise ValueError("Evaluation split is empty. Lower lookback/horizon or add more rows.")
        y_true = np.concatenate(ys, axis=0)
        y_pred = np.concatenate(yp, axis=0)
        return _compute_metrics(y_true, y_pred)

    for ep in range(int(start_epoch), int(epochs) + 1):
        model.train()
        losses = []
        for xb, yb in train_dl:
            xb = xb.to(dev)
            yb = yb.to(dev)
            opt.zero_grad(set_to_none=True)
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            if float(grad_clip) > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), float(grad_clip))
            opt.step()
            losses.append(float(loss.detach().cpu().item()))

        train_loss = float(np.mean(losses)) if losses else float("nan")
        val_metrics = _eval(val_dl)
        row = {"epoch": ep, "train_loss": train_loss, **{f"val_{k}": float(v) for k, v in val_metrics.items()}}
        history.append(row)
        history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")

        if val_metrics["rmse"] < best["val_rmse"]:
            best = {
                "val_rmse": float(val_metrics["rmse"]),
                "state": {k: v.detach().cpu() for k, v in model.state_dict().items()},
                "epoch": int(ep),
            }
            torch.save(
                {
                    "epoch": int(ep),
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": opt.state_dict(),
                    "history": history,
                    "best": best,
                    "model_config": {
                        "input_dim": int(feat_n.shape[1]),
                        "lookback": int(lookback),
                        "horizon": str(horizon),
                        "horizon_steps": int(horizon_steps),
                        "target_mode": str(target_mode),
                        "d_model": int(d_model),
                        "nhead": int(nhead),
                        "num_layers": int(num_layers),
                        "ff_dim": int(ff_dim),
                        "dropout": float(dropout),
                    },
                    "normalization": {
                        "feature_cols": list(cols),
                        "mean": mu.astype(np.float32),
                        "std": sigma.astype(np.float32),
                    },
                },
                checkpoint_best_path,
            )

        if int(save_every_epochs) > 0 and (ep % int(save_every_epochs) == 0):
            ckpt_payload = {
                "epoch": int(ep),
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": opt.state_dict(),
                "history": history,
                "best": best,
                "model_config": {
                    "input_dim": int(feat_n.shape[1]),
                    "lookback": int(lookback),
                    "horizon": str(horizon),
                    "horizon_steps": int(horizon_steps),
                    "target_mode": str(target_mode),
                    "d_model": int(d_model),
                    "nhead": int(nhead),
                    "num_layers": int(num_layers),
                    "ff_dim": int(ff_dim),
                    "dropout": float(dropout),
                },
                "normalization": {
                    "feature_cols": list(cols),
                    "mean": mu.astype(np.float32),
                    "std": sigma.astype(np.float32),
                },
            }
            torch.save(ckpt_payload, checkpoint_latest_path)
            if keep_epoch_checkpoints:
                torch.save(ckpt_payload, out_dir / f"timeseries_transformer_checkpoint_epoch_{int(ep):04d}.pt")

    if best["state"] is not None:
        model.load_state_dict(best["state"])

    val_metrics = _eval(val_dl)
    test_metrics = _eval(test_dl)

    model_path = out_dir / "timeseries_transformer.pt"
    metrics_path = out_dir / "timeseries_transformer_metrics.json"
    config_path = out_dir / "timeseries_transformer_config.json"

    payload = {
        "model_state_dict": model.state_dict(),
        "normalization": {
            "feature_cols": list(cols),
            "mean": mu.astype(np.float32),
            "std": sigma.astype(np.float32),
        },
        "model_config": {
            "input_dim": int(feat_n.shape[1]),
            "lookback": int(lookback),
            "horizon": str(horizon),
            "horizon_steps": int(horizon_steps),
            "target_mode": str(target_mode),
            "d_model": int(d_model),
            "nhead": int(nhead),
            "num_layers": int(num_layers),
            "ff_dim": int(ff_dim),
            "dropout": float(dropout),
        },
    }
    torch.save(payload, model_path)

    metrics = {
        "train": {
            "num_samples": int(len(train_ds)),
            "best_epoch": int(best["epoch"]),
            "history": history,
        },
        "val": {k: float(v) for k, v in val_metrics.items()},
        "test": {k: float(v) for k, v in test_metrics.items()},
        "data": {
            "rows": int(len(df2)),
            "num_features": int(len(cols)),
            "timestamp_col": str(timestamp_col),
            "group_col": str(group_col),
            "sample_period_seconds": float(sample_period_seconds),
            "horizon_seconds": int(horizon_seconds),
            "horizon_steps": int(horizon_steps),
            "lookback": int(lookback),
            "stride": int(stride),
            "target_mode": str(target_mode),
        },
    }
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    config = {
        "feature_cols": list(cols),
        "timestamp_col": str(timestamp_col),
        "group_col": str(group_col),
        "lookback": int(lookback),
        "horizon": str(horizon),
        "horizon_steps": int(horizon_steps),
        "target_mode": str(target_mode),
        "sample_period_seconds": float(sample_period_seconds),
        "normalization": {
            "mean": [float(x) for x in mu.tolist()],
            "std": [float(x) for x in sigma.tolist()],
        },
    }
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    return TimeSeriesTransformerResult(
        model_path=model_path,
        metrics_path=metrics_path,
        config_path=config_path,
    )


def load_timeseries_transformer_bundle(model_path: Path) -> Dict[str, Any]:
    torch, _, _, _ = _require_torch()
    obj = torch.load(Path(model_path), map_location="cpu", weights_only=False)
    if not isinstance(obj, dict):
        raise ValueError(f"Invalid bundle format in {model_path}")
    if "model_state_dict" not in obj or "model_config" not in obj or "normalization" not in obj:
        raise ValueError(f"Bundle missing required keys in {model_path}")
    return obj


def backtest_timeseries_transformer(
    df: pd.DataFrame,
    model_path: Path,
    *,
    timestamp_col: str,
    group_col: str = "",
    horizon: str = "",
    lookback: int = 0,
    stride: int = 1,
    max_gap_seconds: float = 0.0,
    target_mode: str = "",
    batch_size: int = 256,
    dataloader_num_workers: int = 0,
    device: str = "auto",
) -> TimeSeriesTransformerBacktestResult:
    torch, nn, DataLoader, Dataset = _require_torch()

    bundle = load_timeseries_transformer_bundle(Path(model_path))
    model_cfg = dict(bundle.get("model_config", {}))
    norm_cfg = dict(bundle.get("normalization", {}))

    feature_cols = [str(c) for c in norm_cfg.get("feature_cols", [])]
    if not feature_cols:
        raise ValueError("Bundle normalization.feature_cols is empty")
    missing_cols = [c for c in feature_cols if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Input dataset missing feature columns: {', '.join(missing_cols)}")
    if timestamp_col not in df.columns:
        raise ValueError(f"timestamp_col not found: {timestamp_col}")
    if group_col and group_col not in df.columns:
        raise ValueError(f"group_col not found: {group_col}")

    model_horizon = str(model_cfg.get("horizon", "")).strip()
    use_horizon = str(horizon).strip() if str(horizon).strip() else model_horizon
    if not use_horizon:
        raise ValueError("No horizon provided and no horizon saved in bundle")
    use_lookback = int(lookback) if int(lookback) > 0 else int(model_cfg.get("lookback", 0))
    if use_lookback <= 0:
        raise ValueError("lookback must be > 0 (either argument or bundle model_config.lookback)")
    use_target_mode = str(target_mode).strip() if str(target_mode).strip() else str(model_cfg.get("target_mode", "mean"))

    df2 = df.copy()
    if not np.issubdtype(df2[timestamp_col].dtype, np.datetime64):
        maybe_dt = pd.to_datetime(df2[timestamp_col], errors="coerce", utc=True)
        if maybe_dt.notna().mean() > 0.9:
            df2[timestamp_col] = maybe_dt
    sort_cols = [group_col, timestamp_col] if group_col else [timestamp_col]
    df2 = df2.sort_values(sort_cols).reset_index(drop=True)

    feat = df2[feature_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float32)
    valid_row = np.all(np.isfinite(feat), axis=1)
    if valid_row.mean() < 1.0:
        df2 = df2.loc[valid_row].reset_index(drop=True)
        feat = feat[valid_row]

    mu = np.asarray(norm_cfg.get("mean", []), dtype=np.float32)
    sigma = np.asarray(norm_cfg.get("std", []), dtype=np.float32)
    if mu.shape[0] != feat.shape[1] or sigma.shape[0] != feat.shape[1]:
        raise ValueError("Bundle normalization shape does not match input feature count")
    sigma = np.where(np.abs(sigma) > 1e-6, sigma, 1.0).astype(np.float32)
    feat_n = ((feat - mu) / sigma).astype(np.float32, copy=False)

    sample_period_seconds = _infer_sample_period_seconds(df2[timestamp_col])
    horizon_seconds = _parse_duration_seconds(use_horizon)
    horizon_steps = max(1, int(round(horizon_seconds / max(1e-9, sample_period_seconds))))
    end_idx, _ = _build_end_indices(
        df2,
        timestamp_col=timestamp_col,
        group_col=group_col,
        lookback=use_lookback,
        horizon_steps=horizon_steps,
        stride=int(stride),
        max_gap_seconds=float(max_gap_seconds),
    )

    class WindowDataset(Dataset):
        def __init__(self, features, ends, lookback_v, horizon_steps_v, target_mode_v):
            self.impl = _WindowDataset(features, ends, lookback_v, horizon_steps_v, target_mode_v)

        def __len__(self):
            return len(self.impl)

        def __getitem__(self, i):
            return self.impl[i]

    ds = WindowDataset(feat_n, end_idx, use_lookback, horizon_steps, use_target_mode)
    if len(ds) == 0:
        raise ValueError("No backtest samples generated for this horizon/configuration")

    pin_memory = bool(torch.cuda.is_available())
    dl = DataLoader(ds, batch_size=int(batch_size), shuffle=False, num_workers=int(dataloader_num_workers), pin_memory=pin_memory)

    if device == "auto":
        dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        dev = torch.device(device)

    model = _TransformerRegressor(
        nn,
        input_dim=int(model_cfg.get("input_dim", feat_n.shape[1])),
        d_model=int(model_cfg.get("d_model", 128)),
        nhead=int(model_cfg.get("nhead", 4)),
        num_layers=int(model_cfg.get("num_layers", 2)),
        ff_dim=int(model_cfg.get("ff_dim", 256)),
        dropout=float(model_cfg.get("dropout", 0.1)),
        max_lookback=use_lookback,
    ).model.to(dev)
    model.load_state_dict(bundle["model_state_dict"])
    model.eval()

    ys = []
    yp = []
    with torch.no_grad():
        for xb, yb in dl:
            xb = xb.to(dev)
            pred = model(xb)
            ys.append(yb.detach().cpu().numpy())
            yp.append(pred.detach().cpu().numpy())
    y_true_n = np.concatenate(ys, axis=0)
    y_pred_n = np.concatenate(yp, axis=0)
    y_true = (y_true_n * sigma[None, :]) + mu[None, :]
    y_pred = (y_pred_n * sigma[None, :]) + mu[None, :]

    target_idx = end_idx + int(horizon_steps)
    out = pd.DataFrame(
        {
            "sample_end_index": end_idx.astype(np.int64),
            "target_index": target_idx.astype(np.int64),
            "horizon": [str(use_horizon)] * len(end_idx),
        }
    )
    out["timestamp"] = df2[timestamp_col].iloc[target_idx].to_numpy()
    if group_col:
        out[group_col] = df2[group_col].iloc[target_idx].astype(str).to_numpy()
    for j, c in enumerate(feature_cols):
        out[f"true_{c}"] = y_true[:, j].astype(np.float32)
        out[f"pred_{c}"] = y_pred[:, j].astype(np.float32)
        out[f"err_{c}"] = (y_pred[:, j] - y_true[:, j]).astype(np.float32)

    metrics = {
        "overall": _compute_metrics(y_true.astype(np.float32), y_pred.astype(np.float32)),
        "per_feature": {
            c: _compute_metrics(
                y_true[:, i : i + 1].astype(np.float32),
                y_pred[:, i : i + 1].astype(np.float32),
            )
            for i, c in enumerate(feature_cols)
        },
        "data": {
            "num_samples": int(len(out)),
            "num_features": int(len(feature_cols)),
            "timestamp_col": str(timestamp_col),
            "group_col": str(group_col),
            "horizon": str(use_horizon),
            "horizon_steps": int(horizon_steps),
            "lookback": int(use_lookback),
            "stride": int(stride),
            "target_mode": str(use_target_mode),
            "sample_period_seconds": float(sample_period_seconds),
        },
    }
    return TimeSeriesTransformerBacktestResult(predictions=out, metrics=metrics, feature_cols=feature_cols)
