#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Frequency-domain analysis for PLC deliverypressure (proxy for water consumption). "
            "Loads partitioned PLC parquet files, resamples to fixed cadence, and computes PSD "
            "across hourly-to-seasonal periods."
        )
    )
    p.add_argument(
        "--input-glob",
        action="append",
        default=None,
        help="Input parquet glob(s). Repeatable. Default: data/raw/plc/*/date=*/data.parquet",
    )
    p.add_argument("--site", default=None, help="Optional site filter (e.g. bluerock/pryorfarm/santateresa)")
    p.add_argument("--start", default=None, help="UTC start time (ISO-8601, inclusive)")
    p.add_argument("--end", default=None, help="UTC end time (ISO-8601, exclusive)")

    p.add_argument("--timestamp-col", default="plctime", help="Timestamp column name")
    p.add_argument("--value-col", default="deliverypressure", help="Signal column to analyze")
    p.add_argument("--cadence", default="5min", help="Resample cadence (pandas offset alias), default: 5min")
    p.add_argument(
        "--max-interp-points",
        type=int,
        default=6,
        help="Max consecutive missing bins to interpolate (after resample), default: 6",
    )

    p.add_argument(
        "--min-period-hours",
        type=float,
        default=1.0,
        help="Shortest period to keep in output (hours), default: 1",
    )
    p.add_argument(
        "--max-period-hours",
        type=float,
        default=24.0 * 90.0,
        help="Longest period to keep in output (hours), default: 2160 (90 days)",
    )

    p.add_argument(
        "--detrend-window",
        default="7D",
        help="Rolling median window for trend removal (set empty to disable), default: 7D",
    )
    p.add_argument(
        "--zscore",
        action="store_true",
        help="Apply z-score normalization after detrending",
    )
    p.add_argument(
        "--segment-days",
        type=float,
        default=7.0,
        help="Welch segment length in days (if SciPy available), default: 7",
    )
    p.add_argument("--top-k", type=int, default=10, help="Number of strongest periods to report, default: 10")

    p.add_argument(
        "--out-dir",
        default="data/derived/fourier_deliverypressure",
        help="Output directory",
    )
    p.add_argument("--prefix", default=None, help="Optional output filename prefix")
    p.add_argument(
        "--no-plot",
        action="store_true",
        help="Skip PSD plot generation",
    )
    return p


def _default_globs(input_globs: Optional[Sequence[str]]) -> List[str]:
    if input_globs:
        return list(input_globs)
    return ["data/raw/plc/*/date=*/data.parquet"]


def _site_from_path(path: Path) -> str:
    # Expected partition pattern: .../plc/<site>/date=YYYY-MM-DD/data.parquet
    parts = path.parts
    if "plc" in parts:
        i = parts.index("plc")
        if i + 1 < len(parts):
            return parts[i + 1].strip().lower()
    return ""


def _expand_glob_pattern(pattern: str) -> List[Path]:
    # pathlib.Path.glob does not support absolute patterns, so use glob.glob for both.
    return [Path(p) for p in sorted(glob.glob(pattern, recursive=True))]


def _load_rows(
    globs: Sequence[str],
    site: Optional[str],
    timestamp_col: str,
    value_col: str,
    start: Optional[str],
    end: Optional[str],
) -> pd.DataFrame:
    files: List[Path] = []
    for g in globs:
        files.extend(_expand_glob_pattern(g))

    if not files:
        raise SystemExit("No parquet files matched --input-glob")

    site_norm = site.strip().lower() if site else None
    rows: List[pd.DataFrame] = []

    start_ts = pd.Timestamp(start, tz="UTC") if start else None
    end_ts = pd.Timestamp(end, tz="UTC") if end else None

    for fp in files:
        path_site = _site_from_path(fp)
        if site_norm and path_site and path_site != site_norm:
            continue

        try:
            df = pd.read_parquet(fp, columns=[timestamp_col, value_col, "location"])
        except Exception:
            df = pd.read_parquet(fp)
            missing = [c for c in (timestamp_col, value_col) if c not in df.columns]
            if missing:
                continue
            keep_cols = [timestamp_col, value_col]
            if "location" in df.columns:
                keep_cols.append("location")
            df = df[keep_cols]

        if df.empty:
            continue

        df = df.copy()
        df["__ts"] = pd.to_datetime(df[timestamp_col], utc=True, errors="coerce")
        df["__y"] = pd.to_numeric(df[value_col], errors="coerce")
        df["__site_path"] = path_site
        if "location" in df.columns:
            df["__site_loc"] = df["location"].astype(str).str.strip().str.lower()
        else:
            df["__site_loc"] = ""

        if start_ts is not None:
            df = df[df["__ts"] >= start_ts]
        if end_ts is not None:
            df = df[df["__ts"] < end_ts]

        if site_norm:
            # Keep rows when either partition site or location field matches.
            mask = (df["__site_path"] == site_norm) | (df["__site_loc"] == site_norm)
            df = df[mask]

        df = df[df["__ts"].notna() & df["__y"].notna()]
        if not df.empty:
            rows.append(df[["__ts", "__y", "__site_path", "__site_loc"]])

    if not rows:
        raise SystemExit("No rows found after file/site/time filtering")

    out = pd.concat(rows, axis=0, ignore_index=True)
    out = out.sort_values("__ts", kind="mergesort")
    out = out.drop_duplicates(subset=["__ts"], keep="last").reset_index(drop=True)
    return out


