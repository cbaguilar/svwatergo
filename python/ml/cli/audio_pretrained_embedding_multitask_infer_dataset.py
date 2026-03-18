from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from ..train.audio_pretrained_embedding_multitask import (
    AudioPretrainedEmbeddingMultitaskModelFactory,
    _coerce_binary_targets,
)
from ..train.audio_pca_svm import _coerce_target


def _filter_df(
    df: pd.DataFrame,
    *,
    filter_col: str,
    filter_values: Sequence[str],
) -> pd.DataFrame:
    values = [str(v).strip() for v in filter_values if str(v).strip()]
    if not values:
        return df
    col = str(filter_col).strip()
    if not col:
        raise ValueError("filter_col must be set when filter_values are provided")
    if col not in df.columns:
        raise ValueError(f"Missing filter_col in dataset: {col}")
    mask = df[col].astype(str).isin(values)
    out = df.loc[mask].copy()
    if out.empty:
        raise ValueError(f"No rows matched {col} in [{', '.join(values)}]")
    print(f"[filter] col={col} values={values} rows={len(out)}/{len(df)}", flush=True)
    return out


def _source_filter_df(
    df: pd.DataFrame,
    *,
    source_filter_col: str,
    source_filter_values: Sequence[str],
) -> pd.DataFrame:
    values = [str(v).strip() for v in source_filter_values if str(v).strip()]
    if not values:
        return df
    col = str(source_filter_col).strip()
    if not col:
        raise ValueError("source_filter_col must be set when source_filter_values are provided")
    if col not in df.columns:
        raise ValueError(f"Missing source_filter_col in dataset: {col}")
    mask = df[col].astype(str).isin(values)
    out = df.loc[mask].copy()
    if out.empty:
        raise ValueError(f"No rows matched {col} in [{', '.join(values)}]")
    print(f"[source_filter] col={col} values={values} rows={len(out)}/{len(df)}", flush=True)
    return out


def _load_checkpoint(path: Path) -> Dict[str, object]:
    try:
        import torch  # type: ignore
    except Exception as e:
        raise SystemExit("Missing torch. Install: pip install torch") from e
    obj = torch.load(str(path), map_location="cpu")
    if not isinstance(obj, dict) or "state_dict" not in obj:
        raise ValueError(f"Invalid checkpoint bundle: {path}")
    return obj


def _select_metadata_cols(df: pd.DataFrame, *, extra_cols: Optional[Sequence[str]] = None) -> List[str]:
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
    extra = [str(c) for c in df.columns if str(c).startswith("state__") and str(c) not in keep]
    for c in (extra_cols or []):
        cs = str(c).strip()
        if cs and cs in df.columns and cs not in keep and cs not in extra:
            extra.append(cs)
    return keep + extra


