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
from window_pca.model import decode_alarmword_bits


DEFAULT_RAW_ROOT = "/mnt/d/datasets/svwatergo/raw/plc"
DEFAULT_OUT_DIR = "/mnt/d/datasets/svwatergo/derived/daily_power_usage"
DEFAULT_TICK_KWH = 1.25 / 1000.0
DEFAULT_PERMEATE_COL = "totalroflow"
DEFAULT_ALARM_COL = "alarm"
DEFAULT_ALARMWORD_COL = "alarmword"


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
        "--permeate-col",
        default=DEFAULT_PERMEATE_COL,
        help="Totalizing permeate flow column name used for daily delta calculations.",
    )
    p.add_argument("--alarm-col", default=DEFAULT_ALARM_COL, help="Alarm boolean/status column name.")
    p.add_argument("--alarmword-col", default=DEFAULT_ALARMWORD_COL, help="Alarm word/status code column name.")
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
    permeate_col: str,
    alarm_col: str,
    alarmword_col: str,
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
            read_cols = [timestamp_col, powermeter_col, permeate_col, alarm_col, alarmword_col]
            df = pd.read_parquet(fp, columns=read_cols)
        except Exception:
            df = pd.read_parquet(fp)
            if timestamp_col not in df.columns or powermeter_col not in df.columns or permeate_col not in df.columns:
                continue
            keep = [timestamp_col, powermeter_col, permeate_col]
            if alarm_col in df.columns:
                keep.append(alarm_col)
            if alarmword_col in df.columns:
                keep.append(alarmword_col)
            df = df[keep]

        if df.empty:
            continue

        d = df.copy()
        d["ts"] = pd.to_datetime(d[timestamp_col], utc=True, errors="coerce")
        d["powermeter_num"] = pd.to_numeric(d[powermeter_col], errors="coerce")
        d["permeate_num"] = pd.to_numeric(d[permeate_col], errors="coerce")
        if alarm_col in d.columns:
            alarm_series = d[alarm_col]
            if alarm_series.dtype == bool:
                d["alarm_active"] = alarm_series.fillna(False)
            else:
                norm = alarm_series.astype(str).str.strip().str.lower()
                d["alarm_active"] = norm.isin({"1", "true", "t", "yes", "y", "alarm"})
        else:
            d["alarm_active"] = False
        if alarmword_col in d.columns:
            d["alarmword_num"] = pd.to_numeric(d[alarmword_col], errors="coerce").fillna(0)
        else:
            d["alarmword_num"] = 0
        d = d[d["ts"].notna()].sort_values("ts")
        if d.empty:
            continue

        power_rows = d[d["powermeter_num"].notna()]
        if power_rows.empty:
            continue
        power_first = power_rows.iloc[0]
        power_last = power_rows.iloc[-1]
        delta_ticks = float(power_last["powermeter_num"] - power_first["powermeter_num"])

        permeate_rows = d[d["permeate_num"].notna()]
        permeate_first = permeate_rows.iloc[0] if not permeate_rows.empty else None
        permeate_last = permeate_rows.iloc[-1] if not permeate_rows.empty else None
        permeate_delta = (
            float(permeate_last["permeate_num"] - permeate_first["permeate_num"])
            if permeate_first is not None and permeate_last is not None
            else None
        )
        alarm_rows = d[d["alarm_active"]]
        had_alarm = bool(not alarm_rows.empty)
        active_alarmwords = sorted({int(v) for v in alarm_rows.loc[alarm_rows["alarmword_num"] != 0, "alarmword_num"].tolist()})
        alarm_labels: list[str] = []
        for word in active_alarmwords:
            alarm_labels.extend(decode_alarmword_bits(word))
        alarm_labels = sorted(dict.fromkeys(alarm_labels))

        rows.append(
            {
                "site": site,
                "date": pd.Timestamp(day),
                "row_count": int(len(power_rows)),
                "first_plctime_utc": power_first["ts"],
                "last_plctime_utc": power_last["ts"],
                "powermeter_start": float(power_first["powermeter_num"]),
                "powermeter_end": float(power_last["powermeter_num"]),
                "powermeter_delta_ticks": delta_ticks,
                "power_kwh": delta_ticks * tick_kwh,
                "permeate_row_count": int(len(permeate_rows)),
                "permeate_first_plctime_utc": permeate_first["ts"] if permeate_first is not None else pd.NaT,
                "permeate_last_plctime_utc": permeate_last["ts"] if permeate_last is not None else pd.NaT,
                "permeate_start_total": float(permeate_first["permeate_num"]) if permeate_first is not None else None,
                "permeate_end_total": float(permeate_last["permeate_num"]) if permeate_last is not None else None,
                "permeate_delta_gallons": permeate_delta,
                "had_alarm": had_alarm,
                "alarmword_values": ",".join(str(v) for v in active_alarmwords),
                "alarm_labels": " | ".join(alarm_labels),
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
                "permeate_row_count",
                "permeate_first_plctime_utc",
                "permeate_last_plctime_utc",
                "permeate_start_total",
                "permeate_end_total",
                "permeate_delta_gallons",
                "had_alarm",
                "alarmword_values",
                "alarm_labels",
                "source_file",
            ]
        )

    out = pd.DataFrame(rows).sort_values(["site", "date"]).reset_index(drop=True)
    return out


