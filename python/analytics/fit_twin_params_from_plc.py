#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Estimate digital-twin parameters from PLC parquet data: "
            "hysteresis setpoints, key flow params, and feed/product tank capacities."
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
    p.add_argument("--cadence", default="2s", help="Resample cadence (e.g. 2s, 10s, 1min)")
    p.add_argument(
        "--capacity-cadence",
        default="5min",
        help="Coarser cadence used for tank-capacity fitting from %% slopes (default: 5min).",
    )

    p.add_argument("--well-state-col", default="wellpumprun")
    p.add_argument("--ro-state-col", default="ropumprun")
    p.add_argument("--flush-state-col", default="flushrun")
    p.add_argument("--feed-level-col", default="feedtanklevel")
    p.add_argument("--product-level-col", default="prodtanklevel")

    p.add_argument("--permeateflow-col", default="permeateflow")
    p.add_argument("--deliveryflow-col", default="deliveryflow")
    p.add_argument("--feedflow-col", default="feedflow")

    p.add_argument(
        "--setpoint-quantile",
        type=float,
        default=0.5,
        help="Quantile for ON/OFF transition setpoint estimates (default median=0.5).",
    )
    p.add_argument("--min-transition-count", type=int, default=5)
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


def _nonneg_median(x: pd.Series) -> float:
    v = pd.to_numeric(x, errors="coerce")
    v = v[v.notna()]
    if v.empty:
        return 0.0
    return float(v.clip(lower=0.0).median())


