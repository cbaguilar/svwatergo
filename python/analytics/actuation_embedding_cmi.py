#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd


def _ensure_repo_on_syspath() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


_ensure_repo_on_syspath()


DEFAULT_ACTUATORS = [
    "ropumprun",
    "feedpumprun",
    "wellpumprun",
    "deliveryrun",
    "inletrun",
    "flushrun",
    "concbypassrun",
    "proddiversionrun",
]

TRIT_TO_STATE = {
    "0": "off",
    "1": "transition",
    "2": "on",
    "u": "unknown",
    "U": "unknown",
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Estimate how much unique information the audio embedding adds for each actuator "
            "after conditioning on the other actuators, using out-of-fold log-loss reduction."
        )
    )
    p.add_argument("--dataset", required=True, help="Input parquet with embedding_* and *_state columns")
    p.add_argument("--split", default="", help="Optional split filter: train/test/val")
    p.add_argument("--embedding-prefix", default="embedding_", help="Prefix for embedding columns")
    p.add_argument(
        "--actuators",
        default=",".join(DEFAULT_ACTUATORS),
        help="Comma-separated actuator base names",
    )
    p.add_argument(
        "--state-suffix",
        default="_state",
        help="Suffix used for actuator state columns, e.g. ropumprun_state",
    )
    p.add_argument("--drop-unknown", default="yes", choices=["yes", "no"])
    p.add_argument("--cv-folds", type=int, default=5)
    p.add_argument("--max-iter", type=int, default=2000)
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--out-csv", required=True)
    p.add_argument("--out-json", default="")
    return p.parse_args()


