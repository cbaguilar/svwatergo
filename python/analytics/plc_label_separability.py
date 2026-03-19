#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def _ensure_repo_on_syspath() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


_ensure_repo_on_syspath()

from python.analytics.window_pca.selection import select_pca_columns


LABEL_CANDIDATES: Tuple[str, ...] = (
    "state__mode",
    "state__mode_tw",
    "state_mode",
    "primary_class",
    "state",
    "mode",
)

FEATURE_SET_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("raw_window", r"^$"),
    ("plc_pca", r"^plc_pca(\d+)$"),
    ("plc_true", r"^plc_true_pc(\d+)$"),
    ("plc_pred", r"^plc_pred_pc(\d+)$"),
    ("pca", r"^pca(\d+)$"),
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Measure class separability for state/mode labels from an existing PLC PCA parquet. "
            "Supports dataset PLC PCA columns (plc_pca1, ...) and true/pred PLC PCA exports "
            "(plc_true_pc1, plc_pred_pc1, ...)."
        )
    )
    p.add_argument("--input", required=True, help="Input parquet path or URI")
    p.add_argument("--label-col", default="", help="Optional explicit label column")
    p.add_argument(
        "--feature-set",
        default="auto",
        choices=["auto", "raw_window", "plc_pca", "plc_true", "plc_pred", "pca"],
        help="Which PCA feature family to score; auto scores every detected set",
    )
    p.add_argument(
        "--feature-cols",
        default="",
        help="Optional explicit comma-separated PCA columns; overrides --feature-set detection",
    )
    p.add_argument("--split-col", default="split", help="Optional split column for filtering")
    p.add_argument("--split-values", default="", help="Optional comma-separated split filter")
    p.add_argument("--drop-labels", default="unknown,<NA>,nan,None", help="Comma-separated labels to drop")
    p.add_argument("--min-class-rows", type=int, default=5, help="Drop classes with fewer rows than this")
    p.add_argument("--max-rows", type=int, default=50000, help="Optional cap for metric computation")
    p.add_argument("--sample-seed", type=int, default=42)
    p.add_argument("--cv-folds", type=int, default=5)
    p.add_argument("--out-json", default="", help="Optional output JSON path")
    return p.parse_args()


def _default_raw_window_cols(df: pd.DataFrame, label_col: str) -> List[str]:
    always_exclude = [
        "sample_id",
        "site",
        "audio_source",
        "source",
        "source_name",
        "camera",
        "day_utc",
        "segment_path",
        "segment_start_ts_utc",
        "segment_end_ts_utc",
        "window_start_ts",
        "window_end_ts",
        "mel_shard_path",
        "mel_local_path",
        "mel_shard_local_index",
        "event_window_id",
        "split_group_id",
        "split",
        "split_seed",
        "actuation_combo",
        "actuation_bits",
        "actuation_unknown",
        "has_mel",
        "window_seconds",
        "n_rows",
        label_col,
    ]
    always_exclude.extend(
        [
            c
            for c in df.columns
            if str(c).startswith("plc_pca")
            or str(c).startswith("plc_true_pc")
            or str(c).startswith("plc_pred_pc")
            or str(c).startswith("pca")
        ]
    )
    always_exclude.extend([c for c in df.columns if str(c).endswith("_state")])
    always_exclude.extend([c for c in df.columns if str(c).endswith("_duty_target")])
    return select_pca_columns(
        df,
        explicit_cols=None,
        include_regex=None,
        exclude_regex=None,
        always_exclude=always_exclude,
    )


def _resolve_label_col(df: pd.DataFrame, explicit: str) -> str:
    col = str(explicit).strip()
    if col:
        if col not in df.columns:
            raise SystemExit(f"label column not found: {col}")
        return col
    for candidate in LABEL_CANDIDATES:
        if candidate in df.columns:
            return candidate
    raise SystemExit(
        "could not infer label column; tried: " + ", ".join(LABEL_CANDIDATES)
    )


