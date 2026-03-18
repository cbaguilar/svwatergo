#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from python.ml.train.audio_pca_svm import _coerce_target
from python.ml.train.audio_pretrained_embedding_multitask import (
    AudioPretrainedEmbeddingMultitaskModelFactory,
    _coerce_binary_targets,
)


DEFAULT_TARGET_COLS = [
    "ropumprun_duty_target",
    "wellpumprun_duty_target",
    "feedpumprun_duty_target",
    "deliveryrun_duty_target",
    "flushrun_duty_target",
]


def _parse_csv(values: str) -> List[str]:
    return [str(v).strip() for v in str(values).split(",") if str(v).strip()]


def _load_checkpoint(path: Path) -> Dict[str, object]:
    try:
        import torch  # type: ignore
    except Exception as e:  # pragma: no cover
        raise SystemExit("Missing torch. Install: pip install torch") from e
    obj = torch.load(str(path), map_location="cpu")
    if not isinstance(obj, dict) or "state_dict" not in obj:
        raise ValueError(f"Invalid checkpoint bundle: {path}")
    return obj


def _resolve_target_cols(ckpt: Dict[str, object], requested: Sequence[str]) -> List[str]:
    cols = [str(c).strip() for c in requested if str(c).strip()]
    if cols:
        return cols
    cols = [str(c).strip() for c in (ckpt.get("target_cols") or []) if str(c).strip()]
    if cols:
        return cols
    return list(DEFAULT_TARGET_COLS)


def _build_day_window(day: str, timezone: str) -> Tuple[pd.Timestamp, pd.Timestamp]:
    start_local = pd.Timestamp(f"{day} 00:00:00", tz=timezone)
    end_local = start_local + pd.Timedelta(days=1)
    return start_local.tz_convert("UTC"), end_local.tz_convert("UTC")


def _filter_window(
    df: pd.DataFrame,
    *,
    time_col: str,
    source_col: str,
    source_value: str,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
) -> pd.DataFrame:
    if time_col not in df.columns:
        raise ValueError(f"Missing time column in dataset: {time_col}")
    if source_col not in df.columns:
        raise ValueError(f"Missing source column in dataset: {source_col}")
    out = df.copy()
    out[time_col] = pd.to_datetime(out[time_col], utc=True, errors="coerce")
    out = out[out[time_col].notna()].copy()
    out = out[out[source_col].astype(str) == str(source_value)].copy()
    out = out[(out[time_col] >= start_utc) & (out[time_col] < end_utc)].copy()
    if out.empty:
        raise ValueError(
            f"No rows found for {source_col}={source_value!r} in "
            f"[{start_utc.isoformat()}, {end_utc.isoformat()})"
        )
    return out.sort_values([time_col, "sample_id"] if "sample_id" in out.columns else [time_col], kind="mergesort")


def _select_metadata_cols(df: pd.DataFrame, *, target_cols: Sequence[str]) -> List[str]:
    preferred = [
        "sample_id",
        "site",
        "audio_source",
        "camera",
        "day_utc",
        "segment_start_ts_utc",
        "segment_end_ts_utc",
        "segment_path",
        "state__mode_tw",
    ]
    keep = [c for c in preferred if c in df.columns]
    extras = [str(c) for c in target_cols if str(c) in df.columns and str(c) not in keep]
    state_cols = [str(c) for c in df.columns if str(c).startswith("state__") and str(c) not in keep and str(c) not in extras]
    return keep + extras + state_cols