def _resample_series(
    df: pd.DataFrame,
    cadence: str,
    max_interp_points: int,
) -> Tuple[pd.Series, dict]:
    s = df.set_index("__ts")["__y"].sort_index()
    s = s.resample(cadence).mean()
    n_bins = int(s.shape[0])
    n_missing_pre = int(s.isna().sum())

    if max_interp_points > 0:
        s = s.interpolate(method="time", limit=max_interp_points, limit_direction="both")

    n_missing_post = int(s.isna().sum())
    s = s.dropna()

    meta = {
        "resample_bins": n_bins,
        "missing_before_interp": n_missing_pre,
        "missing_after_interp": n_missing_post,
        "points_after_dropna": int(s.shape[0]),
    }
    return s, meta


def _detrend(s: pd.Series, detrend_window: str, zscore: bool) -> pd.Series:
    y = s.astype(float).copy()
    y = y - float(np.nanmean(y.to_numpy(dtype=float)))

    if detrend_window:
        trend = y.rolling(detrend_window, center=True, min_periods=1).median()
        y = y - trend

    if zscore:
        std = float(np.nanstd(y.to_numpy(dtype=float)))
        if std > 0:
            y = y / std
    return y


def _compute_psd(y: np.ndarray, fs_hz: float, segment_days: float) -> Tuple[np.ndarray, np.ndarray, str]:
    # Prefer Welch if SciPy is installed; fallback to FFT periodogram otherwise.
    try:
        from scipy.signal import welch  # type: ignore

        nperseg = max(32, int(round(segment_days * 86400.0 * fs_hz)))
        nperseg = min(nperseg, len(y))
        f_hz, pxx = welch(
            y,
            fs=fs_hz,
            window="hann",
            nperseg=nperseg,
            noverlap=nperseg // 2,
            detrend="constant",
            scaling="density",
            return_onesided=True,
        )
        return f_hz, pxx, "welch"
    except Exception:
        n = len(y)
        if n < 8:
            raise SystemExit("Not enough points for FFT fallback; need at least 8 samples")
        w = np.hanning(n)
        y_w = y * w
        y_w = y_w - np.mean(y_w)
        x = np.fft.rfft(y_w)
        f_hz = np.fft.rfftfreq(n, d=1.0 / fs_hz)
        # Approximate density scaling for comparability.
        scale = fs_hz * np.sum(w**2)
        pxx = (np.abs(x) ** 2) / max(scale, 1e-12)
        return f_hz, pxx, "fft_periodogram"


def _restrict_period_band(
    f_hz: np.ndarray,
    pxx: np.ndarray,
    min_period_hours: float,
    max_period_hours: float,
) -> pd.DataFrame:
    f_hz = np.asarray(f_hz)
    pxx = np.asarray(pxx)
    keep = f_hz > 0
    f = f_hz[keep]
    p = pxx[keep]
    period_h = 1.0 / f / 3600.0
    keep2 = (period_h >= min_period_hours) & (period_h <= max_period_hours)
    out = pd.DataFrame({
        "frequency_hz": f[keep2],
        "period_hours": period_h[keep2],
        "power": p[keep2],
    }).sort_values("period_hours", ascending=True)
    return out.reset_index(drop=True)


def _top_k_peaks(psd_df: pd.DataFrame, k: int) -> pd.DataFrame:
    if psd_df.empty:
        return psd_df.copy()
    df = psd_df.sort_values("power", ascending=False).head(k).copy()
    df["period_days"] = df["period_hours"] / 24.0
    return df[["period_hours", "period_days", "frequency_hz", "power"]].reset_index(drop=True)


def _band_power(psd_df: pd.DataFrame, center_hours: float, tol_frac: float = 0.15) -> float:
    lo = center_hours * (1.0 - tol_frac)
    hi = center_hours * (1.0 + tol_frac)
    d = psd_df[(psd_df["period_hours"] >= lo) & (psd_df["period_hours"] <= hi)]
    if d.empty:
        return float("nan")
    return float(d["power"].mean())