def _ordered_numeric_suffix_cols(df: pd.DataFrame, pattern: str) -> List[str]:
    import re

    found: List[Tuple[int, str]] = []
    for col in df.columns:
        m = re.match(pattern, str(col))
        if m is None:
            continue
        found.append((int(m.group(1)), str(col)))
    found.sort(key=lambda x: x[0])
    return [col for _, col in found]


def _detect_feature_sets(df: pd.DataFrame, feature_set: str, explicit_cols: str) -> Dict[str, List[str]]:
    cols_explicit = [c.strip() for c in str(explicit_cols).split(",") if c.strip()]
    if cols_explicit:
        missing = [c for c in cols_explicit if c not in df.columns]
        if missing:
            raise SystemExit(f"explicit feature columns missing: {', '.join(missing)}")
        return {"explicit": cols_explicit}

    requested = str(feature_set).strip().lower()
    out: Dict[str, List[str]] = {}
    if requested in ("auto", "raw_window"):
        raw_cols = _default_raw_window_cols(df, label_col=_resolve_label_col(df, ""))
        if raw_cols:
            out["raw_window"] = raw_cols
    for name, pattern in FEATURE_SET_PATTERNS:
        if name == "raw_window":
            continue
        if requested != "auto" and requested != name:
            continue
        cols = _ordered_numeric_suffix_cols(df, pattern)
        if cols:
            out[name] = cols
    if out:
        return out
    raise SystemExit(
        "could not find PCA feature columns for requested feature set; "
        "looked for plc_pca*, plc_true_pc*, plc_pred_pc*, pca*"
    )


def _apply_filters(
    df: pd.DataFrame,
    *,
    label_col: str,
    split_col: str,
    split_values: Sequence[str],
    drop_labels: Sequence[str],
    min_class_rows: int,
) -> pd.DataFrame:
    out = df.copy()
    split_vals = [str(x).strip() for x in split_values if str(x).strip()]
    if split_vals:
        if split_col not in out.columns:
            raise SystemExit(f"split filter requested but split column not found: {split_col}")
        out = out.loc[out[split_col].astype(str).isin(split_vals)].copy()

    label_ser = out[label_col].astype("string")
    drop_set = {str(x).strip() for x in drop_labels if str(x).strip()}
    keep_mask = ~label_ser.astype(str).isin(drop_set)
    keep_mask &= label_ser.notna()
    out = out.loc[keep_mask].copy()
    if out.empty:
        raise SystemExit("no rows left after split/label filtering")

    counts = out[label_col].astype(str).value_counts()
    keep_labels = counts[counts >= int(min_class_rows)].index.tolist()
    out = out.loc[out[label_col].astype(str).isin(keep_labels)].copy()
    if out.empty:
        raise SystemExit("no rows left after dropping small classes")
    return out.reset_index(drop=True)


def _sample_rows(df: pd.DataFrame, max_rows: int, seed: int) -> pd.DataFrame:
    if int(max_rows) <= 0 or len(df) <= int(max_rows):
        return df.reset_index(drop=True)
    rng = np.random.default_rng(int(seed))
    idx = np.sort(rng.choice(np.arange(len(df), dtype=np.int64), size=int(max_rows), replace=False))
    return df.iloc[idx].reset_index(drop=True)


