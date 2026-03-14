#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Fit a low-order harmonic demand model on hourly-aggregated PLC flow "
            "(daily + weekly sinusoidal terms)."
        )
    )
    p.add_argument(
        "--input-glob",
        action="append",
        default=None,
        help="Input parquet glob(s). Repeatable. Default: data/raw/plc/*/date=*/data.parquet",
    )
    p.add_argument("--site", default=None, help="Optional site filter (e.g. bluerock)")
    p.add_argument("--timestamp-col", default="plctime")
    p.add_argument("--target-col", default="deliveryflow")
    p.add_argument("--timezone", default="America/Los_Angeles")
    p.add_argument("--start", default=None, help="UTC start (inclusive), ISO-8601")
    p.add_argument("--end", default=None, help="UTC end (exclusive), ISO-8601")
    p.add_argument("--agg", default="mean", choices=["mean", "median"], help="Hourly aggregation method")
    p.add_argument("--agg-hours", type=int, default=1, help="Aggregation bin size in hours (e.g. 1 or 2)")

    p.add_argument("--daily-order", type=int, default=2, help="Number of daily harmonics")
    p.add_argument("--weekly-order", type=int, default=1, help="Number of weekly harmonics")
    p.add_argument("--trend-order", type=int, default=0, help="Add polynomial trend terms in local days (0,1,2)")
    p.add_argument("--holdout-days", type=int, default=7, help="Last N days used as test holdout")
    p.add_argument(
        "--fit-window-days",
        type=int,
        default=0,
        help="If >0, fit separate harmonic models in consecutive windows of this many days (e.g., 14).",
    )

    p.add_argument("--out-dir", default="data/derived/harmonic_demand")
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


