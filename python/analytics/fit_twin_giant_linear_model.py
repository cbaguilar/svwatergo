#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

DEFAULT_STATE_COLS = [
    "wellpumprun",
    "feedpumprun",
    "ropumprun",
    "deliveryrun",
    "inletrun",
    "flushrun",
]

DEFAULT_FLOW_COLS = [
    "permeateflow",
    "deliveryflow",
    "feedflow",
    "inletflow",
    "concentrateflow",
    "recycleflow",
]


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Fit one giant linear model with state-combination indicator variables shared across all targets. "
            "Targets include flow sensors and tank level rates."
        )
    )
    p.add_argument(
        "--input-glob",
        action="append",
        default=None,
        help="Input parquet glob(s). Repeatable. Default: data/raw/plc/*/date=*/data.parquet",
    )
    p.add_argument("--site", default=None, help="Optional site filter (e.g. bluerock)")
    p.add_argument("--start", default=None, help="UTC start (inclusive), ISO-8601")
    p.add_argument("--end", default=None, help="UTC end (exclusive), ISO-8601")
    p.add_argument("--timestamp-col", default="plctime")
    p.add_argument("--cadence", default="5min", help="Resample cadence before fitting, e.g. 2s, 10s, 1min, 5min")

    p.add_argument("--state-col", action="append", default=None, help="Repeatable state columns (default common pump/valve run bits)")
    p.add_argument("--flow-col", action="append", default=None, help="Repeatable flow columns to include as targets")
    p.add_argument("--feed-level-col", default="feedtanklevel")
    p.add_argument("--product-level-col", default="prodtanklevel")

    p.add_argument("--include-intercept", action="store_true", help="Add intercept; otherwise one-hot state coefficients are direct state means")
    p.add_argument("--min-state-rows", type=int, default=30, help="Drop states with fewer rows from model fit")
    p.add_argument(
        "--require-on",
        action="append",
        default=None,
        help=(
            "Hard state constraint target:statecol (repeatable). "
            "Example: --require-on permeateflow:ropumprun enforces 0 coefficient where ropumprun=0."
        ),
    )
    p.add_argument("--nonnegative", action="store_true", help="Constrain coefficients >= 0 (intercept unconstrained)")
    p.add_argument("--out-dir", default="data/derived/twin_calibration")
    p.add_argument("--prefix", default=None)
    return p


def _default_globs(globs: Sequence[str] | None) -> List[str]:
    return list(globs) if globs else ["data/raw/plc/*/date=*/data.parquet"]


def _expand(globs: Sequence[str]) -> List[Path]:
    out: List[Path] = []
    for g in globs:
        out.extend(Path(p) for p in sorted(glob.glob(g, recursive=True)))
    return sorted(set(out))


def _site_from_path(path: Path) -> str:
    parts = path.parts
    if "plc" not in parts:
        return ""
    i = parts.index("plc")
    if i + 1 >= len(parts):
        return ""
    raw = parts[i + 1].strip().lower()
    return raw.split("=", 1)[1] if raw.startswith("site=") else raw