def _attach_truth(df: pd.DataFrame, *, task_mode: str, target_col: Optional[str], target_cols: Sequence[str]) -> pd.DataFrame:
    mode = str(task_mode).strip().lower()
    out = df.copy()
    if mode == "multiclass":
        tc = str(target_col or "").strip()
        if tc and tc in out.columns:
            _, y_raw, y_meta = _coerce_target(out, target_col=tc, task="multiclass", positive_label="on")
            classes = [str(x) for x in (y_meta.get("classes") or [])]
            labels = np.asarray(y_raw, dtype=np.int64)
            out["true_label"] = [classes[i] if 0 <= int(i) < len(classes) else str(int(i)) for i in labels.tolist()]
    elif mode == "multilabel":
        cols = [str(c).strip() for c in target_cols if str(c).strip()]
        if cols and all(c in out.columns for c in cols):
            y_raw, _ = _coerce_binary_targets(
                out,
                target_cols=cols,
                positive_threshold=0.5,
                positive_label="on",
            )
            bits = np.asarray(y_raw, dtype=np.int64)
            out["true_bits"] = ["|".join(str(int(v)) for v in row.tolist()) for row in bits]
            out["true_label"] = [
                "|".join(f"{name}={'on' if int(v) == 1 else 'off'}" for name, v in zip(cols, row.tolist()))
                for row in bits
            ]
    return out


def _infer_multitask_dataset(
    df: pd.DataFrame,
    *,
    embeddings_path: Path,
    embeddings_key: str,
    dataset_len: int,
    ckpt: Dict[str, object],
    batch_size: int,
    target_cols: Sequence[str],
) -> pd.DataFrame:
    try:
        import torch  # type: ignore
    except Exception as e:  # pragma: no cover
        raise SystemExit("Missing torch. Install: pip install torch") from e

    z = np.load(str(embeddings_path))
    if embeddings_key not in z.files:
        raise ValueError(f"Embeddings key {embeddings_key!r} not found in {embeddings_path}. Available: {list(z.files)}")
    x_full = np.asarray(z[embeddings_key], dtype=np.float32)
    if int(x_full.shape[0]) != int(dataset_len):
        raise ValueError("Embedding cache rows do not match original dataset rows.")
    row_idx = df.index.to_numpy(dtype=np.int64, copy=False)
    x = np.asarray(x_full[row_idx], dtype=np.float32, copy=False)
    df = df.reset_index(drop=True)

    hidden = [int(v) for v in (ckpt.get("hidden") or [])]
    z_dim = int(ckpt.get("z_dim", 64))
    input_dim = int(ckpt.get("input_dim", int(x.shape[1])))
    y_dim = int(ckpt.get("n_targets", 0))
    model = AudioPretrainedEmbeddingMultitaskModelFactory.build(
        in_dim=input_dim,
        hidden=hidden,
        z_dim=z_dim,
        y_dim=y_dim,
        plc_dim=0,
        drop=0.0,
    )
    model.load_state_dict(ckpt["state_dict"], strict=False)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.eval()

    mode = str(ckpt.get("task_mode", "multiclass")).strip().lower()
    target_col = str(ckpt.get("target_col") or "").strip() or None
    target_cols = [str(c) for c in target_cols]
    class_names = [str(v) for v in (ckpt.get("class_names") or [])]
    reg_mean = np.asarray(ckpt.get("regression_target_mean") or [], dtype=np.float32)
    reg_std = np.asarray(ckpt.get("regression_target_std") or [], dtype=np.float32)

    rows: List[pd.DataFrame] = []
    x_t = torch.from_numpy(np.asarray(x, dtype=np.float32))
    bs = max(1, int(batch_size))
    with torch.no_grad():
        for i0 in range(0, int(x_t.shape[0]), bs):
            xb = x_t[i0 : i0 + bs].to(device)
            logits, z_latent, _ = model(xb)
            batch_df = df.iloc[i0 : i0 + len(xb)].copy()
            batch_df = batch_df[_select_metadata_cols(batch_df, target_cols=target_cols)]

            if mode == "multiclass":
                probs = torch.softmax(logits, dim=1).cpu().numpy().astype(np.float32, copy=False)
                pred_idx = np.argmax(probs, axis=1).astype(np.int64, copy=False)
                batch_df["pred_index"] = pred_idx
                batch_df["pred_label"] = [
                    class_names[i] if class_names and 0 <= int(i) < len(class_names) else str(int(i))
                    for i in pred_idx.tolist()
                ]
                batch_df["pred_confidence"] = np.max(probs, axis=1).astype(np.float32, copy=False)
            elif mode == "multilabel":
                probs = torch.sigmoid(logits).cpu().numpy().astype(np.float32, copy=False)
                thresholds = np.asarray(
                    list(ckpt.get("inference_thresholds") or [0.5] * len(target_cols)),
                    dtype=np.float64,
                )
                if thresholds.shape[0] != len(target_cols):
                    thresholds = np.asarray([float(ckpt.get("inference_threshold_default", 0.5))] * len(target_cols))
                preds = (probs >= thresholds.reshape(1, -1)).astype(np.int64, copy=False)
                batch_df["pred_confidence"] = np.max(np.maximum(probs, 1.0 - probs), axis=1).astype(np.float32, copy=False)
                batch_df["pred_bits"] = ["|".join(str(int(v)) for v in row.tolist()) for row in preds]
                batch_df["pred_label"] = [
                    "|".join(f"{name}={'on' if int(v) == 1 else 'off'}" for name, v in zip(target_cols, row.tolist()))
                    for row in preds
                ]
                for j, name in enumerate(target_cols):
                    batch_df[f"prob__{name}"] = probs[:, j]
                    batch_df[f"pred__{name}"] = preds[:, j]
            elif mode == "multiregression":
                pred = logits.cpu().numpy().astype(np.float32, copy=False)
                if reg_mean.size and reg_std.size and reg_mean.shape[0] == pred.shape[1] and reg_std.shape[0] == pred.shape[1]:
                    pred = (pred * reg_std.reshape(1, -1)) + reg_mean.reshape(1, -1)
                for j, name in enumerate(target_cols):
                    batch_df[f"pred__{name}"] = pred[:, j].astype(np.float32, copy=False)
            else:
                raise ValueError(f"Unsupported task_mode: {mode!r}")

            for j in range(int(z_latent.shape[1])):
                batch_df[f"latent_{j:03d}"] = z_latent[:, j].detach().cpu().numpy().astype(np.float32, copy=False)
            rows.append(batch_df)

    out_df = pd.concat(rows, axis=0, ignore_index=True, sort=False)
    out_df = _attach_truth(out_df, task_mode=mode, target_col=target_col, target_cols=target_cols)
    if "segment_start_ts_utc" in out_df.columns:
        out_df["segment_start_ts_utc"] = pd.to_datetime(out_df["segment_start_ts_utc"], utc=True, errors="coerce")
        out_df = out_df.sort_values(["segment_start_ts_utc", "sample_id"], kind="mergesort").reset_index(drop=True)
    return out_df


