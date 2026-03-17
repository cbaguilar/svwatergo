from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd

from ..utils.parquet_discovery import discover_date_partitioned_parquets


TIMESTAMP_CANDIDATES = ("plctime", "timestamp", "ts", "time", "datetime", "recordtime")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Analyze date-partitioned Bluerock parquet files and report daily data gaps "
            "above a threshold."
        )
    )
    p.add_argument(
        "--dataset-root",
        default="data/raw/plc/bluerock",
        help="Root containing date=YYYY-MM-DD partitions with parquet files",
    )
    p.add_argument(
        "--dataset-filename",
        default="data.parquet",
        help="Filename inside each date partition",
    )
    p.add_argument("--date-from", default="2024-01-01", help="Inclusive lower bound (YYYY-MM-DD)")
    p.add_argument("--date-to", default="2024-04-30", help="Inclusive upper bound (YYYY-MM-DD)")
    p.add_argument(
        "--timestamp-col",
        default="",
        help="Timestamp column to use. Defaults to auto-detecting a known timestamp column.",
    )
    p.add_argument(
        "--gap-minutes",
        type=float,
        default=5.0,
        help="Only gaps strictly larger than this many minutes are counted",
    )
    p.add_argument(
        "--expected-cadence-seconds",
        type=float,
        default=0.0,
        help="Expected sample cadence. If <= 0, estimate from the median positive gap.",
    )
    p.add_argument(
        "--out-daily-csv",
        default="data/derived/bluerock_daily_gaps_2024q1_q2.csv",
        help="Path for daily summary CSV",
    )
    p.add_argument(
        "--out-gap-csv",
        default="data/derived/bluerock_gap_details_2024q1_q2.csv",
        help="Path for per-gap detail CSV",
    )
    p.add_argument(
        "--out-png",
        default="data/derived/bluerock_daily_lost_minutes_2024q1_q2.png",
        help="Path for daily lost-minutes chart PNG",
    )
    return p.parse_args()


def _choose_timestamp_col(columns: Iterable[str], requested: str) -> str:
    cols = {str(c) for c in columns}
    if str(requested).strip():
        if requested not in cols:
            raise ValueError(f"Requested timestamp column not found: {requested}")
        return requested
    for candidate in TIMESTAMP_CANDIDATES:
        if candidate in cols:
            return candidate
    raise ValueError(
        "Could not auto-detect timestamp column. "
        f"Checked candidates: {', '.join(TIMESTAMP_CANDIDATES)}"
    )