def _as_binary(s: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(s):
        return s.astype(int)
    x = pd.to_numeric(s, errors="coerce")
    return (x.fillna(0.0) > 0).astype(int)


def _load_and_resample(
    files: Sequence[Path],
    *,
    site: str | None,
    timestamp_col: str,
    state_cols: Sequence[str],
    flow_cols: Sequence[str],
    feed_level_col: str,
    product_level_col: str,
    start: str | None,
    end: str | None,
    cadence: str,
) -> pd.DataFrame:
    site_norm = site.strip().lower() if site else None
    start_ts = pd.Timestamp(start, tz="UTC") if start else None
    end_ts = pd.Timestamp(end, tz="UTC") if end else None

    rows: List[pd.DataFrame] = []
    for fp in files:
        path_site = _site_from_path(fp)
        if site_norm and path_site and path_site != site_norm:
            continue

        try:
            d = pd.read_parquet(fp)
        except Exception:
            continue
        if timestamp_col not in d.columns:
            continue

        keep = [timestamp_col] + list(state_cols) + list(flow_cols) + [feed_level_col, product_level_col]
        keep = [c for c in keep if c in d.columns]
        d = d[keep].copy()
        d["__ts"] = pd.to_datetime(d[timestamp_col], utc=True, errors="coerce")
        d = d[d["__ts"].notna()]
        if start_ts is not None:
            d = d[d["__ts"] >= start_ts]
        if end_ts is not None:
            d = d[d["__ts"] < end_ts]
        if d.empty:
            continue

        out = pd.DataFrame({"__ts": d["__ts"]})
        for c in state_cols:
            out[c] = _as_binary(d[c]) if c in d.columns else 0
        for c in flow_cols + [feed_level_col, product_level_col]:
            out[c] = pd.to_numeric(d[c], errors="coerce") if c in d.columns else np.nan
        rows.append(out)

    if not rows:
        raise SystemExit("No rows found after filtering")

    df = pd.concat(rows, ignore_index=True).sort_values("__ts").reset_index(drop=True)

    g = df.set_index("__ts")
    agg: Dict[str, str] = {c: "mean" for c in state_cols + list(flow_cols) + [feed_level_col, product_level_col]}
    r = g.resample(cadence).agg(agg).dropna(how="all")
    for c in state_cols:
        r[c] = (r[c].fillna(0.0) >= 0.5).astype(int)

    r = r.reset_index().sort_values("__ts").reset_index(drop=True)
    dt_h = r["__ts"].diff().dt.total_seconds() / 3600.0
    r["feed_dpct_per_h"] = (r[feed_level_col].diff() / dt_h)
    r["product_dpct_per_h"] = (r[product_level_col].diff() / dt_h)
    return r


def _state_key(df: pd.DataFrame, state_cols: Sequence[str]) -> pd.Series:
    x = df[list(state_cols)].fillna(0).astype(int)
    return x.astype(str).agg("|".join, axis=1)


def _estimate_setpoints(df: pd.DataFrame, level_col: str, run_col: str) -> Dict[str, float | int | None]:
    if run_col not in df.columns or level_col not in df.columns:
        return {"n_on": 0, "n_off": 0, "low_median": None, "high_median": None}
    x = _as_binary(df[run_col])
    lv = pd.to_numeric(df[level_col], errors="coerce")
    dx = x.diff()
    on_levels = lv[dx == 1].dropna()
    off_levels = lv[dx == -1].dropna()
    return {
        "n_on": int(len(on_levels)),
        "n_off": int(len(off_levels)),
        "low_median": float(on_levels.median()) if len(on_levels) else None,
        "high_median": float(off_levels.median()) if len(off_levels) else None,
    }


def _parse_require_on(items: Sequence[str] | None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in items or []:
        s = str(raw).strip()
        if not s or ":" not in s:
            continue
        target, state_col = s.split(":", 1)
        out[target.strip()] = state_col.strip()
    return out


def _state_bits_from_dummy_col(name: str) -> List[int]:
    key = name[len("st_") :] if name.startswith("st_") else name
    return [int(x) for x in key.split("|")]


def _fit_target_constrained(
    *,
    x_dummy: pd.DataFrame,
    y: np.ndarray,
    include_intercept: bool,
    nonnegative: bool,
    require_state_col: str | None,
    state_cols: Sequence[str],
) -> Tuple[np.ndarray, Dict[str, object]]:
    cols = list(x_dummy.columns)
    allow = np.ones(len(cols), dtype=bool)

    if require_state_col and require_state_col in state_cols:
        bit_idx = list(state_cols).index(require_state_col)
        allow = np.array([_state_bits_from_dummy_col(c)[bit_idx] == 1 for c in cols], dtype=bool)

    x_work = x_dummy.loc[:, allow]
    names_work = list(x_work.columns)
    x_mat = x_work.to_numpy(dtype=float)

    if include_intercept:
        x_mat = np.column_stack([np.ones(len(x_mat), dtype=float), x_mat])

    if nonnegative:
        try:
            from scipy.optimize import lsq_linear  # type: ignore

            lb = np.zeros(x_mat.shape[1], dtype=float)
            ub = np.full(x_mat.shape[1], np.inf, dtype=float)
            if include_intercept:
                lb[0] = -np.inf
            res = lsq_linear(x_mat, y, bounds=(lb, ub), method="trf", lsmr_tol="auto")
            b_work = res.x
            solver = "scipy.optimize.lsq_linear"
        except Exception:
            b_work, *_ = np.linalg.lstsq(x_mat, y, rcond=None)
            solver = "numpy.linalg.lstsq_fallback"
    else:
        b_work, *_ = np.linalg.lstsq(x_mat, y, rcond=None)
        solver = "numpy.linalg.lstsq"

    out = np.zeros((1 + len(cols)) if include_intercept else len(cols), dtype=float)
    if include_intercept:
        out[0] = float(b_work[0])
        for i, col in enumerate(names_work):
            full_i = cols.index(col)
            out[1 + full_i] = float(b_work[1 + i])
    else:
        for i, col in enumerate(names_work):
            full_i = cols.index(col)
            out[full_i] = float(b_work[i])

    meta = {
        "solver": solver,
        "require_state_col": require_state_col,
        "n_allowed_states": int(allow.sum()),
        "n_total_states": int(len(allow)),
    }
    return out, meta


def main() -> None:
    args = build_argparser().parse_args()
    state_cols = list(args.state_col) if args.state_col else list(DEFAULT_STATE_COLS)
    flow_cols = list(args.flow_col) if args.flow_col else list(DEFAULT_FLOW_COLS)

    files = _expand(_default_globs(args.input_glob))
    if not files:
        raise SystemExit("No files matched --input-glob")

    df = _load_and_resample(
        files,
        site=args.site,
        timestamp_col=args.timestamp_col,
        state_cols=state_cols,
        flow_cols=flow_cols,
        feed_level_col=args.feed_level_col,
        product_level_col=args.product_level_col,
        start=args.start,
        end=args.end,
        cadence=args.cadence,
    )

    all_targets_raw = [c for c in flow_cols if c in df.columns] + ["feed_dpct_per_h", "product_dpct_per_h"]
    work = df[["__ts"] + state_cols + all_targets_raw].copy()
    for c in all_targets_raw:
        work[c] = pd.to_numeric(work[c], errors="coerce")
    all_targets = [c for c in all_targets_raw if work[c].notna().sum() >= int(max(10, args.min_state_rows))]
    if not all_targets:
        raise SystemExit("No usable targets after NaN filtering")
    work = work[["__ts"] + state_cols + all_targets].copy()

    work["state_key"] = _state_key(work, state_cols)
    counts = work["state_key"].value_counts().sort_index()
    keep_states = counts[counts >= int(max(1, args.min_state_rows))].index
    w = work[work["state_key"].isin(keep_states)].copy()
    w = w.dropna(subset=all_targets)
    if w.empty:
        raise SystemExit("No rows left after state-count and NaN filtering")

    dummies = pd.get_dummies(w["state_key"], prefix="st", dtype=float)
    state_names = list(dummies.columns)
    coef_names = (["intercept"] + state_names) if args.include_intercept else state_names

    Y = w[all_targets].to_numpy(dtype=float)
    B = np.zeros((len(coef_names), len(all_targets)), dtype=float)
    Yhat = np.full_like(Y, np.nan, dtype=float)

    require_on = _parse_require_on(args.require_on)
    fit_meta: Dict[str, Dict[str, object]] = {}
    x_full = dummies.to_numpy(dtype=float)

    for j, t in enumerate(all_targets):
        req = require_on.get(t)
        if req is not None and req not in state_cols:
            req = None
        b_j, meta_j = _fit_target_constrained(
            x_dummy=dummies,
            y=Y[:, j],
            include_intercept=bool(args.include_intercept),
            nonnegative=bool(args.nonnegative),
            require_state_col=req,
            state_cols=state_cols,
        )
        B[:, j] = b_j
        fit_meta[t] = meta_j
        if args.include_intercept:
            Yhat[:, j] = b_j[0] + x_full @ b_j[1:]
        else:
            Yhat[:, j] = x_full @ b_j

    metrics = {}
    for j, t in enumerate(all_targets):
        y = Y[:, j]
        yh = Yhat[:, j]
        err = yh - y
        mae = float(np.mean(np.abs(err)))
        rmse = float(np.sqrt(np.mean(err**2)))
        sst = float(np.sum((y - float(np.mean(y))) ** 2))
        sse = float(np.sum((y - yh) ** 2))
        r2 = float(1.0 - sse / sst) if sst > 0 else 0.0
        metrics[t] = {"mae": mae, "rmse": rmse, "r2": r2}

    coef_df = pd.DataFrame({"coef_name": coef_names})
    for j, t in enumerate(all_targets):
        coef_df[f"coef_{t}"] = B[:, j]

    state_rows = []
    for sk, n in counts.items():
        bits = [int(x) for x in sk.split("|")]
        row = {c: bits[i] for i, c in enumerate(state_cols)}
        row["state_key"] = sk
        row["n_rows"] = int(n)
        cname = f"st_{sk}"
        if args.include_intercept:
            base = coef_df.loc[coef_df["coef_name"] == "intercept"].iloc[0]
            st = coef_df.loc[coef_df["coef_name"] == cname]
            for t in all_targets:
                row[f"mean_{t}"] = float(base[f"coef_{t}"] + (st.iloc[0][f"coef_{t}"] if not st.empty else 0.0))
        else:
            st = coef_df.loc[coef_df["coef_name"] == cname]
            for t in all_targets:
                row[f"mean_{t}"] = float(st.iloc[0][f"coef_{t}"]) if not st.empty else np.nan
        state_rows.append(row)
    state_means = pd.DataFrame(state_rows).sort_values("n_rows", ascending=False)

    setpoints = {
        "feed": _estimate_setpoints(df, args.feed_level_col, "wellpumprun"),
        "product": _estimate_setpoints(df, args.product_level_col, "ropumprun"),
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = args.prefix or (args.site if args.site else "all_sites")
    base = out_dir / f"{name}_giant_linear"

    out_state = base.with_name(base.name + "_state_means.csv")
    out_coef = base.with_name(base.name + "_coefficients.csv")
    out_metrics = base.with_name(base.name + "_summary.json")
    out_pred = base.with_name(base.name + "_predictions.csv")

    state_means.to_csv(out_state, index=False)
    coef_df.to_csv(out_coef, index=False)

    pred = w[["__ts", "state_key"] + all_targets].copy()
    for j, t in enumerate(all_targets):
        pred[f"pred_{t}"] = Yhat[:, j]
    pred.to_csv(out_pred, index=False)

    payload = {
        "site": args.site,
        "state_cols": state_cols,
        "targets": all_targets,
        "include_intercept": bool(args.include_intercept),
        "min_state_rows": int(args.min_state_rows),
        "cadence": args.cadence,
        "rows_used": int(len(w)),
        "n_states_seen": int(counts.shape[0]),
        "n_states_modeled": int(len(keep_states)),
        "metrics": metrics,
        "fit_meta": fit_meta,
        "require_on": require_on,
        "nonnegative": bool(args.nonnegative),
        "setpoint_estimates": setpoints,
        "files_matched": len(files),
        "input_globs": _default_globs(args.input_glob),
        "start": args.start,
        "end": args.end,
    }
    out_metrics.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"[OK] wrote {out_state}")
    print(f"[OK] wrote {out_coef}")
    print(f"[OK] wrote {out_pred}")
    print(f"[OK] wrote {out_metrics}")


if __name__ == "__main__":
    main()