def _estimate_cmi_bits(
    df: pd.DataFrame,
    *,
    embedding_cols: List[str],
    actuator_cols: List[str],
    cv_folds: int,
    max_iter: int,
    random_state: int,
) -> pd.DataFrame:
    try:
        from sklearn.compose import ColumnTransformer  # type: ignore
        from sklearn.impute import SimpleImputer  # type: ignore
        from sklearn.linear_model import LogisticRegression  # type: ignore
        from sklearn.metrics import log_loss  # type: ignore
        from sklearn.model_selection import StratifiedKFold, cross_val_predict  # type: ignore
        from sklearn.pipeline import Pipeline  # type: ignore
        from sklearn.preprocessing import OneHotEncoder  # type: ignore
    except Exception as e:
        raise SystemExit("Missing scikit-learn. Install: pip install scikit-learn") from e

    rows: List[dict] = []
    for target_col in actuator_cols:
        others = [c for c in actuator_cols if c != target_col]
        y = df[target_col].astype("string")
        keep = y.notna()
        if int(keep.sum()) <= 1:
            continue
        y = y.loc[keep].astype(str)
        if y.nunique() < 2:
            continue

        X_other = df.loc[keep, others].copy()
        X_full = pd.concat([df.loc[keep, embedding_cols].copy(), X_other], axis=1)

        n_splits = max(2, min(int(cv_folds), int(y.value_counts().min())))
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=int(random_state))

        other_pre = ColumnTransformer(
            [
                (
                    "cat",
                    Pipeline(
                        [
                            ("imp", SimpleImputer(strategy="most_frequent")),
                            ("oh", OneHotEncoder(handle_unknown="ignore")),
                        ]
                    ),
                    others,
                )
            ]
        )
        full_pre = ColumnTransformer(
            [
                (
                    "emb",
                    Pipeline([("imp", SimpleImputer(strategy="median"))]),
                    embedding_cols,
                ),
                (
                    "cat",
                    Pipeline(
                        [
                            ("imp", SimpleImputer(strategy="most_frequent")),
                            ("oh", OneHotEncoder(handle_unknown="ignore")),
                        ]
                    ),
                    others,
                ),
            ]
        )

        base_model = Pipeline(
            [
                ("pre", other_pre),
                ("clf", LogisticRegression(max_iter=int(max_iter), multi_class="auto")),
            ]
        )
        full_model = Pipeline(
            [
                ("pre", full_pre),
                ("clf", LogisticRegression(max_iter=int(max_iter), multi_class="auto")),
            ]
        )

        labels = np.unique(y)
        p_base = cross_val_predict(base_model, X_other, y, cv=cv, method="predict_proba")
        p_full = cross_val_predict(full_model, X_full, y, cv=cv, method="predict_proba")

        ll_base = float(log_loss(y, p_base, labels=labels))
        ll_full = float(log_loss(y, p_full, labels=labels))
        cmi_bits = (ll_base - ll_full) / np.log(2.0)

        rows.append(
            {
                "actuator": target_col,
                "classes": int(y.nunique()),
                "n_rows": int(len(y)),
                "baseline_log_loss_nats": ll_base,
                "full_log_loss_nats": ll_full,
                "cmi_bits": float(cmi_bits),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("cmi_bits", ascending=False).reset_index(drop=True)


def _materialize_state_cols_from_trit(
    df: pd.DataFrame,
    *,
    actuators: List[str],
    state_suffix: str,
) -> pd.DataFrame:
    out = df.copy()
    trit_col = ""
    for cand in ("actuation_trit", "actuation_bits"):
        if cand in out.columns:
            trit_col = cand
            break
    if not trit_col:
        return out

    trit = out[trit_col].astype("string").fillna("").astype(str)
    for i, actuator in enumerate(actuators):
        state_col = f"{actuator}{state_suffix}"
        if state_col in out.columns:
            continue
        out[state_col] = trit.str.slice(i, i + 1).map(TRIT_TO_STATE).fillna("unknown").astype("string")
    return out


def main() -> int:
    args = _parse_args()
    dataset = Path(args.dataset)
    if not dataset.exists():
        raise SystemExit(f"dataset not found: {dataset}")

    df = pd.read_parquet(dataset)
    if df.empty:
        raise SystemExit("dataset is empty")

    if str(args.split).strip():
        if "split" not in df.columns:
            raise SystemExit("--split was provided but dataset has no split column")
        df = df[df["split"].astype(str).str.lower() == str(args.split).strip().lower()].copy()
        if df.empty:
            raise SystemExit("no rows left after split filter")

    actuators = [x.strip() for x in str(args.actuators).split(",") if x.strip()]
    df = _materialize_state_cols_from_trit(df, actuators=actuators, state_suffix=str(args.state_suffix))
    actuator_cols = [f"{a}{args.state_suffix}" for a in actuators]
    missing = [c for c in actuator_cols if c not in df.columns]
    if missing:
        raise SystemExit(f"missing actuator state columns: {', '.join(missing)}")

    if str(args.drop_unknown) == "yes":
        mask = np.ones(len(df), dtype=bool)
        for col in actuator_cols:
            mask &= (df[col].astype(str).str.lower().to_numpy() != "unknown")
        df = df.loc[mask].copy()
        if df.empty:
            raise SystemExit("no rows left after dropping unknown actuator states")

    embedding_cols = [c for c in df.columns if str(c).startswith(str(args.embedding_prefix))]
    if not embedding_cols:
        raise SystemExit(f"no embedding columns found with prefix: {args.embedding_prefix}")

    res = _estimate_cmi_bits(
        df,
        embedding_cols=embedding_cols,
        actuator_cols=actuator_cols,
        cv_folds=int(args.cv_folds),
        max_iter=int(args.max_iter),
        random_state=int(args.random_state),
    )
    if res.empty:
        raise SystemExit("no actuator scores produced")

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(out_csv, index=False)

    out_json = Path(args.out_json) if str(args.out_json).strip() else None
    if out_json is not None:
        payload = {
            "dataset": str(dataset),
            "split_filter": str(args.split).strip() or None,
            "drop_unknown": bool(str(args.drop_unknown) == "yes"),
            "embedding_prefix": str(args.embedding_prefix),
            "actuator_state_columns": actuator_cols,
            "cv_folds": int(args.cv_folds),
            "max_iter": int(args.max_iter),
            "random_state": int(args.random_state),
            "scores": res.to_dict(orient="records"),
        }
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Scores -> {out_csv}")
    if out_json is not None:
        print(f"Meta -> {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
