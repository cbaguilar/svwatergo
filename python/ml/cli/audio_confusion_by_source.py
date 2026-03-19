#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix

from python.analytics.site_alias import alias_site_names

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build confusion-matrix atlas by datasource from train_projection.parquet")
    p.add_argument("--projection-path", required=True, help="Path to train_projection.parquet")
    p.add_argument("--metrics-path", default=None, help="Optional audio_tiny_cnn_metrics.json for task/classes/thresholds")
    p.add_argument("--split", default="test", choices=["train", "test", "val", "all"])
    p.add_argument("--source-col", default=None, help="Optional override source column")
    p.add_argument("--threshold", type=float, default=None, help="Optional global threshold override for score columns")
    p.add_argument(
        "--use-score",
        action="store_true",
        help="Use score columns + threshold instead of y_pred columns when available",
    )
    p.add_argument("--out-dir", default=None, help="Output dir (default: alongside projection path)")
    p.add_argument("--prefix", default="confusion_by_source")
    return p


def _find_source_col(df: pd.DataFrame, requested: str | None) -> str:
    if requested:
        if requested not in df.columns:
            raise SystemExit(f"--source-col not found: {requested}")
        return requested
    for c in ("audio_source", "source_name", "source", "source_label"):
        if c in df.columns:
            return c
    return "__source_unknown"


def _plot_grid(entries: List[Tuple[str, np.ndarray, int]], labels: List[str], title: str, out_png: Path) -> bool:
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
    axes_arr = np.asarray([axes], dtype=object) if not isinstance(axes, np.ndarray) else axes.reshape(-1)
    vmax = max(float(np.max(cm)) for _, cm, _ in entries)
    vmax = max(vmax, 1.0)
    for i, (src, cm, n_rows) in enumerate(entries):
        ax = axes_arr[i]
        mat = np.asarray(cm, dtype=np.int64)
        ax.imshow(mat, cmap="Blues", vmin=0.0, vmax=vmax)
        ax.set_title(alias_site_names(f"{src}\nn={n_rows}"), fontsize=9)
        ax.set_xlabel("Pred")
        ax.set_ylabel("True")
        ticks = np.arange(len(labels))
        ax.set_xticks(ticks)
        ax.set_yticks(ticks)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax.set_yticklabels(labels, fontsize=8)
        for r in range(mat.shape[0]):
            for c in range(mat.shape[1]):
                v = int(mat[r, c])
                color = "white" if v > (0.55 * vmax) else "black"
                ax.text(c, r, str(v), ha="center", va="center", fontsize=8, color=color)
    for j in range(len(entries), len(axes_arr)):
        axes_arr[j].axis("off")
    fig.suptitle(alias_site_names(title))
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)
    return True


def _counts(cm: np.ndarray) -> Dict[str, int]:
    m = np.asarray(cm, dtype=np.int64)
    d: Dict[str, int] = {"total": int(np.sum(m))}
    if m.shape == (2, 2):
        d.update({"tn": int(m[0, 0]), "fp": int(m[0, 1]), "fn": int(m[1, 0]), "tp": int(m[1, 1])})
    return d