def write_outputs(df: pd.DataFrame, *, out_dir: Path, prefix: str, year: int, tick_kwh: float) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / f"{prefix}.csv"
    parquet_path = out_dir / f"{prefix}.parquet"
    power_png_path = out_dir / f"{prefix}_power_kwh.png"
    permeate_png_path = out_dir / f"{prefix}_permeate_gallons.png"
    summary_path = out_dir / f"{prefix}_summary.json"

    df.to_csv(csv_path, index=False)
    df.to_parquet(parquet_path, index=False)

    summary = {
        "year": year,
        "tick_kwh": tick_kwh,
        "days": int(len(df)),
        "sites": sorted(df["site"].dropna().astype(str).unique().tolist()) if not df.empty else [],
        "total_power_kwh": float(df["power_kwh"].sum()) if not df.empty else 0.0,
        "total_permeate_gallons": float(df["permeate_delta_gallons"].fillna(0).sum()) if not df.empty else 0.0,
        "alarm_days": int(df["had_alarm"].fillna(False).sum()) if not df.empty else 0,
        "csv": str(csv_path),
        "parquet": str(parquet_path),
        "power_chart_png": str(power_png_path),
        "permeate_chart_png": str(permeate_png_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    plot_daily_usage(
        df,
        power_png_path,
        year=year,
        value_col="power_kwh",
        title=f"Daily Power Usage by Site ({year})",
        ylabel="kWh/day",
    )
    plot_daily_usage(
        df,
        permeate_png_path,
        year=year,
        value_col="permeate_delta_gallons",
        title=f"Daily Permeate Delta by Site ({year})",
        ylabel="Gallons/day",
    )
    return summary


def plot_daily_usage(
    df: pd.DataFrame,
    out_png: Path,
    *,
    year: int,
    value_col: str,
    title: str,
    ylabel: str,
) -> None:
    if df.empty:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.text(0.5, 0.5, f"No daily rows found for {year}", ha="center", va="center")
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
        vals = pd.to_numeric(sub[value_col], errors="coerce").fillna(0)
        alarm_mask = sub["had_alarm"].fillna(False).astype(bool)
        colors = ["#c0392b" if flagged else "#2b6f8a" for flagged in alarm_mask]
        edges = ["#7b241c" if flagged else "#18485a" for flagged in alarm_mask]
        ax.bar(sub["date"], vals, width=0.9, color=colors, edgecolor=edges, linewidth=0.3)
        ax.set_title(site)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
        ymax = float(vals.max()) if len(vals) else 0.0
        label_y = ymax * 0.02 if ymax > 0 else 0.1
        for _, row in sub[alarm_mask].iterrows():
            value = pd.to_numeric(pd.Series([row[value_col]]), errors="coerce").fillna(0).iloc[0]
            label_lines = [pd.Timestamp(row["date"]).strftime("%Y-%m-%d")]
            if str(row.get("alarm_labels", "")).strip():
                label_lines.extend(str(row["alarm_labels"]).split(" | "))
            elif str(row.get("alarmword_values", "")).strip():
                label_lines.append(f"alarmword={row['alarmword_values']}")
            ax.annotate(
                "\n".join(label_lines),
                (row["date"], value),
                textcoords="offset points",
                xytext=(0, 4 if value >= 0 else -18),
                ha="center",
                va="bottom" if value >= 0 else "top",
                rotation=90,
                fontsize=7,
                color="#7b241c",
            )
        if alarm_mask.any():
            ax.text(
                0.995,
                0.95,
                "Red = alarm day",
                transform=ax.transAxes,
                ha="right",
                va="top",
                fontsize=8,
                color="#7b241c",
            )

    axes[-1].set_xlabel(f"Date ({year})")
    fig.suptitle(title, y=0.995, fontsize=14)
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
        permeate_col=args.permeate_col,
        alarm_col=args.alarm_col,
        alarmword_col=args.alarmword_col,
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