def _plot_actuator_window(
    df: pd.DataFrame,
    *,
    time_col: str,
    target_cols: Sequence[str],
    day: str,
    timezone: str,
    out_png: Path,
) -> None:
    try:
        import matplotlib.dates as mdates  # type: ignore
        import matplotlib.pyplot as plt  # type: ignore
        from matplotlib.patches import Patch  # type: ignore
    except Exception as e:  # pragma: no cover
        raise SystemExit("Missing matplotlib. Install: pip install matplotlib") from e

    times = pd.to_datetime(df[time_col], utc=True, errors="coerce").dt.tz_convert(timezone)
    if times.isna().any():
        raise ValueError(f"Invalid timestamps found in {time_col}")

    def _binary_intervals(ts: pd.Series, vals: pd.Series) -> List[Tuple[float, float]]:
        tser = pd.to_datetime(ts, errors="coerce")
        vser = pd.to_numeric(vals, errors="coerce").fillna(0.0)
        if len(tser) == 0:
            return []
        tnum = mdates.date2num(tser.dt.to_pydatetime())
        if len(tnum) == 1:
            default_w = float(pd.Timedelta(seconds=1) / pd.Timedelta(days=1))
            next_widths = np.asarray([default_w], dtype=np.float64)
        else:
            next_widths = np.diff(tnum)
            fallback = float(np.median(next_widths[next_widths > 0])) if np.any(next_widths > 0) else float(
                pd.Timedelta(seconds=1) / pd.Timedelta(days=1)
            )
            next_widths = np.concatenate([next_widths, np.asarray([fallback], dtype=np.float64)])

        intervals: List[Tuple[float, float]] = []
        start_num: Optional[float] = None
        acc_width = 0.0
        prev_on = False
        for i, raw_v in enumerate(vser.to_numpy(dtype=np.float64, copy=False)):
            is_on = bool(raw_v >= 0.5)
            width = float(max(next_widths[i], 0.0))
            if is_on and not prev_on:
                start_num = float(tnum[i])
                acc_width = width
            elif is_on and prev_on:
                acc_width += width
            elif (not is_on) and prev_on and start_num is not None:
                intervals.append((start_num, max(acc_width, 1e-9)))
                start_num = None
                acc_width = 0.0
            prev_on = is_on
        if prev_on and start_num is not None:
            intervals.append((start_num, max(acc_width, 1e-9)))
        return intervals

    fig, ax = plt.subplots(1, 1, figsize=(16, max(5.0, 1.1 * len(target_cols) * 2.0)), constrained_layout=True)
    lane_h = 0.36
    group_gap = 0.32
    lane_gap = 0.10
    ytick_pos: List[float] = []
    ytick_lab: List[str] = []
    real_color = "#1f77b4"
    pred_color = "#d62728"

    for i, col in enumerate(target_cols):
        true_col = col
        pred_col = f"pred__{col}"
        if true_col not in df.columns:
            raise ValueError(f"Missing truth column for plotting: {true_col}")
        if pred_col not in df.columns:
            raise ValueError(f"Missing prediction column for plotting: {pred_col}")
        yt = pd.to_numeric(df[true_col], errors="coerce")
        yp = pd.to_numeric(df[pred_col], errors="coerce")
        mismatch = ((yt - yp).abs() > 1e-9)
        match_ratio = float((~mismatch).mean()) if len(mismatch) else float("nan")
        base_y = float((len(target_cols) - 1 - i) * (2.0 * lane_h + lane_gap + group_gap))
        real_y = base_y + lane_h + lane_gap
        pred_y = base_y

        true_intervals = _binary_intervals(times, yt)
        pred_intervals = _binary_intervals(times, yp)
        if true_intervals:
            ax.broken_barh(true_intervals, (real_y, lane_h), facecolors=real_color, edgecolors="none", alpha=0.88)
        if pred_intervals:
            ax.broken_barh(pred_intervals, (pred_y, lane_h), facecolors=pred_color, edgecolors="none", alpha=0.72)

        group_center = base_y + lane_h + (lane_gap / 2.0)
        label_x = float(mdates.date2num(times.iloc[0].to_pydatetime()))
        ax.text(
            label_x,
            group_center + lane_h * 0.95,
            f"{col.replace('_duty_target', '')}  match={match_ratio:.1%}",
            fontsize=9,
            color="#333333",
            ha="left",
            va="bottom",
        )
        ytick_pos.extend([real_y + lane_h / 2.0, pred_y + lane_h / 2.0])
        ytick_lab.extend(["real", "pred"])

    ax.set_title(f"Bluerock rpi_audio actuator states on {day} ({timezone})")
    ax.set_yticks(ytick_pos)
    ax.set_yticklabels(ytick_lab)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M", tz=times.dt.tz))
    ax.set_xlabel(f"Time ({timezone})")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(
        handles=[
            Patch(facecolor=real_color, edgecolor="none", alpha=0.88, label="real"),
            Patch(facecolor=pred_color, edgecolor="none", alpha=0.72, label="predicted"),
        ],
        loc="upper right",
    )
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=180)
    plt.close(fig)


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Run a pretrained actuation model on a single day window and plot real vs predicted actuator states."
    )
    p.add_argument("--dataset", required=True, help="samples.parquet path")
    p.add_argument("--embeddings-npz", required=True, help="Aligned embeddings npz path")
    p.add_argument("--embeddings-key", default="embeddings")
    p.add_argument("--model", required=True, help="Path to audio_pretrained_embedding_multitask_best.pt")
    p.add_argument("--day", default="2025-07-04", help="Local calendar day to plot, format YYYY-MM-DD")
    p.add_argument("--timezone", default="UTC", help="Timezone used to interpret --day and plot axis")
    p.add_argument("--time-col", default="segment_start_ts_utc")
    p.add_argument("--source-col", default="audio_source")
    p.add_argument("--source-value", default="rpi_audio")
    p.add_argument("--target-cols", default=",".join(DEFAULT_TARGET_COLS))
    p.add_argument("--batch-size", type=int, default=1024)
    p.add_argument("--out-parquet", required=True, help="Output parquet with predictions for the filtered day window")
    p.add_argument("--out-png", required=True, help="Output PNG path for real vs predicted actuator plot")
    p.add_argument("--out-json", default="", help="Optional metadata JSON output")
    args = p.parse_args()

    dataset_path = Path(args.dataset)
    embeddings_path = Path(args.embeddings_npz)
    model_path = Path(args.model)
    target_cols = _parse_csv(args.target_cols)
    start_utc, end_utc = _build_day_window(str(args.day), str(args.timezone))

    ckpt = _load_checkpoint(model_path)
    task_mode = str(ckpt.get("task_mode", "multiclass")).strip().lower()
    if task_mode != "multilabel":
        raise SystemExit(f"This script currently expects a multilabel actuation checkpoint, got task_mode={task_mode!r}")
    target_cols = _resolve_target_cols(ckpt, target_cols)

    df_all = pd.read_parquet(dataset_path).reset_index(drop=True)
    df_window = _filter_window(
        df_all,
        time_col=str(args.time_col),
        source_col=str(args.source_col),
        source_value=str(args.source_value),
        start_utc=start_utc,
        end_utc=end_utc,
    )

    out_df = _infer_multitask_dataset(
        df_window,
        embeddings_path=embeddings_path,
        embeddings_key=str(args.embeddings_key),
        dataset_len=len(df_all),
        ckpt=ckpt,
        batch_size=int(args.batch_size),
        target_cols=target_cols,
    )

    out_parquet = Path(args.out_parquet)
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(out_parquet, index=False)

    _plot_actuator_window(
        out_df,
        time_col=str(args.time_col),
        target_cols=target_cols,
        day=str(args.day),
        timezone=str(args.timezone),
        out_png=Path(args.out_png),
    )

    if str(args.out_json).strip():
        _write_json(
            Path(args.out_json),
            {
                "dataset": str(dataset_path),
                "embeddings_npz": str(embeddings_path),
                "model": str(model_path),
                "source_col": str(args.source_col),
                "source_value": str(args.source_value),
                "day": str(args.day),
                "timezone": str(args.timezone),
                "window_start_utc": start_utc.isoformat(),
                "window_end_utc": end_utc.isoformat(),
                "target_cols": target_cols,
                "task_mode": task_mode,
                "n_rows": int(len(out_df)),
                "out_parquet": str(out_parquet),
                "out_png": str(Path(args.out_png)),
            },
        )

    print(
        f"[ok] wrote {out_parquet} rows={len(out_df)} window=[{start_utc.isoformat()}, {end_utc.isoformat()})",
        flush=True,
    )
    print(f"[ok] wrote {Path(args.out_png)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