def _load_dataset(paths: list[Path], timestamp_col: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths:
        df = pd.read_parquet(path)
        if timestamp_col not in df.columns:
            raise ValueError(f"{path} does not contain timestamp column {timestamp_col!r}")
        frames.append(df[[timestamp_col]].copy())
    if not frames:
        return pd.DataFrame(columns=[timestamp_col])
    out = pd.concat(frames, axis=0, ignore_index=True, sort=False)
    out[timestamp_col] = pd.to_datetime(out[timestamp_col], errors="coerce", utc=True)
    out = out[out[timestamp_col].notna()].sort_values(timestamp_col).reset_index(drop=True)
    return out


def _estimate_expected_cadence_seconds(ts: pd.Series) -> float:
    deltas = ts.diff().dt.total_seconds()
    deltas = deltas[(deltas.notna()) & (deltas > 0)]
    if deltas.empty:
        return 0.0
    return float(deltas.median())


def _build_gap_details(ts: pd.Series, gap_threshold_seconds: float, expected_cadence_seconds: float) -> pd.DataFrame:
    prev_ts = ts.shift(1)
    delta_s = (ts - prev_ts).dt.total_seconds()
    gaps = pd.DataFrame(
        {
            "prev_ts": prev_ts,
            "next_ts": ts,
            "gap_seconds": delta_s,
        }
    )
    gaps = gaps[gaps["gap_seconds"] > float(gap_threshold_seconds)].copy()
    if gaps.empty:
        return pd.DataFrame(
            columns=[
                "day",
                "prev_ts",
                "next_ts",
                "gap_seconds",
                "gap_minutes",
                "lost_seconds",
                "lost_minutes",
            ]
        )
    cadence = max(float(expected_cadence_seconds), 0.0)
    gaps["lost_seconds"] = (gaps["gap_seconds"] - cadence).clip(lower=0.0)
    gaps["gap_minutes"] = gaps["gap_seconds"] / 60.0
    gaps["lost_minutes"] = gaps["lost_seconds"] / 60.0
    gaps["day"] = gaps["prev_ts"].dt.strftime("%Y-%m-%d")
    return gaps[["day", "prev_ts", "next_ts", "gap_seconds", "gap_minutes", "lost_seconds", "lost_minutes"]]


def _allocate_gap_time_by_day(gap_details: pd.DataFrame, expected_cadence_seconds: float) -> pd.DataFrame:
    if gap_details.empty:
        return pd.DataFrame(columns=["day", "gap_minutes", "lost_minutes"])

    rows: list[dict[str, object]] = []
    for row in gap_details.itertuples(index=False):
        start = pd.Timestamp(row.prev_ts)
        end = pd.Timestamp(row.next_ts)
        if pd.isna(start) or pd.isna(end) or end <= start:
            continue
        total_gap_seconds = max((end - start).total_seconds(), 0.0)
        total_lost_seconds = max(total_gap_seconds - float(expected_cadence_seconds), 0.0)
        cursor = start
        while cursor < end:
            next_midnight = cursor.normalize() + pd.Timedelta(days=1)
            chunk_end = min(end, next_midnight)
            elapsed_seconds = max((chunk_end - cursor).total_seconds(), 0.0)
            if elapsed_seconds > 0:
                lost_seconds = 0.0
                if total_gap_seconds > 0:
                    lost_seconds = total_lost_seconds * (elapsed_seconds / total_gap_seconds)
                rows.append(
                    {
                        "day": cursor.strftime("%Y-%m-%d"),
                        "gap_minutes": elapsed_seconds / 60.0,
                        "lost_minutes": lost_seconds / 60.0,
                    }
                )
            cursor = chunk_end

    if not rows:
        return pd.DataFrame(columns=["day", "gap_minutes", "lost_minutes"])

    alloc = pd.DataFrame(rows)
    alloc = alloc.groupby("day", as_index=False).agg(
        gap_minutes=("gap_minutes", "sum"),
        lost_minutes=("lost_minutes", "sum"),
    )
    return alloc


def _build_daily_summary(
    ts: pd.Series,
    gap_details: pd.DataFrame,
    expected_cadence_seconds: float,
    date_from: str,
    date_to: str,
) -> pd.DataFrame:
    day_key = ts.dt.strftime("%Y-%m-%d")
    daily_rows = pd.DataFrame(
        {
            "day": day_key,
            "timestamp": ts,
        }
    ).groupby("day", as_index=False).agg(
        first_ts=("timestamp", "min"),
        last_ts=("timestamp", "max"),
        row_count=("timestamp", "size"),
    )
    all_days = pd.DataFrame(
        {
            "day": pd.date_range(start=str(date_from), end=str(date_to), freq="D", tz="UTC").strftime("%Y-%m-%d")
        }
    )

    daily_gaps = gap_details.groupby("day", as_index=False).agg(
        gap_count=("gap_seconds", "size"),
        largest_gap_minutes=("gap_minutes", "max"),
    )
    daily_alloc = _allocate_gap_time_by_day(gap_details, expected_cadence_seconds)

    out = (
        all_days.merge(daily_rows, on="day", how="left")
        .merge(daily_gaps, on="day", how="left")
        .merge(daily_alloc, on="day", how="left")
    )
    out["partition_has_rows"] = out["row_count"].fillna(0).astype(int) > 0
    out["row_count"] = out["row_count"].fillna(0).astype(int)
    out["gap_count"] = out["gap_count"].fillna(0).astype(int)
    for col in ("largest_gap_minutes", "gap_minutes", "lost_minutes"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    out = out.rename(columns={"gap_minutes": "total_gap_minutes"})
    return out.sort_values("day").reset_index(drop=True)


def _write_daily_lost_minutes_plot(daily: pd.DataFrame, out_png: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as e:
        raise SystemExit("Missing matplotlib. Install: pip install matplotlib") from e

    plot_df = daily.copy()
    plot_df["day_dt"] = pd.to_datetime(plot_df["day"], utc=True, errors="coerce")
    plot_df["lost_minutes"] = pd.to_numeric(plot_df["lost_minutes"], errors="coerce").fillna(0.0)

    fig, ax = plt.subplots(figsize=(10.5, 4.2), dpi=150, constrained_layout=True)
    colors = plot_df["partition_has_rows"].map({True: "#1f77b4", False: "#d62728"}).fillna("#1f77b4")
    ax.bar(plot_df["day_dt"], plot_df["lost_minutes"], width=0.9, color=colors)
    ax.set_title("Impact of Compressed Retries on Site A Data Loss")
    ax.set_xlabel("Day")
    ax.set_ylabel("Total Data Loss, Minutes")
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)

    x_start = pd.Timestamp("2024-02-20", tz="UTC")
    x_end = pd.Timestamp("2024-04-15", tz="UTC")
    ax.set_xlim(x_start, x_end)

    ymax = float(plot_df["lost_minutes"].max()) if not plot_df.empty else 0.0
    text_top = max(ymax * 1.12, 120.0)
    ax.set_ylim(0.0, text_top)

    def _lost_minutes_on(day: str) -> float:
        day_ts = pd.Timestamp(day, tz="UTC")
        match = plot_df.loc[plot_df["day_dt"] == day_ts, "lost_minutes"]
        if match.empty:
            return 0.0
        return float(match.iloc[0])

    ann1_day = pd.Timestamp("2024-03-18", tz="UTC")
    ann1_y = _lost_minutes_on("2024-03-18")
    ax.annotate(
        "Added message retries\nwith zip compression",
        xy=(ann1_day, ann1_y),
        xytext=(pd.Timestamp("2024-03-13", tz="UTC"), max(text_top * 0.78, ann1_y + 140.0)),
        textcoords="data",
        arrowprops={"arrowstyle": "->", "color": "#444444", "lw": 1.0},
        ha="left",
        va="bottom",
        fontsize=9,
    )

    ann_reg_day = pd.Timestamp("2024-03-24", tz="UTC")
    ann_reg_y = _lost_minutes_on("2024-03-24")
    ax.annotate(
        "Domain routing errors begin\nwith registrar",
        xy=(ann_reg_day, ann_reg_y),
        xytext=(pd.Timestamp("2024-03-21", tz="UTC"), max(text_top * 0.48, ann_reg_y + 180.0)),
        textcoords="data",
        arrowprops={"arrowstyle": "->", "color": "#444444", "lw": 1.0},
        ha="left",
        va="bottom",
        fontsize=9,
    )

    ann2_day = pd.Timestamp("2024-03-27", tz="UTC")
    ann2_y = _lost_minutes_on("2024-03-27")
    ax.annotate(
        "Adding IP fallback",
        xy=(ann2_day, ann2_y),
        xytext=(pd.Timestamp("2024-03-30", tz="UTC"), max(text_top * 0.60, ann2_y + 180.0)),
        textcoords="data",
        arrowprops={"arrowstyle": "->", "color": "#444444", "lw": 1.0},
        ha="left",
        va="bottom",
        fontsize=9,
    )

    ann3_day = pd.Timestamp("2024-03-29", tz="UTC")
    ann3_y = _lost_minutes_on("2024-03-29")
    ax.annotate(
        "Data connection issues\nwere resolved",
        xy=(ann3_day, ann3_y),
        xytext=(pd.Timestamp("2024-04-02", tz="UTC"), max(text_top * 0.34, ann3_y + 120.0)),
        textcoords="data",
        arrowprops={"arrowstyle": "->", "color": "#444444", "lw": 1.0},
        ha="left",
        va="bottom",
        fontsize=9,
    )

    if not plot_df.empty:
        fig.autofmt_xdate(rotation=45, ha="right")

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=160)
    plt.close(fig)


def main() -> int:
    args = _parse_args()
    dataset_root = Path(args.dataset_root)
    paths = discover_date_partitioned_parquets(
        dataset_root,
        filename=str(args.dataset_filename),
        date_from=str(args.date_from),
        date_to=str(args.date_to),
    )
    if not paths:
        raise SystemExit(
            f"No parquet files found under {dataset_root} for {args.date_from} through {args.date_to}"
        )

    sample_columns = pd.read_parquet(paths[0]).columns
    timestamp_col = _choose_timestamp_col(sample_columns, str(args.timestamp_col))
    df = _load_dataset(paths, timestamp_col)
    if df.empty:
        raise SystemExit("Resolved parquet files but no valid timestamps were found")

    expected_cadence_seconds = float(args.expected_cadence_seconds)
    if expected_cadence_seconds <= 0:
        expected_cadence_seconds = _estimate_expected_cadence_seconds(df[timestamp_col])

    gap_threshold_seconds = float(args.gap_minutes) * 60.0
    gap_details = _build_gap_details(df[timestamp_col], gap_threshold_seconds, expected_cadence_seconds)
    daily = _build_daily_summary(
        df[timestamp_col],
        gap_details,
        expected_cadence_seconds,
        str(args.date_from),
        str(args.date_to),
    )

    out_daily = Path(args.out_daily_csv)
    out_gap = Path(args.out_gap_csv)
    out_png = Path(args.out_png)
    out_daily.parent.mkdir(parents=True, exist_ok=True)
    out_gap.parent.mkdir(parents=True, exist_ok=True)
    daily.to_csv(out_daily, index=False)
    gap_details.to_csv(out_gap, index=False)
    _write_daily_lost_minutes_plot(daily, out_png)

    total_lost_minutes = float(gap_details["lost_minutes"].sum()) if not gap_details.empty else 0.0
    print(f"Resolved files           : {len(paths)}")
    print(f"Timestamp column         : {timestamp_col}")
    print(f"Expected cadence seconds : {expected_cadence_seconds:.3f}")
    print(f"Gap threshold minutes    : {float(args.gap_minutes):.3f}")
    print(f"Days summarized          : {len(daily)}")
    print(f"Gaps found               : {len(gap_details)}")
    print(f"Total lost minutes       : {total_lost_minutes:.3f}")
    print(f"Daily summary CSV        : {out_daily}")
    print(f"Gap detail CSV           : {out_gap}")
    print(f"Lost-minutes PNG         : {out_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