def _save_plot(psd_df: pd.DataFrame, out_png: Path, title: str) -> bool:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:
        return False

    fig, ax = plt.subplots(figsize=(10, 5), dpi=130)
    ax.plot(psd_df["period_hours"], psd_df["power"], lw=1.5)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Period (hours, log scale)")
    ax.set_ylabel("Power Spectral Density (log scale)")
    ax.set_title(title)
    ax.grid(True, which="both", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)
    return True


def _seconds_from_cadence(cadence: str) -> float:
    td = pd.to_timedelta(cadence)
    sec = float(td.total_seconds())
    if sec <= 0:
        raise SystemExit("Cadence must be positive")
    return sec


def run(args: argparse.Namespace) -> None:
    globs = _default_globs(args.input_glob)
    raw = _load_rows(
        globs=globs,
        site=args.site,
        timestamp_col=args.timestamp_col,
        value_col=args.value_col,
        start=args.start,
        end=args.end,
    )

    rs, rs_meta = _resample_series(raw, cadence=args.cadence, max_interp_points=args.max_interp_points)
    if rs.shape[0] < 32:
        raise SystemExit(f"Too few resampled points for PSD: {rs.shape[0]} (<32)")

    y = _detrend(rs, detrend_window=(args.detrend_window or "").strip(), zscore=bool(args.zscore))
    y_np = y.to_numpy(dtype=float)

    cadence_s = _seconds_from_cadence(args.cadence)
    fs_hz = 1.0 / cadence_s

    f_hz, pxx, method = _compute_psd(y_np, fs_hz=fs_hz, segment_days=float(args.segment_days))
    psd = _restrict_period_band(
        f_hz,
        pxx,
        min_period_hours=float(args.min_period_hours),
        max_period_hours=float(args.max_period_hours),
    )

    if psd.empty:
        raise SystemExit("PSD is empty after period filtering. Relax min/max period or increase data duration.")

    peaks = _top_k_peaks(psd, k=int(args.top_k))

    band_summary = {
        "band_24h_power": _band_power(psd, 24.0),
        "band_7d_power": _band_power(psd, 24.0 * 7.0),
        "band_30d_power": _band_power(psd, 24.0 * 30.0),
        "band_90d_power": _band_power(psd, 24.0 * 90.0),
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    name = args.prefix or args.site or "all_sites"
    name = str(name).strip().replace(" ", "_")
    psd_csv = out_dir / f"{name}_deliverypressure_psd.csv"
    peaks_csv = out_dir / f"{name}_deliverypressure_top_peaks.csv"
    summary_json = out_dir / f"{name}_deliverypressure_fourier_summary.json"
    plot_png = out_dir / f"{name}_deliverypressure_psd.png"

    psd.to_csv(psd_csv, index=False)
    peaks.to_csv(peaks_csv, index=False)

    time_min = rs.index.min()
    time_max = rs.index.max()
    duration_hours = float((time_max - time_min).total_seconds() / 3600.0)

    summary = {
        "site": args.site,
        "value_col": args.value_col,
        "timestamp_col": args.timestamp_col,
        "input_globs": globs,
        "method": method,
        "cadence": args.cadence,
        "cadence_seconds": cadence_s,
        "start_utc": None if time_min is None else str(time_min),
        "end_utc": None if time_max is None else str(time_max),
        "duration_hours": duration_hours,
        "raw_rows": int(raw.shape[0]),
        "resampled_points": int(rs.shape[0]),
        "resample_meta": rs_meta,
        "period_filter_hours": {
            "min": float(args.min_period_hours),
            "max": float(args.max_period_hours),
        },
        "detrend_window": (args.detrend_window or ""),
        "zscore": bool(args.zscore),
        "top_peaks": peaks.to_dict(orient="records"),
        "band_summary": band_summary,
        "artifacts": {
            "psd_csv": str(psd_csv),
            "peaks_csv": str(peaks_csv),
            "plot_png": str(plot_png) if not args.no_plot else None,
        },
    }

    plot_written = False
    if not args.no_plot:
        title = f"{name} deliverypressure PSD ({method}, cadence={args.cadence})"
        plot_written = _save_plot(psd, plot_png, title=title)
        if not plot_written:
            summary["artifacts"]["plot_png"] = None
            summary["plot_warning"] = "matplotlib unavailable; skipped PNG"

    with summary_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"[OK] wrote {psd_csv}")
    print(f"[OK] wrote {peaks_csv}")
    if not args.no_plot and plot_written:
        print(f"[OK] wrote {plot_png}")
    print(f"[OK] wrote {summary_json}")


if __name__ == "__main__":
    run(build_argparser().parse_args())
