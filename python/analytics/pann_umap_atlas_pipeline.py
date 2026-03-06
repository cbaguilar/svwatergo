#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence

import numpy as np
import pandas as pd

try:
    import umap  # type: ignore
except Exception as e:
    raise SystemExit("Missing umap-learn. Install with: pip install umap-learn") from e

from python.ml.train.audio_pca_svm_plot import render_audio_pca_svm_overview


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Build a UMAP projection from PANN embedding columns and render atlas plots "
            "using the existing audio projection plotter."
        )
    )
    p.add_argument("--input-parquet", action="append", required=True, help="Input parquet path(s), repeatable")
    p.add_argument(
        "--embedding-col-regex",
        default=r"^(pann_|embed_|embedding_).+",
        help="Regex selecting embedding columns",
    )
    p.add_argument(
        "--embedding-cols",
        default="",
        help="Optional explicit comma-separated embedding columns (overrides regex).",
    )
    p.add_argument("--label-col", default="ropumprun_duty", help="Ground-truth column (numeric or on/off style)")
    p.add_argument("--pred-col", default="", help="Optional predicted label/duty column")
    p.add_argument("--score-col", default="", help="Optional positive-class score column")
    p.add_argument("--positive-threshold", type=float, default=0.5)

    p.add_argument("--umap-n-neighbors", type=int, default=15)
    p.add_argument("--umap-min-dist", type=float, default=0.1)
    p.add_argument("--umap-metric", default="euclidean")
    p.add_argument("--umap-random-state", type=int, default=42)
    p.add_argument("--umap-max-fit-points", type=int, default=0, help="If >0, fit on subsample and transform all")
    p.add_argument(
        "--umap-backend",
        default="auto",
        choices=["auto", "cpu", "gpu"],
        help="UMAP backend: cpu=umap-learn, gpu=RAPIDS cuML, auto=prefer gpu if available.",
    )

    p.add_argument("--max-points-plot", type=int, default=12000)
    p.add_argument("--feature-atlas", default="yes", choices=["yes", "no"])
    p.add_argument("--feature-regex", action="append", default=[])
    p.add_argument("--feature-max-cols", type=int, default=48)
    p.add_argument("--feature-pair", default="1:2")

    p.add_argument("--out-dir", default="data/derived/embeddings")
    p.add_argument("--prefix", default="pann_umap")
    p.add_argument("--title", default="PANN UMAP Atlas")
    return p


def _coerce_binary(s: pd.Series, threshold: float) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        x = pd.to_numeric(s, errors="coerce").fillna(0.0)
        return (x >= float(threshold)).astype(int)
    txt = s.astype(str).str.strip().str.lower()
    on = txt.isin({"1", "true", "t", "yes", "on", "running", "open"})
    return on.astype(int)


def _pick_embedding_cols(df: pd.DataFrame, explicit_csv: str, pattern: str) -> List[str]:
    if str(explicit_csv).strip():
        cols = [c.strip() for c in str(explicit_csv).split(",") if c.strip()]
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise SystemExit(f"Missing explicit embedding cols: {missing}")
        return cols
    rx = re.compile(str(pattern))
    cols = [c for c in df.columns if rx.search(c)]
    if not cols:
        raise SystemExit(f"No embedding columns matched --embedding-col-regex={pattern!r}")
    return cols


def _parse_feature_pair(s: str) -> tuple[int, int]:
    tok = str(s).strip()
    if ":" not in tok:
        raise SystemExit(f"Invalid --feature-pair {tok!r}; expected A:B")
    a, b = tok.split(":", 1)
    try:
        ia = int(a.strip())
        ib = int(b.strip())
    except Exception as e:
        raise SystemExit(f"Invalid --feature-pair {tok!r}; expected integer A:B") from e
    if ia < 1 or ib < 1:
        raise SystemExit("feature pair indices must be >= 1")
    return ia, ib