def _centroid_metrics(X: np.ndarray, y: np.ndarray) -> Dict[str, float | None]:
    labels = np.unique(y)
    if len(labels) < 2:
        return {
            "centroid_min_interclass_distance": None,
            "centroid_mean_interclass_distance": None,
            "within_class_rms_mean": None,
            "centroid_separation_ratio": None,
            "fisher_trace_ratio": None,
            "nearest_centroid_resub_accuracy": None,
        }

    centroids: List[np.ndarray] = []
    within_rms: List[float] = []
    correct = 0
    sw_trace = 0.0
    global_mean = np.mean(X, axis=0)
    sb_trace = 0.0
    for lab in labels:
        Xi = X[y == lab]
        mu = np.mean(Xi, axis=0)
        centroids.append(mu)
        d2 = np.sum((Xi - mu) ** 2, axis=1)
        within_rms.append(float(np.sqrt(np.mean(d2))) if len(d2) else 0.0)
        sw_trace += float(np.sum(d2))
        sb_trace += float(len(Xi) * np.sum((mu - global_mean) ** 2))
    C = np.vstack(centroids).astype(np.float64, copy=False)
    inter = np.sqrt(np.sum((C[:, None, :] - C[None, :, :]) ** 2, axis=2))
    inter_vals = inter[np.triu_indices(len(labels), k=1)]

    for i in range(len(X)):
        d = np.sqrt(np.sum((C - X[i]) ** 2, axis=1))
        pred = labels[int(np.argmin(d))]
        correct += int(pred == y[i])

    within_mean = float(np.mean(within_rms)) if within_rms else None
    min_inter = float(np.min(inter_vals)) if len(inter_vals) else None
    return {
        "centroid_min_interclass_distance": min_inter,
        "centroid_mean_interclass_distance": (float(np.mean(inter_vals)) if len(inter_vals) else None),
        "within_class_rms_mean": within_mean,
        "centroid_separation_ratio": (
            float(min_inter / within_mean) if min_inter is not None and within_mean is not None and within_mean > 0.0 else None
        ),
        "fisher_trace_ratio": (float(sb_trace / sw_trace) if sw_trace > 0.0 else None),
        "nearest_centroid_resub_accuracy": float(correct / len(X)) if len(X) else None,
    }


def _linear_probe_metrics(X: np.ndarray, y: np.ndarray, cv_folds: int, seed: int) -> Dict[str, float | int | None]:
    try:
        from sklearn.linear_model import LogisticRegression  # type: ignore
        from sklearn.metrics import accuracy_score, f1_score  # type: ignore
        from sklearn.model_selection import StratifiedKFold  # type: ignore
        from sklearn.pipeline import Pipeline  # type: ignore
        from sklearn.preprocessing import StandardScaler  # type: ignore
    except Exception as e:
        raise SystemExit("Missing scikit-learn. Install: pip install scikit-learn") from e

    class_counts = pd.Series(y).value_counts()
    min_count = int(class_counts.min()) if len(class_counts) else 0
    folds = int(max(2, min(int(cv_folds), min_count)))
    if len(np.unique(y)) < 2 or min_count < 2:
        return {
            "linear_probe_cv_folds": None,
            "linear_probe_accuracy_mean": None,
            "linear_probe_accuracy_std": None,
            "linear_probe_macro_f1_mean": None,
            "linear_probe_macro_f1_std": None,
        }

    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=int(seed))
    accs: List[float] = []
    f1s: List[float] = []
    for tr_idx, te_idx in cv.split(X, y):
        clf = Pipeline(
            [
                ("scale", StandardScaler(with_mean=True, with_std=True)),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=2000,
                        class_weight="balanced",
                        random_state=int(seed),
                    ),
                ),
            ]
        )
        clf.fit(X[tr_idx], y[tr_idx])
        yp = clf.predict(X[te_idx])
        accs.append(float(accuracy_score(y[te_idx], yp)))
        f1s.append(float(f1_score(y[te_idx], yp, average="macro", zero_division=0)))
    return {
        "linear_probe_cv_folds": int(folds),
        "linear_probe_accuracy_mean": float(np.mean(accs)),
        "linear_probe_accuracy_std": float(np.std(accs)),
        "linear_probe_macro_f1_mean": float(np.mean(f1s)),
        "linear_probe_macro_f1_std": float(np.std(f1s)),
    }


def _cluster_metrics(X: np.ndarray, y: np.ndarray) -> Dict[str, float | None]:
    try:
        from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score  # type: ignore
    except Exception as e:
        raise SystemExit("Missing scikit-learn. Install: pip install scikit-learn") from e

    uniq = np.unique(y)
    counts = pd.Series(y).value_counts()
    valid_silhouette = len(uniq) >= 2 and int(counts.min()) >= 2 and len(X) > len(uniq)
    out: Dict[str, float | None] = {
        "silhouette_score": None,
        "davies_bouldin_score": None,
        "calinski_harabasz_score": None,
    }
    if len(uniq) < 2:
        return out
    if valid_silhouette:
        out["silhouette_score"] = float(silhouette_score(X, y))
    out["davies_bouldin_score"] = float(davies_bouldin_score(X, y))
    out["calinski_harabasz_score"] = float(calinski_harabasz_score(X, y))
    return out