def main() -> None:
    args = _build_argparser().parse_args()
    proj_path = Path(args.projection_path)
    if not proj_path.exists():
        raise SystemExit(f"projection file not found: {proj_path}")
    out_dir = Path(args.out_dir) if args.out_dir else proj_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics: Dict[str, Any] = {}
    if args.metrics_path:
        mp = Path(args.metrics_path)
        if mp.exists():
            metrics = json.loads(mp.read_text(encoding="utf-8"))

    df = pd.read_parquet(proj_path)
    if "split" in df.columns and args.split != "all":
        df = df[df["split"].astype(str).str.lower() == str(args.split).lower()].copy()
    if df.empty:
        raise SystemExit("No rows after split filtering")

    src_col = _find_source_col(df, args.source_col)
    if src_col == "__source_unknown":
        df[src_col] = "unknown"
    df[src_col] = df[src_col].astype(str).fillna("unknown")

    task = str(metrics.get("task", "binary")).strip().lower()
    threshold_default = float(metrics.get("inference_threshold_default", 0.5))
    threshold = float(args.threshold) if args.threshold is not None else threshold_default

    out: Dict[str, Any] = {
        "projection_path": str(proj_path),
        "metrics_path": str(args.metrics_path) if args.metrics_path else None,
        "split": str(args.split),
        "task": task,
        "source_col": src_col,
    }

    if task == "multilabel":
        classes = []
        y_meta = metrics.get("y_meta")
        if isinstance(y_meta, dict) and isinstance(y_meta.get("classes"), list):
            classes = [str(c) for c in y_meta.get("classes")]
        if not classes:
            classes = sorted([c[len("y_true_") :] for c in df.columns if c.startswith("y_true_")])
        if not classes:
            raise SystemExit("Could not infer multilabel class columns")
        thresholds = metrics.get("inference_thresholds")
        thr_by_class: Dict[str, float] = {}
        if isinstance(thresholds, list) and len(thresholds) == len(classes):
            thr_by_class = {classes[i]: float(thresholds[i]) for i in range(len(classes))}
        else:
            thr_by_class = {c: float(threshold) for c in classes}

        by_source: Dict[str, Any] = {}
        atlas_paths: Dict[str, str] = {}
        for cls in classes:
            c_true = f"y_true_{cls}"
            c_pred = f"y_pred_{cls}"
            c_score = f"score_{cls}"
            if c_true not in df.columns:
                continue
            if args.use_score and c_score in df.columns:
                yp_all = (pd.to_numeric(df[c_score], errors="coerce").fillna(0.0) >= float(thr_by_class[cls])).astype(int)
            elif c_pred in df.columns:
                yp_all = pd.to_numeric(df[c_pred], errors="coerce").fillna(0.0).astype(int)
            else:
                raise SystemExit(f"Missing prediction columns for class={cls}; need {c_pred} or {c_score}")
            yt_all = pd.to_numeric(df[c_true], errors="coerce").fillna(0.0).astype(int)

            entries: List[Tuple[str, np.ndarray, int]] = []
            cls_out: Dict[str, Any] = {}
            for src, g in df.groupby(src_col):
                yt = yt_all.loc[g.index].to_numpy(dtype=np.int64)
                yp = yp_all.loc[g.index].to_numpy(dtype=np.int64)
                cm = confusion_matrix(yt, yp, labels=[0, 1]).astype(np.int64)
                cls_out[str(src)] = {"n_rows": int(len(g)), "labels": ["0", "1"], "matrix": cm.tolist(), "counts": _counts(cm)}
                entries.append((str(src), cm, int(len(g))))
            by_source[cls] = cls_out

            png = out_dir / f"{args.prefix}_{args.split}_{cls}.png"
            if _plot_grid(entries, ["0", "1"], f"{args.split} confusion by source ({cls})", png):
                atlas_paths[cls] = str(png)

        out["thresholds_by_class"] = thr_by_class
        out["by_label"] = by_source
        if atlas_paths:
            out["atlases"] = atlas_paths
    else:
        if "y_true" not in df.columns:
            raise SystemExit("projection must contain y_true")
        if args.use_score and "score_positive" in df.columns:
            y_pred_ser = (pd.to_numeric(df["score_positive"], errors="coerce").fillna(0.0) >= float(threshold)).astype(int)
        elif "y_pred" in df.columns:
            y_pred_ser = pd.to_numeric(df["y_pred"], errors="coerce").fillna(0.0).astype(int)
        else:
            raise SystemExit("projection must contain y_pred or score_positive")

        y_true_ser = pd.to_numeric(df["y_true"], errors="coerce").fillna(0.0).astype(int)
        if task == "binary":
            labels = [0, 1]
            label_names = ["0", "1"]
        else:
            labels = sorted(set(y_true_ser.tolist()) | set(y_pred_ser.tolist()))
            label_names = [str(v) for v in labels]
        entries = []
        by_source = {}
        for src, g in df.groupby(src_col):
            yt = y_true_ser.loc[g.index].to_numpy(dtype=np.int64)
            yp = y_pred_ser.loc[g.index].to_numpy(dtype=np.int64)
            cm = confusion_matrix(yt, yp, labels=labels).astype(np.int64)
            by_source[str(src)] = {
                "n_rows": int(len(g)),
                "labels": label_names,
                "matrix": cm.tolist(),
                "counts": _counts(cm),
            }
            entries.append((str(src), cm, int(len(g))))

        png = out_dir / f"{args.prefix}_{args.split}.png"
        atlas_ok = _plot_grid(entries, label_names, f"{args.split} confusion by source", png)
        out["threshold"] = float(threshold)
        out["use_score"] = bool(args.use_score)
        out["by_source"] = by_source
        if atlas_ok:
            out["atlas"] = str(png)

    out_json = out_dir / f"{args.prefix}_{args.split}.json"
    out_json.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[OK] wrote {out_json}")
    if "atlas" in out:
        print(f"[OK] wrote {out['atlas']}")
    if isinstance(out.get("atlases"), dict):
        print(f"[OK] wrote {len(out['atlases'])} class atlases")


if __name__ == "__main__":
    main()