def main() -> None:
    args = build_argparser().parse_args()

    frames = [pd.read_parquet(Path(p)) for p in args.input_parquet]
    if not frames:
        raise SystemExit("No input frames loaded")
    df = pd.concat(frames, axis=0, ignore_index=True, sort=False)

    emb_cols = _pick_embedding_cols(df, args.embedding_cols, args.embedding_col_regex)
    x = df[emb_cols].apply(pd.to_numeric, errors="coerce")
    keep = x.notna().all(axis=1)
    if args.label_col in df.columns:
        keep &= df[args.label_col].notna()
    x = x.loc[keep].to_numpy(dtype=np.float32)
    work = df.loc[keep].copy().reset_index(drop=True)
    if len(work) < 10:
        raise SystemExit("Not enough valid rows after filtering")

    reducer, backend_used = _make_umap_reducer(
        backend=str(args.umap_backend),
        n_neighbors=int(args.umap_n_neighbors),
        min_dist=float(args.umap_min_dist),
        metric=str(args.umap_metric),
        random_state=int(args.umap_random_state),
    )
    max_fit = int(args.umap_max_fit_points)
    if max_fit > 0 and len(x) > max_fit:
        rng = np.random.default_rng(int(args.umap_random_state))
        idx = rng.choice(len(x), size=max_fit, replace=False)
        reducer.fit(x[idx])
        z = reducer.transform(x)
    else:
        z = reducer.fit_transform(x)
    z = np.asarray(z, dtype=np.float32)

    proj = work.copy()
    proj["pca1"] = z[:, 0].astype("float64")
    proj["pca2"] = z[:, 1].astype("float64")
    proj["pca3"] = 0.0

    if args.label_col not in proj.columns:
        raise SystemExit(f"--label-col not found: {args.label_col}")
    proj["y_true"] = _coerce_binary(proj[args.label_col], float(args.positive_threshold))

    if str(args.pred_col).strip() and args.pred_col in proj.columns:
        proj["y_pred"] = _coerce_binary(proj[args.pred_col], float(args.positive_threshold))
    elif str(args.score_col).strip() and args.score_col in proj.columns:
        proj["score_positive"] = pd.to_numeric(proj[args.score_col], errors="coerce").fillna(0.0).astype("float64")
        proj["y_pred"] = (proj["score_positive"] >= float(args.positive_threshold)).astype(int)
    else:
        proj["y_pred"] = proj["y_true"].astype(int)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_projection = out_dir / f"{args.prefix}_train_projection.parquet"
    out_png = out_dir / f"{args.prefix}_atlas.png"
    out_meta = out_dir / f"{args.prefix}_atlas.json"
    out_umap_meta = out_dir / f"{args.prefix}_umap_meta.json"

    proj.to_parquet(out_projection, index=False)

    feature_pair = _parse_feature_pair(args.feature_pair)
    res = render_audio_pca_svm_overview(
        projection_path=out_projection,
        out_png=out_png,
        out_meta=out_meta,
        title=str(args.title),
        max_points=int(args.max_points_plot),
        pc_pairs=[(1, 2)],
        feature_atlas=(str(args.feature_atlas) == "yes"),
        feature_regex=list(args.feature_regex or []),
        feature_max_cols=int(args.feature_max_cols),
        feature_pair=feature_pair,
    )

    meta: Dict[str, Any] = {
        "input_parquet": list(args.input_parquet),
        "rows_in": int(len(df)),
        "rows_used": int(len(work)),
        "embedding_cols": emb_cols,
        "label_col": str(args.label_col),
        "pred_col": str(args.pred_col),
        "score_col": str(args.score_col),
        "positive_threshold": float(args.positive_threshold),
        "umap": {
            "backend_used": backend_used,
            "n_neighbors": int(args.umap_n_neighbors),
            "min_dist": float(args.umap_min_dist),
            "metric": str(args.umap_metric),
            "random_state": int(args.umap_random_state),
            "max_fit_points": int(args.umap_max_fit_points),
        },
        "artifacts": {
            "projection_parquet": str(out_projection),
            "atlas_png": str(out_png),
            "atlas_json": str(out_meta),
            "plotter_result": res,
        },
    }
    out_umap_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"[OK] wrote {out_projection}")
    print(f"[OK] wrote {out_png}")
    print(f"[OK] wrote {out_meta}")
    print(f"[OK] wrote {out_umap_meta}")


def _make_umap_reducer(
    *,
    backend: str,
    n_neighbors: int,
    min_dist: float,
    metric: str,
    random_state: int,
) -> tuple[Any, str]:
    b = str(backend).strip().lower()
    if b not in {"auto", "cpu", "gpu"}:
        raise SystemExit(f"Unsupported --umap-backend={backend!r}")

    if b in {"auto", "gpu"}:
        try:
            from cuml.manifold import UMAP as cuUMAP  # type: ignore

            reducer = cuUMAP(
                n_components=2,
                n_neighbors=int(n_neighbors),
                min_dist=float(min_dist),
                metric=str(metric),
                random_state=int(random_state),
            )
            return reducer, "gpu_cuml"
        except Exception as e:
            if b == "gpu":
                raise SystemExit(f"Requested --umap-backend=gpu but RAPIDS cuML UMAP unavailable: {e}") from e

    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=int(n_neighbors),
        min_dist=float(min_dist),
        metric=str(metric),
        random_state=int(random_state),
    )
    return reducer, "cpu_umap_learn"


if __name__ == "__main__":
    main()