def _load_hourly(
    files: Sequence[Path],
    *,
    site: str | None,
    timestamp_col: str,
    target_col: str,
    timezone: str,
    start: str | None,
    end: str | None,
    agg: str,
    agg_hours: int,
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
            d = pd.read_parquet(fp, columns=[timestamp_col, target_col, "location"])
        except Exception:
            d = pd.read_parquet(fp)
            if timestamp_col not in d.columns or target_col not in d.columns:
                continue
            keep = [timestamp_col, target_col]
            if "location" in d.columns:
                keep.append("location")
            d = d[keep]

        if d.empty:
            continue
        d = d.copy()
        d["ts"] = pd.to_datetime(d[timestamp_col], utc=True, errors="coerce")
        d["y"] = pd.to_numeric(d[target_col], errors="coerce")
        d["site_loc"] = d["location"].astype(str).str.strip().str.lower() if "location" in d.columns else ""

        if start_ts is not None:
            d = d[d["ts"] >= start_ts]
        if end_ts is not None:
            d = d[d["ts"] < end_ts]
        if site_norm:
            d = d[(d["site_loc"] == site_norm) | (path_site == site_norm)]
        d = d[d["ts"].notna() & d["y"].notna()]
        if not d.empty:
            rows.append(d[["ts", "y"]])

    if not rows:
        raise SystemExit("No rows found after filtering")

    df = pd.concat(rows, ignore_index=True).sort_values("ts").reset_index(drop=True)
    df["ts_local"] = df["ts"].dt.tz_convert(timezone)
    s = df.set_index("ts_local")["y"]
    freq = f"{int(max(1, agg_hours))}h"
    if agg == "mean":
        h = s.resample(freq).mean()
    else:
        h = s.resample(freq).median()
    h = h.dropna().rename("y").to_frame().reset_index()
    h = h.rename(columns={"ts_local": "t_local"})
    return h


def _design_matrix(t_local: pd.Series, daily_order: int, weekly_order: int, trend_order: int) -> Tuple[np.ndarray, List[str]]:
    # Use local clock features for periodic demand.
    hour = t_local.dt.hour + (t_local.dt.minute / 60.0)
    dow = t_local.dt.dayofweek + (hour / 24.0)

    cols = [np.ones(len(t_local), dtype=float)]
    names = ["bias"]

    for k in range(1, daily_order + 1):
        ang = 2.0 * np.pi * k * hour / 24.0
        cols.append(np.sin(ang).to_numpy())
        cols.append(np.cos(ang).to_numpy())
        names.append(f"day_sin_{k}")
        names.append(f"day_cos_{k}")

    for m in range(1, weekly_order + 1):
        ang = 2.0 * np.pi * m * dow / 7.0
        cols.append(np.sin(ang).to_numpy())
        cols.append(np.cos(ang).to_numpy())
        names.append(f"week_sin_{m}")
        names.append(f"week_cos_{m}")

    if trend_order > 0:
        t_days = (t_local - t_local.min()).dt.total_seconds() / 86400.0
        t_days = t_days.to_numpy(dtype=float)
        for q in range(1, trend_order + 1):
            cols.append(np.power(t_days, q))
            names.append(f"trend_pow_{q}")

    x = np.column_stack(cols)
    return x, names


def _metrics(y: np.ndarray, yhat: np.ndarray) -> Dict[str, float]:
    err = yhat - y
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    ybar = float(np.mean(y))
    sst = float(np.sum((y - ybar) ** 2))
    sse = float(np.sum((y - yhat) ** 2))
    r2 = float(1.0 - sse / sst) if sst > 0 else 0.0
    return {"mae": mae, "rmse": rmse, "r2": r2}


def _fit_and_predict(
    df_hourly: pd.DataFrame,
    daily_order: int,
    weekly_order: int,
    trend_order: int,
    holdout_days: int,
    fit_window_days: int,
) -> Tuple[pd.DataFrame, Dict]:
    df = df_hourly.copy().sort_values("t_local").reset_index(drop=True)
    x, names = _design_matrix(
        df["t_local"],
        daily_order=daily_order,
        weekly_order=weekly_order,
        trend_order=trend_order,
    )
    y = df["y"].to_numpy(dtype=float)

    if fit_window_days > 0:
        yhat = np.full_like(y, np.nan, dtype=float)
        t0 = df["t_local"].min()
        window = pd.Timedelta(days=int(fit_window_days))
        win_idx = ((df["t_local"] - t0) / window).astype(int)
        coeff_by_window: Dict[str, Dict[str, float]] = {}

        p = 1 + 2 * daily_order + 2 * weekly_order
        for w in sorted(win_idx.unique()):
            mask = (win_idx == w).to_numpy()
            if mask.sum() < p:
                continue
            beta_w, *_ = np.linalg.lstsq(x[mask], y[mask], rcond=None)
            yhat[mask] = x[mask] @ beta_w
            coeff_by_window[str(int(w))] = {names[i]: float(beta_w[i]) for i in range(len(names))}

        # Fill any unfitted rows with global model fallback.
        miss = ~np.isfinite(yhat)
        if miss.any():
            beta_g, *_ = np.linalg.lstsq(x[~miss], y[~miss], rcond=None)
            yhat[miss] = x[miss] @ beta_g
            coeff_global = {names[i]: float(beta_g[i]) for i in range(len(names))}
        else:
            coeff_global = None

        pred = df.copy()
        pred["yhat"] = yhat
        pred["split"] = "all"
        pred["window_idx"] = win_idx.to_numpy()

        baseline = np.full_like(y, float(np.mean(y)))
        info = {
            "coefficients_by_window": coeff_by_window,
            "coefficients_global_fallback": coeff_global,
            "metrics_all": _metrics(y, yhat),
            "metrics_baseline_all": _metrics(y, baseline),
            "n_rows_hourly": int(len(df)),
            "n_windows": int(len(set(int(v) for v in win_idx))),
            "fit_window_days": int(fit_window_days),
            "fit_t0_local": str(t0.isoformat()),
        }
        return pred, info

    cutoff = df["t_local"].max() - pd.Timedelta(days=int(max(0, holdout_days)))
    train_mask = (df["t_local"] < cutoff).to_numpy() if holdout_days > 0 else np.ones(len(df), dtype=bool)
    if train_mask.sum() < (1 + 2 * daily_order + 2 * weekly_order):
        train_mask[:] = True

    x_tr, y_tr = x[train_mask], y[train_mask]
    beta, *_ = np.linalg.lstsq(x_tr, y_tr, rcond=None)
    yhat = x @ beta

    pred = df.copy()
    pred["yhat"] = yhat
    pred["split"] = np.where(train_mask, "train", "test")

    baseline = np.full_like(y, y_tr.mean())
    info = {
        "coefficients": {names[i]: float(beta[i]) for i in range(len(names))},
        "metrics_train": _metrics(y[train_mask], yhat[train_mask]),
        "metrics_test": _metrics(y[~train_mask], yhat[~train_mask]) if (~train_mask).sum() > 0 else None,
        "metrics_baseline_train": _metrics(y[train_mask], baseline[train_mask]),
        "metrics_baseline_test": _metrics(y[~train_mask], baseline[~train_mask]) if (~train_mask).sum() > 0 else None,
        "n_rows_hourly": int(len(df)),
        "n_train": int(train_mask.sum()),
        "n_test": int((~train_mask).sum()),
        "fit_t0_local": str(df["t_local"].min().isoformat()),
    }
    return pred, info


def _heatmap_table(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    x = df.copy()
    x["hour"] = x["t_local"].dt.hour
    x["dow"] = x["t_local"].dt.dayofweek
    heat = (
        x.groupby(["dow", "hour"], as_index=False)[value_col]
        .mean()
        .pivot(index="dow", columns="hour", values=value_col)
        .reindex(index=range(7), columns=range(24))
    )
    return heat


def _plot_outputs(pred: pd.DataFrame, out_prefix: Path) -> Tuple[Path, Path]:
    import matplotlib.pyplot as plt

    png_ts = out_prefix.with_name(out_prefix.name + "_timeseries.png")
    png_heat = out_prefix.with_name(out_prefix.name + "_heatmaps.png")

    # Timeseries
    fig, ax = plt.subplots(figsize=(11, 4.5), dpi=140)
    ax.plot(pred["t_local"], pred["y"], label="hourly actual", lw=1.3)
    ax.plot(pred["t_local"], pred["yhat"], label="harmonic fit", lw=1.3)
    ax.set_title("Hourly demand: actual vs harmonic fit")
    ax.set_ylabel("Flow (GPM)")
    ax.set_xlabel("Time (local)")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_ts)
    plt.close(fig)

    # Heatmaps actual / fitted / residual
    ha = _heatmap_table(pred, "y")
    hf = _heatmap_table(pred, "yhat")
    hr = ha - hf

    fig, axs = plt.subplots(1, 3, figsize=(15, 4.7), dpi=140, constrained_layout=True)
    im0 = axs[0].imshow(ha.to_numpy(dtype=float), origin="upper", aspect="auto", cmap="viridis")
    axs[0].set_title("Actual")
    axs[0].set_xlabel("Hour")
    axs[0].set_ylabel("DOW")
    fig.colorbar(im0, ax=axs[0], fraction=0.046, pad=0.04)

    im1 = axs[1].imshow(hf.to_numpy(dtype=float), origin="upper", aspect="auto", cmap="viridis")
    axs[1].set_title("Harmonic fit")
    axs[1].set_xlabel("Hour")
    axs[1].set_ylabel("DOW")
    fig.colorbar(im1, ax=axs[1], fraction=0.046, pad=0.04)

    vmax = np.nanmax(np.abs(hr.to_numpy(dtype=float)))
    vmax = float(vmax) if np.isfinite(vmax) and vmax > 0 else 1.0
    im2 = axs[2].imshow(hr.to_numpy(dtype=float), origin="upper", aspect="auto", cmap="coolwarm", vmin=-vmax, vmax=vmax)
    axs[2].set_title("Residual (actual - fit)")
    axs[2].set_xlabel("Hour")
    axs[2].set_ylabel("DOW")
    fig.colorbar(im2, ax=axs[2], fraction=0.046, pad=0.04)

    fig.savefig(png_heat)
    plt.close(fig)
    return png_ts, png_heat


def main() -> None:
    args = build_argparser().parse_args()
    globs = _default_globs(args.input_glob)
    files = _expand(globs)
    if not files:
        raise SystemExit("No input files matched --input-glob")

    hourly = _load_hourly(
        files,
        site=args.site,
        timestamp_col=args.timestamp_col,
        target_col=args.target_col,
        timezone=args.timezone,
        start=args.start,
        end=args.end,
        agg=args.agg,
        agg_hours=int(args.agg_hours),
    )
    pred, info = _fit_and_predict(
        hourly,
        daily_order=int(args.daily_order),
        weekly_order=int(args.weekly_order),
        trend_order=int(args.trend_order),
        holdout_days=int(args.holdout_days),
        fit_window_days=int(args.fit_window_days),
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = args.prefix or args.site or "all_sites"
    prefix = out_dir / f"{name}_harmonic_demand"

    out_pred = prefix.with_name(prefix.name + "_hourly_pred.csv")
    out_coef = prefix.with_name(prefix.name + "_fit_info.json")
    out_heat_actual = prefix.with_name(prefix.name + "_heat_actual.csv")
    out_heat_fit = prefix.with_name(prefix.name + "_heat_fit.csv")
    out_heat_resid = prefix.with_name(prefix.name + "_heat_resid.csv")

    pred.to_csv(out_pred, index=False)
    with out_coef.open("w", encoding="utf-8") as f:
        payload = {
            "site": args.site,
            "target_col": args.target_col,
            "timezone": args.timezone,
            "daily_order": int(args.daily_order),
            "weekly_order": int(args.weekly_order),
            "trend_order": int(args.trend_order),
            "holdout_days": int(args.holdout_days),
            "fit_window_days": int(args.fit_window_days),
            "agg": args.agg,
            "agg_hours": int(args.agg_hours),
            "input_globs": globs,
            "n_files_matched": len(files),
            **info,
        }
        json.dump(payload, f, indent=2)

    ha = _heatmap_table(pred, "y")
    hf = _heatmap_table(pred, "yhat")
    hr = ha - hf
    ha.to_csv(out_heat_actual, index_label="dow")
    hf.to_csv(out_heat_fit, index_label="dow")
    hr.to_csv(out_heat_resid, index_label="dow")

    png_ts, png_heat = _plot_outputs(pred, prefix)

    print(f"[OK] wrote {out_pred}")
    print(f"[OK] wrote {out_coef}")
    print(f"[OK] wrote {out_heat_actual}")
    print(f"[OK] wrote {out_heat_fit}")
    print(f"[OK] wrote {out_heat_resid}")
    print(f"[OK] wrote {png_ts}")
    print(f"[OK] wrote {png_heat}")


if __name__ == "__main__":
    main()