def _score_feature_set(
    df: pd.DataFrame,
    *,
    label_col: str,
    feature_cols: Sequence[str],
    cv_folds: int,
    seed: int,
) -> Dict[str, object]:
    work = df[[label_col] + list(feature_cols)].copy()
    for col in feature_cols:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=list(feature_cols)).reset_index(drop=True)
    if work.empty:
        raise SystemExit(f"no valid numeric rows available for feature cols: {', '.join(feature_cols)}")

    X = np.asarray(work[list(feature_cols)], dtype=np.float64)
    std = np.std(X, axis=0)
    keep = np.isfinite(std) & (std > 0.0)
    if not np.any(keep):
        raise SystemExit(f"all feature columns were constant or non-finite: {', '.join(feature_cols)}")
    if int(np.sum(~keep)) > 0:
        kept_cols = [str(c) for c, ok in zip(feature_cols, keep.tolist()) if ok]
        dropped_cols = [str(c) for c, ok in zip(feature_cols, keep.tolist()) if not ok]
        X = X[:, keep]
    else:
        kept_cols = list(feature_cols)
        dropped_cols = []
    y_labels = work[label_col].astype(str).to_numpy()
    classes, y = np.unique(y_labels, return_inverse=True)
    class_counts = pd.Series(y_labels).value_counts().sort_index()

    metrics: Dict[str, object] = {
        "feature_cols": kept_cols,
        "dropped_constant_or_nonfinite_cols": dropped_cols,
        "n_rows": int(len(work)),
        "n_dims": int(X.shape[1]),
        "n_classes": int(len(classes)),
        "class_counts": {str(k): int(v) for k, v in class_counts.items()},
    }
    metrics.update(_cluster_metrics(X, y))
    metrics.update(_centroid_metrics(X, y))
    metrics.update(_linear_probe_metrics(X, y, cv_folds=int(cv_folds), seed=int(seed)))
    return metrics


def main() -> int:
    args = _parse_args()
    inp = str(args.input).strip()
    if not inp:
        raise SystemExit("--input is required")

    df = pd.read_parquet(inp)
    if df.empty:
        raise SystemExit("input parquet is empty")

    label_col = _resolve_label_col(df, str(args.label_col))
    df = _apply_filters(
        df,
        label_col=label_col,
        split_col=str(args.split_col),
        split_values=[x.strip() for x in str(args.split_values).split(",") if x.strip()],
        drop_labels=[x.strip() for x in str(args.drop_labels).split(",") if x.strip()],
        min_class_rows=int(args.min_class_rows),
    )
    df = _sample_rows(df, max_rows=int(args.max_rows), seed=int(args.sample_seed))

    feature_sets = _detect_feature_sets(
        df,
        feature_set=str(args.feature_set),
        explicit_cols=str(args.feature_cols),
    )
    results = {
        "input": inp,
        "label_col": label_col,
        "split_col": str(args.split_col),
        "split_values": [x.strip() for x in str(args.split_values).split(",") if x.strip()],
        "drop_labels": [x.strip() for x in str(args.drop_labels).split(",") if x.strip()],
        "min_class_rows": int(args.min_class_rows),
        "rows_scored": int(len(df)),
        "feature_sets": {},
    }
    for name, cols in feature_sets.items():
        results["feature_sets"][name] = _score_feature_set(
            df,
            label_col=label_col,
            feature_cols=cols,
            cv_folds=int(args.cv_folds),
            seed=int(args.sample_seed),
        )

    payload = json.dumps(results, indent=2, sort_keys=True)
    out_json = Path(args.out_json) if str(args.out_json).strip() else None
    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(payload + "\n", encoding="utf-8")
        print(f"[ok] wrote {out_json}", flush=True)
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
