#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Iterable, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


DEFAULT_RAW_ROOT = "/mnt/d/datasets/svwatergo/raw/plc"
DEFAULT_OUT_DIR = "/mnt/d/datasets/svwatergo/derived/daily_power_usage"
DEFAULT_TICK_KWH = 1.25 / 1000.0


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Compute daily power-meter usage from PLC parquet partitions by subtracting "
            "the first powermeter reading of the day from the last."
        )
    )
    p.add_argument(
        "--input-glob",
        action="append",
        default=None,
        help=(
            "Input parquet glob(s). Repeatable. "
            f"Default: {DEFAULT_RAW_ROOT}/*/date=*/data.parquet"
        ),
    )
    p.add_argument("--site", action="append", default=None, help="Optional site filter. Repeatable.")
    p.add_argument("--year", type=int, default=2025, help="Calendar year filter for output and plotting.")
    p.add_argument("--timestamp-col", default="plctime", help="Timestamp column name.")
    p.add_argument("--powermeter-col", default="powermeter", help="Totalizing power meter column name.")
    p.add_argument(
        "--tick-kwh",
        type=float,
        default=DEFAULT_TICK_KWH,
        help="Conversion from powermeter ticks to kWh. Default follows backend logic.",
    )
    p.add_argument(
        "--out-dir",
        default=DEFAULT_OUT_DIR,
        help="Directory for CSV/parquet/chart outputs.",
    )
    p.add_argument(
        "--prefix",
        default=None,
        help="Optional output filename prefix. Default: power_usage_<year>",
    )
    return p


def default_globs(globs: Iterable[str] | None) -> List[str]:
    return list(globs) if globs else [f"{DEFAULT_RAW_ROOT}/*/date=*/data.parquet"]


def expand(globs: Iterable[str]) -> List[Path]:
    out: List[Path] = []
    for pattern in globs:
        out.extend(Path(p) for p in glob.glob(pattern, recursive=True))
    return sorted(set(out))


def site_from_path(path: Path) -> str:
    for part in path.parts:
        lower = part.lower()
        if lower.startswith("site="):
            return lower.split("=", 1)[1]
    parts = list(path.parts)
    if "plc" in parts:
        idx = parts.index("plc")
        if idx + 1 < len(parts):
            return parts[idx + 1].lower()
    return ""


def date_from_path(path: Path) -> str:
    for part in path.parts:
        if part.startswith("date="):
            return part.split("=", 1)[1]
    return ""


def compute_daily_usage(
    files: Iterable[Path],
    *,
    sites: set[str] | None,
    timestamp_col: str,
    powermeter_col: str,
    year: int,
    tick_kwh: float,
) -> pd.DataFrame:
    rows: List[dict] = []
    for fp in files:
        site = site_from_path(fp)
        if sites and site not in sites:
            continue

        day_str = date_from_path(fp)
        if not day_str:
            continue
        try:
            day = pd.Timestamp(day_str).date()
        except Exception:
            continue
        if day.year != year:
            continue

        try:
            df = pd.read_parquet(fp, columns=[timestamp_col, powermeter_col])
        except Exception:
            df = pd.read_parquet(fp)
            if timestamp_col not in df.columns or powermeter_col not in df.columns:
                continue
            df = df[[timestamp_col, powermeter_col]]

        if df.empty:
            continue

        d = df.copy()
        d["ts"] = pd.to_datetime(d[timestamp_col], utc=True, errors="coerce")
        d["powermeter_num"] = pd.to_numeric(d[powermeter_col], errors="coerce")
        d = d[d["ts"].notna() & d["powermeter_num"].notna()].sort_values("ts")
        if d.empty:
            continue

        first = d.iloc[0]
        last = d.iloc[-1]
        delta_ticks = float(last["powermeter_num"] - first["powermeter_num"])

        rows.append(
            {
                "site": site,
                "date": pd.Timestamp(day),
                "row_count": int(len(d)),
                "first_plctime_utc": first["ts"],
                "last_plctime_utc": last["ts"],
                "powermeter_start": float(first["powermeter_num"]),
                "powermeter_end": float(last["powermeter_num"]),
                "powermeter_delta_ticks": delta_ticks,
                "power_kwh": delta_ticks * tick_kwh,
                "source_file": str(fp),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "site",
                "date",
                "row_count",
                "first_plctime_utc",
                "last_plctime_utc",
                "powermeter_start",
                "powermeter_end",
                "powermeter_delta_ticks",
                "power_kwh",
                "source_file",
            ]
        )

    out = pd.DataFrame(rows).sort_values(["site", "date"]).reset_index(drop=True)
    return out


def write_outputs(df: pd.DataFrame, *, out_dir: Path, prefix: str, year: int, tick_kwh: float) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / f"{prefix}.csv"
    parquet_path = out_dir / f"{prefix}.parquet"
    png_path = out_dir / f"{prefix}.png"
    summary_path = out_dir / f"{prefix}_summary.json"

    df.to_csv(csv_path, index=False)
    df.to_parquet(parquet_path, index=False)

    summary = {
        "year": year,
        "tick_kwh": tick_kwh,
        "days": int(len(df)),
        "sites": sorted(df["site"].dropna().astype(str).unique().tolist()) if not df.empty else [],
        "total_power_kwh": float(df["power_kwh"].sum()) if not df.empty else 0.0,
        "csv": str(csv_path),
        "parquet": str(parquet_path),
        "chart_png": str(png_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    plot_daily_usage(df, png_path, year=year)
    return summary


def plot_daily_usage(df: pd.DataFrame, out_png: Path, *, year: int) -> None:
    if df.empty:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.text(0.5, 0.5, f"No daily power usage rows found for {year}", ha="center", va="center")
        ax.set_axis_off()
        fig.tight_layout()
        fig.savefig(out_png, dpi=160)
        plt.close(fig)
        return

    sites = sorted(df["site"].astype(str).unique().tolist())
    fig, axes = plt.subplots(len(sites), 1, figsize=(16, max(4, 3.6 * len(sites))), sharex=True)
    if len(sites) == 1:
        axes = [axes]

    for ax, site in zip(axes, sites):
        sub = df[df["site"] == site].sort_values("date")
        ax.bar(sub["date"], sub["power_kwh"], width=0.9, color="#2b6f8a", edgecolor="#18485a", linewidth=0.3)
        ax.set_title(site)
        ax.set_ylabel("kWh/day")
        ax.grid(axis="y", alpha=0.25)

    axes[-1].set_xlabel(f"Date ({year})")
    fig.suptitle(f"Daily Power Usage by Site ({year})", y=0.995, fontsize=14)
    fig.tight_layout()
    fig.savefig(out_png, dpi=160)
    plt.close(fig)


def main() -> None:
    args = build_argparser().parse_args()
    files = expand(default_globs(args.input_glob))
    sites = {s.strip().lower() for s in (args.site or []) if s and s.strip()} or None
    prefix = args.prefix or f"power_usage_{args.year}"

    df = compute_daily_usage(
        files,
        sites=sites,
        timestamp_col=args.timestamp_col,
        powermeter_col=args.powermeter_col,
        year=args.year,
        tick_kwh=args.tick_kwh,
    )
    summary = write_outputs(
        df,
        out_dir=Path(args.out_dir),
        prefix=prefix,
        year=args.year,
        tick_kwh=args.tick_kwh,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