def _attach_truth(
    df: pd.DataFrame,
    *,
    task_mode: str,
    target_col: Optional[str],
    target_cols: Sequence[str],
) -> pd.DataFrame:
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
    elif mode == "multiregression":
        cols = [str(c).strip() for c in target_cols if str(c).strip()]
        if cols and all(c in out.columns for c in cols):
            for name in cols:
                out[f"true__{name}"] = pd.to_numeric(out[name], errors="coerce").astype(np.float32)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Infer over an existing samples.parquet + embedding cache with a multitask checkpoint")
    p.add_argument("--dataset", required=True, help="samples.parquet path")
    p.add_argument("--embeddings-npz", required=True, help="Aligned embeddings npz path")
    p.add_argument("--embeddings-key", default="embeddings")
    p.add_argument("--model", required=True, help="Path to audio_pretrained_embedding_multitask_best.pt or last checkpoint")
    p.add_argument("--out-parquet", required=True, help="Output parquet with predictions per window")
    p.add_argument("--out-json", default="", help="Optional compact metadata JSON path")
    p.add_argument("--filter-col", default="", help="Optional column to filter before inference")
    p.add_argument("--filter-values", default="", help="Optional comma-separated values for --filter-col")
    p.add_argument("--source-filter-col", default="", help="Optional source column to filter before inference")
    p.add_argument("--source-filter-values", default="", help="Optional comma-separated values for --source-filter-col")
    p.add_argument("--batch-size", type=int, default=1024)
    args = p.parse_args()

    ckpt = _load_checkpoint(Path(args.model))
    mode = str(ckpt.get("task_mode", "multiclass")).strip().lower()
    if mode not in ("multiclass", "multilabel", "multiregression"):
        raise SystemExit(f"Unsupported task_mode for dataset inference: {mode!r}")

    df = pd.read_parquet(str(Path(args.dataset))).reset_index(drop=True)
    df = _filter_df(
        df,
        filter_col=str(args.filter_col),
        filter_values=[x.strip() for x in str(args.filter_values).split(",") if x.strip()],
    )
    df = _source_filter_df(
        df,
        source_filter_col=str(args.source_filter_col),
        source_filter_values=[x.strip() for x in str(args.source_filter_values).split(",") if x.strip()],
    )

    z = np.load(str(Path(args.embeddings_npz)))
    emb_key = str(args.embeddings_key or "embeddings").strip() or "embeddings"
    if emb_key not in z.files:
        raise SystemExit(f"Embeddings key {emb_key!r} not found in {args.embeddings_npz}. Available: {list(z.files)}")
    X_full = np.asarray(z[emb_key], dtype=np.float32)
    if int(X_full.shape[0]) != int(len(pd.read_parquet(str(Path(args.dataset))))):
        raise SystemExit("Embedding cache rows do not match original dataset rows.")
    row_idx = df.index.to_numpy(dtype=np.int64, copy=False)
    X = np.asarray(X_full[row_idx], dtype=np.float32, copy=False)
    df = df.reset_index(drop=True)

    hidden = [int(x) for x in (ckpt.get("hidden") or [])]
    z_dim = int(ckpt.get("z_dim", 64))
    input_dim = int(ckpt.get("input_dim", int(X.shape[1])))
    y_dim = int(ckpt.get("n_targets", 0))
    plc_dim = 0

    try:
        import torch  # type: ignore
    except Exception as e:
        raise SystemExit("Missing torch. Install: pip install torch") from e

    model = AudioPretrainedEmbeddingMultitaskModelFactory.build(
        in_dim=input_dim,
        hidden=hidden,
        z_dim=z_dim,
        y_dim=y_dim,
        plc_dim=plc_dim,
        drop=0.0,
    )
    model.load_state_dict(ckpt["state_dict"], strict=False)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.eval()
    print(f"[device] inference using {device}", flush=True)

    class_names = [str(x) for x in (ckpt.get("class_names") or [])]
    target_col = (str(ckpt.get("target_col") or "").strip() or None)
    target_cols = [str(x) for x in (ckpt.get("target_cols") or []) if str(x).strip()]
    reg_mean = np.asarray(ckpt.get("regression_target_mean") or [], dtype=np.float32)
    reg_std = np.asarray(ckpt.get("regression_target_std") or [], dtype=np.float32)

    rows: List[pd.DataFrame] = []
    X_t = torch.from_numpy(np.asarray(X, dtype=np.float32))
    bs = max(1, int(args.batch_size))
    with torch.no_grad():
        for i0 in range(0, int(X_t.shape[0]), bs):
            xb = X_t[i0 : i0 + bs].to(device)
            logits, z_latent, _ = model(xb)
            batch_df = df.iloc[i0 : i0 + len(xb)].copy()
            batch_df = batch_df[_select_metadata_cols(batch_df, extra_cols=([target_col] if target_col else []) + target_cols)]

            if mode == "multiclass":
                probs = torch.softmax(logits, dim=1).cpu().numpy().astype(np.float32, copy=False)
                pred_idx = np.argmax(probs, axis=1).astype(np.int64, copy=False)
                pred_label = [
                    class_names[i] if class_names and 0 <= int(i) < len(class_names) else str(int(i))
                    for i in pred_idx.tolist()
                ]
                batch_df["pred_index"] = pred_idx
                batch_df["pred_label"] = pred_label
                batch_df["pred_confidence"] = np.max(probs, axis=1).astype(np.float32, copy=False)
                entropy = -np.sum(probs * np.log(np.clip(probs, 1e-12, 1.0)), axis=1)
                batch_df["pred_entropy"] = entropy.astype(np.float32, copy=False)
                for j in range(probs.shape[1]):
                    cname = class_names[j] if j < len(class_names) else f"class_{j}"
                    batch_df[f"prob__{cname}"] = probs[:, j]
            elif mode == "multilabel":
                probs = torch.sigmoid(logits).cpu().numpy().astype(np.float32, copy=False)
                preds = (probs >= 0.5).astype(np.int64, copy=False)
                batch_df["pred_confidence"] = np.max(np.maximum(probs, 1.0 - probs), axis=1).astype(np.float32, copy=False)
                entropy = -(
                    probs * np.log(np.clip(probs, 1e-12, 1.0))
                    + (1.0 - probs) * np.log(np.clip(1.0 - probs, 1e-12, 1.0))
                ).mean(axis=1)
                batch_df["pred_entropy"] = entropy.astype(np.float32, copy=False)
                batch_df["pred_bits"] = ["|".join(str(int(v)) for v in row.tolist()) for row in preds]
                batch_df["pred_label"] = [
                    "|".join(f"{name}={'on' if int(v) == 1 else 'off'}" for name, v in zip(target_cols, row.tolist()))
                    for row in preds
                ]
                for j, name in enumerate(target_cols):
                    batch_df[f"prob__{name}"] = probs[:, j]
                    batch_df[f"pred__{name}"] = preds[:, j]
            else:
                pred = logits.cpu().numpy().astype(np.float32, copy=False)
                if reg_mean.size and reg_std.size and reg_mean.shape[0] == pred.shape[1] and reg_std.shape[0] == pred.shape[1]:
                    pred = (pred * reg_std.reshape(1, -1)) + reg_mean.reshape(1, -1)
                for j, name in enumerate(target_cols):
                    batch_df[f"pred__{name}"] = pred[:, j].astype(np.float32, copy=False)

            for j in range(int(z_latent.shape[1])):
                batch_df[f"latent_{j:03d}"] = z_latent[:, j].detach().cpu().numpy().astype(np.float32, copy=False)
            rows.append(batch_df)

    out_df = pd.concat(rows, axis=0, ignore_index=True, sort=False)
    out_df = _attach_truth(out_df, task_mode=mode, target_col=target_col, target_cols=target_cols)
    if "segment_start_ts_utc" in out_df.columns:
        out_df["segment_start_ts_utc"] = pd.to_datetime(out_df["segment_start_ts_utc"], utc=True, errors="coerce")
        out_df = out_df.sort_values(["segment_start_ts_utc", "sample_id"], kind="mergesort").reset_index(drop=True)
    out_path = Path(args.out_parquet)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(out_path, index=False)

    if str(args.out_json).strip():
        meta = {
            "model": str(Path(args.model)),
            "dataset": str(Path(args.dataset)),
            "embeddings_npz": str(Path(args.embeddings_npz)),
            "task_mode": mode,
            "target_col": target_col,
            "target_cols": target_cols,
            "class_names": class_names,
            "n_rows": int(len(out_df)),
            "out_parquet": str(out_path),
        }
        meta_path = Path(args.out_json)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"[ok] wrote {out_path} rows={len(out_df)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