def _load_and_resample(
    files: Sequence[Path],
    *,
    site: str | None,
    timestamp_col: str,
    cols: Sequence[str],
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
        keep = [timestamp_col] + [c for c in cols if c in d.columns]
        d = d[keep].copy()
        d["__ts"] = pd.to_datetime(d[timestamp_col], utc=True, errors="coerce")
        d = d[d["__ts"].notna()]
        if start_ts is not None:
            d = d[d["__ts"] >= start_ts]
        if end_ts is not None:
            d = d[d["__ts"] < end_ts]
        if d.empty:
            continue
        rows.append(d)

    if not rows:
        raise SystemExit("No rows found after file/site/time filtering")

    df = pd.concat(rows, ignore_index=True).sort_values("__ts").reset_index(drop=True)
    g = df.set_index("__ts")
    agg: Dict[str, str] = {c: "mean" for c in cols if c in df.columns}
    r = g.resample(cadence).agg(agg).dropna(how="all")
    r = r.reset_index().sort_values("__ts").reset_index(drop=True)
    return r


def _estimate_setpoints(df: pd.DataFrame, level_col: str, run_col: str, q: float) -> Dict[str, float | int | None]:
    if level_col not in df.columns or run_col not in df.columns:
        return {"n_on": 0, "n_off": 0, "low": None, "high": None}
    x = _as_binary(df[run_col])
    lv = pd.to_numeric(df[level_col], errors="coerce")
    dx = x.diff()
    on_levels = lv[dx == 1].dropna()
    off_levels = lv[dx == -1].dropna()
    return {
        "n_on": int(len(on_levels)),
        "n_off": int(len(off_levels)),
        "low": float(on_levels.quantile(q)) if len(on_levels) else None,
        "high": float(off_levels.quantile(q)) if len(off_levels) else None,
    }


def _safe_div(num: float, den: float) -> float:
    return float(num / den) if abs(float(den)) > 1e-12 else float("nan")


def main() -> None:
    args = build_argparser().parse_args()
    files = _expand(_default_globs(args.input_glob))
    if not files:
        raise SystemExit("No files matched --input-glob")

    cols = [
        args.well_state_col,
        args.ro_state_col,
        args.flush_state_col,
        args.feed_level_col,
        args.product_level_col,
        args.permeateflow_col,
        args.deliveryflow_col,
        args.feedflow_col,
    ]
    df = _load_and_resample(
        files,
        site=args.site,
        timestamp_col=args.timestamp_col,
        cols=cols,
        start=args.start,
        end=args.end,
        cadence=args.cadence,
    )

    for c in [args.well_state_col, args.ro_state_col, args.flush_state_col]:
        if c in df.columns:
            df[c] = _as_binary(df[c])
        else:
            df[c] = 0
    for c in [
        args.feed_level_col,
        args.product_level_col,
        args.permeateflow_col,
        args.deliveryflow_col,
        args.feedflow_col,
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = np.nan

    dt_seconds = float(pd.to_timedelta(args.cadence).total_seconds())
    if dt_seconds <= 0:
        raise SystemExit("--cadence must be > 0")

    cap_dt_seconds = float(pd.to_timedelta(args.capacity_cadence).total_seconds())
    if cap_dt_seconds <= 0:
        raise SystemExit("--capacity-cadence must be > 0")

    feed_sp = _estimate_setpoints(df, args.feed_level_col, args.well_state_col, float(args.setpoint_quantile))
    prod_sp = _estimate_setpoints(df, args.product_level_col, args.ro_state_col, float(args.setpoint_quantile))

    ro_on = df[args.ro_state_col] == 1
    well_on = df[args.well_state_col] == 1
    flush_on = df[args.flush_state_col] == 1

    q_ro_permeate = _nonneg_median(df.loc[ro_on, args.permeateflow_col])
    q_ro_feed_draw = _nonneg_median(df.loc[ro_on, args.feedflow_col])
    q_flush_draw = _nonneg_median(df.loc[flush_on & (~ro_on), args.feedflow_col])
    q_demand_mean = float(pd.to_numeric(df[args.deliveryflow_col], errors="coerce").clip(lower=0.0).mean())

    # Capacity fit on coarser cadence to reduce level quantization noise.
    fit_cols = [
        args.well_state_col,
        args.ro_state_col,
        args.flush_state_col,
        args.feed_level_col,
        args.product_level_col,
        args.deliveryflow_col,
    ]
    cdf = (
        df.set_index("__ts")[fit_cols]
        .resample(args.capacity_cadence)
        .mean()
        .dropna(how="all")
        .reset_index()
        .sort_values("__ts")
        .reset_index(drop=True)
    )
    for c in [args.well_state_col, args.ro_state_col, args.flush_state_col]:
        cdf[c] = (pd.to_numeric(cdf[c], errors="coerce").fillna(0.0) >= 0.5).astype(int)
    cdf[args.deliveryflow_col] = pd.to_numeric(cdf[args.deliveryflow_col], errors="coerce").fillna(0.0).clip(lower=0.0)

    cdt_h = cdf["__ts"].diff().dt.total_seconds() / 3600.0
    cdf["feed_dpct_per_h"] = pd.to_numeric(cdf[args.feed_level_col], errors="coerce").diff() / cdt_h
    cdf["product_dpct_per_h"] = pd.to_numeric(cdf[args.product_level_col], errors="coerce").diff() / cdt_h

    # Feed tank: y = b_well * well_on - g_feed * q_known_out
    # where y is dpct_per_h and g_feed = 6000 / C_feed, b_well = g_feed * q_well.
    fd = cdf[[args.well_state_col, args.ro_state_col, args.flush_state_col, "feed_dpct_per_h"]].copy()
    fd = fd.replace([np.inf, -np.inf], np.nan).dropna()
    x_well = fd[args.well_state_col].to_numpy(dtype=float)
    x_out = (
        q_ro_feed_draw * fd[args.ro_state_col].to_numpy(dtype=float)
        + q_flush_draw * fd[args.flush_state_col].to_numpy(dtype=float)
    )
    y_feed = fd["feed_dpct_per_h"].to_numpy(dtype=float)
    x_feed = np.column_stack([x_well, -x_out])
    b_feed, *_ = np.linalg.lstsq(x_feed, y_feed, rcond=None)
    b_well = max(0.0, float(b_feed[0]))
    g_feed = max(1e-9, float(b_feed[1]))
    c_feed = 6000.0 / g_feed
    q_well_refill = b_well / g_feed if g_feed > 0 else float("nan")

    yhat_feed = x_feed @ np.array([b_well, g_feed], dtype=float)
    rmse_feed = float(np.sqrt(np.mean((yhat_feed - y_feed) ** 2)))

    # Product tank: y = g_prod * (q_perm*ro_on - q_demand_meas)
    pdm = cdf[[args.ro_state_col, args.deliveryflow_col, "product_dpct_per_h"]].copy()
    pdm = pdm.replace([np.inf, -np.inf], np.nan).dropna()
    x_prod = (
        q_ro_permeate * pdm[args.ro_state_col].to_numpy(dtype=float)
        - pdm[args.deliveryflow_col].clip(lower=0.0).to_numpy(dtype=float)
    )
    y_prod = pdm["product_dpct_per_h"].to_numpy(dtype=float)
    den = float(np.dot(x_prod, x_prod))
    g_prod = float(max(1e-9, np.dot(x_prod, y_prod) / den)) if den > 0 else 1e-9
    c_product = 6000.0 / g_prod
    yhat_prod = g_prod * x_prod
    rmse_prod = float(np.sqrt(np.mean((yhat_prod - y_prod) ** 2)))

    feed_low = feed_sp.get("low")
    feed_high = feed_sp.get("high")
    prod_low = prod_sp.get("low")
    prod_high = prod_sp.get("high")

    twin_params = {
        "feed_capacity_gal": float(c_feed),
        "product_capacity_gal": float(c_product),
        "feed_low_pct": float(feed_low) if feed_low is not None else None,
        "feed_high_pct": float(feed_high) if feed_high is not None else None,
        "product_low_pct": float(prod_low) if prod_low is not None else None,
        "product_high_pct": float(prod_high) if prod_high is not None else None,
        "well_refill_gpm": float(q_well_refill),
        "ro_permeate_gpm": float(q_ro_permeate),
        "ro_feed_draw_gpm": float(q_ro_feed_draw),
        "flush1_draw_gpm": float(q_flush_draw),
        "flush2_draw_gpm": float(q_flush_draw),
        "demand_base_gpm": float(q_demand_mean),
    }

    summary = {
        "site": args.site,
        "rows": int(len(df)),
        "cadence": args.cadence,
        "cadence_seconds": dt_seconds,
        "capacity_cadence": args.capacity_cadence,
        "capacity_cadence_seconds": cap_dt_seconds,
        "files_matched": int(len(files)),
        "start": args.start,
        "end": args.end,
        "setpoint_quantile": float(args.setpoint_quantile),
        "setpoints": {"feed": feed_sp, "product": prod_sp},
        "flow_sensor_estimates_gpm": {
            "ro_permeate": float(q_ro_permeate),
            "ro_feed_draw": float(q_ro_feed_draw),
            "flush_draw": float(q_flush_draw),
            "delivery_mean": float(q_demand_mean),
        },
        "fit_quality": {
            "feed_dpct_per_h_rmse": float(rmse_feed),
            "product_dpct_per_h_rmse": float(rmse_prod),
            "feed_rows": int(len(fd)),
            "product_rows": int(len(pdm)),
        },
        "twin_params": twin_params,
    }

    if int(feed_sp.get("n_on", 0)) < int(args.min_transition_count) or int(feed_sp.get("n_off", 0)) < int(args.min_transition_count):
        summary["setpoints"]["feed"]["warning"] = (
            f"feed transitions below --min-transition-count={int(args.min_transition_count)}"
        )
    if int(prod_sp.get("n_on", 0)) < int(args.min_transition_count) or int(prod_sp.get("n_off", 0)) < int(args.min_transition_count):
        summary["setpoints"]["product"]["warning"] = (
            f"product transitions below --min-transition-count={int(args.min_transition_count)}"
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = args.prefix or (args.site if args.site else "all_sites")
    base = out_dir / f"{name}_twin_fit"
    out_summary = base.with_name(base.name + "_summary.json")
    out_params = base.with_name(base.name + "_params.json")
    out_transitions = base.with_name(base.name + "_transition_samples.csv")

    tr = df[["__ts", args.feed_level_col, args.product_level_col, args.well_state_col, args.ro_state_col]].copy()
    tr["well_edge"] = tr[args.well_state_col].diff().fillna(0).astype(int)
    tr["ro_edge"] = tr[args.ro_state_col].diff().fillna(0).astype(int)
    tr = tr[(tr["well_edge"] != 0) | (tr["ro_edge"] != 0)]
    tr.to_csv(out_transitions, index=False)
    out_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    out_params.write_text(json.dumps(twin_params, indent=2), encoding="utf-8")

    print(f"[OK] wrote {out_summary}")
    print(f"[OK] wrote {out_params}")
    print(f"[OK] wrote {out_transitions}")


if __name__ == "__main__":
    main()
