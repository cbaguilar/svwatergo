#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from python.analytics.site_alias import alias_site_names
from python.units import label_with_unit


DEFAULT_INCLUDE_REGEX = (
    r"flow",
    r"pressure",
    r"conduct",
    r"tds",
    r"nitrate",
)

DEFAULT_EXCLUDE_REGEX = (
    r"^total.*flow",
    r"^daily.*flow",
    r"state",
    r"alarm",
    r"run$",
    r"mode",
    r"command",
    r"setpoint",
)

WINDOW_FEATURES_DEFAULT_INCLUDE_REGEX = (
    r"__mean_tw$",
)

WINDOW_FEATURES_DEFAULT_EXCLUDE_REGEX = DEFAULT_EXCLUDE_REGEX + (
    r"__d1$",
    r"__sec_since_transition$",
    r"__transitions$",
    r"__duty$",
)


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Render histogram atlases for PLC flow, pressure, conductivity, and nitrate signals over a time range. "
            "Discovers daily raw PLC parquet files by site/date and writes per-group PNGs plus CSV/JSON summaries."
        )
    )
    p.add_argument("--local-root", required=True, help="Root directory containing parquet days")
    p.add_argument(
        "--dataset-kind",
        choices=["raw_plc", "window_features"],
        default="raw_plc",
        help="Input dataset layout to discover and summarize",
    )
    p.add_argument("--site", required=True, help="Site name, e.g. bluerock/pryorfarm/santateresa")
    p.add_argument("--date-from", required=True, help="Start date YYYY-MM-DD (inclusive)")
    p.add_argument("--date-to", required=True, help="End date YYYY-MM-DD (inclusive)")
    p.add_argument("--timestamp-col", default=None, help="Timestamp column; defaults depend on --dataset-kind")
    p.add_argument("--window-s", type=int, default=None, help="Window size for --dataset-kind window_features")
    p.add_argument("--stride-s", type=int, default=None, help="Optional stride for --dataset-kind window_features")
    p.add_argument("--start", default=None, help="Optional UTC timestamp start filter (inclusive)")
    p.add_argument("--end", default=None, help="Optional UTC timestamp end filter (exclusive)")
    p.add_argument("--bins", type=int, default=80, help="Histogram bin count")
    p.add_argument("--bin-width-flow", type=float, default=0.02, help="Explicit flow histogram bucket width")
    p.add_argument("--bin-width-pressure", type=float, default=0.02, help="Explicit pressure histogram bucket width")
    p.add_argument(
        "--bin-width-water-quality",
        type=float,
        default=0.02,
        help="Explicit conductivity/nitrate histogram bucket width",
    )
    p.add_argument("--bin-width-other", type=float, default=None, help="Explicit bucket width for uncategorized signals")
    p.add_argument(
        "--include-regex",
        action="append",
        default=[],
        help="Column include regex. Repeatable. Defaults target flow/pressure/conductivity/nitrate.",
    )
    p.add_argument(
        "--exclude-regex",
        action="append",
        default=[],
        help="Column exclude regex. Repeatable. Defaults exclude totals/dailies/states/runs.",
    )
    p.add_argument(
        "--signal-col",
        action="append",
        default=[],
        help="Explicit signal columns. Repeatable. If set, skips regex auto-discovery.",
    )
    p.add_argument("--max-cols", type=int, default=24, help="Max signals to render")
    p.add_argument("--cols-per-page", type=int, default=6, help="Subplots per atlas page")
    p.add_argument("--fig-width", type=float, default=16.0, help="Atlas figure width in inches")
    p.add_argument("--fig-row-height", type=float, default=3.6, help="Per-row height in inches")
    p.add_argument("--density", action="store_true", help="Plot density instead of counts")
    p.add_argument("--log-y", action="store_true", help="Use log scale on histogram y-axis")
    p.add_argument(
        "--split-state-col",
        default="state",
        help="Optional categorical state column to split histograms. Defaults depend on --dataset-kind. Use 'none' to disable.",
    )
    p.add_argument("--out-dir", default="./hist_out", help="Output directory")
    p.add_argument("--out-prefix", default=None, help="Output prefix")
    p.add_argument("--verbose", action="store_true")
    return p


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(str(s))


def _daterange(d0: dt.date, d1: dt.date) -> List[dt.date]:
    if d1 < d0:
        raise SystemExit("--date-to must be >= --date-from")
    n = (d1 - d0).days
    return [d0 + dt.timedelta(days=i) for i in range(n + 1)]


def _sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name)).strip("_")


def _normalize_optional_col(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.lower() in {"none", "off", "false", "no"}:
        return None
    return text


def _candidate_day_paths(root: Path, site: str, day: str) -> List[Path]:
    return [
        root / site / f"date={day}" / "data.parquet",
        root / f"site={site}" / f"date={day}" / "data.parquet",
        root / "plc" / site / f"date={day}" / "data.parquet",
        root / "plc" / f"site={site}" / f"date={day}" / "data.parquet",
    ]


def _candidate_window_feature_paths(
    root: Path,
    site: str,
    day: str,
    window_s: Optional[int],
    stride_s: Optional[int],
) -> List[Path]:
    paths: List[Path] = []
    if window_s is not None:
        ws = int(window_s)
        if stride_s is not None and int(stride_s) != ws:
            paths.append(
                root
                / f"window_s={ws}"
                / f"stride_s={int(stride_s)}"
                / f"site={site}"
                / f"date={day}"
                / "window_features.parquet"
            )
        paths.append(
            root
            / f"window_s={ws}"
            / f"site={site}"
            / f"date={day}"
            / "window_features.parquet"
        )
    else:
        paths.append(root / f"site={site}" / f"date={day}" / "window_features.parquet")
    return paths


def _discover_files(
    local_root: str,
    site: str,
    date_from: str,
    date_to: str,
    *,
    dataset_kind: str,
    window_s: Optional[int],
    stride_s: Optional[int],
) -> List[Path]:
    root = Path(local_root)
    out: List[Path] = []
    for day in _daterange(_parse_date(date_from), _parse_date(date_to)):
        day_str = day.isoformat()
        if dataset_kind == "window_features":
            candidates = _candidate_window_feature_paths(root, site, day_str, window_s, stride_s)
        else:
            candidates = _candidate_day_paths(root, site, day_str)
        for candidate in candidates:
            if candidate.exists():
                out.append(candidate)
                break
    return out


def _default_timestamp_col(dataset_kind: str) -> str:
    if dataset_kind == "window_features":
        return "window_start_ts"
    return "plctime"


def _default_split_state_col(dataset_kind: str) -> str:
    if dataset_kind == "window_features":
        return "state__last"
    return "state"


def _matches_any(text: str, patterns: Sequence[str]) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def _select_signal_cols(
    schema_cols: Sequence[str],
    explicit: Sequence[str],
    include_regex: Sequence[str],
    exclude_regex: Sequence[str],
    max_cols: int,
    *,
    dataset_kind: str,
) -> List[str]:
    if explicit:
        chosen = []
        schema_map = {c.lower(): c for c in schema_cols}
        for col in explicit:
            found = schema_map.get(col.lower())
            if found:
                chosen.append(found)
        return chosen[: max(1, int(max_cols))]

    default_inc, default_exc = _default_signal_regex(dataset_kind)
    includes = list(include_regex) or list(default_inc)
    excludes = list(exclude_regex) or list(default_exc)
    chosen = []
    for col in schema_cols:
        cl = col.lower()
        if not _matches_any(cl, includes):
            continue
        if _matches_any(cl, excludes):
            continue
        chosen.append(col)
    chosen = sorted(dict.fromkeys(chosen))
    return chosen[: max(1, int(max_cols))]


def _default_signal_regex(dataset_kind: str) -> tuple[Sequence[str], Sequence[str]]:
    if dataset_kind == "window_features":
        return WINDOW_FEATURES_DEFAULT_INCLUDE_REGEX, WINDOW_FEATURES_DEFAULT_EXCLUDE_REGEX
    return DEFAULT_INCLUDE_REGEX, DEFAULT_EXCLUDE_REGEX


def _group_for_column(col: str) -> str:
    cl = col.lower()
    if "pressure" in cl:
        return "pressure"
    if "flow" in cl:
        return "flow"
    if "conduct" in cl or "tds" in cl or "nitrate" in cl:
        return "water_quality"
    return "other"


def _load_data(
    files: Sequence[Path],
    timestamp_col: str,
    signal_cols: Sequence[str],
    split_state_col: Optional[str],
    start: Optional[str],
    end: Optional[str],
) -> pd.DataFrame:
    start_ts = pd.Timestamp(start, tz="UTC") if start else None
    end_ts = pd.Timestamp(end, tz="UTC") if end else None
    keep_cols = [timestamp_col] + list(signal_cols)
    if split_state_col:
        keep_cols.append(split_state_col)

    rows: List[pd.DataFrame] = []
    for fp in files:
        df = pd.read_parquet(fp, columns=keep_cols)
        if df.empty:
            continue
        out = pd.DataFrame()
        out["__ts"] = pd.to_datetime(df[timestamp_col], utc=True, errors="coerce")
        for col in signal_cols:
            out[col] = pd.to_numeric(df[col], errors="coerce")
        if split_state_col:
            out["__split_state"] = pd.to_numeric(df[split_state_col], errors="coerce")
        out = out[out["__ts"].notna()]
        if start_ts is not None:
            out = out[out["__ts"] >= start_ts]
        if end_ts is not None:
            out = out[out["__ts"] < end_ts]
        if not out.empty:
            rows.append(out)

    if not rows:
        raise SystemExit("No rows found after filtering")
    return pd.concat(rows, axis=0, ignore_index=True)


def _split_value_label(value: object) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "unknown"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        if float(value).is_integer():
            return str(int(value))
        return f"{float(value):g}"
    return str(value)


def _hist_edges(x: np.ndarray, *, bins: int, bin_width: Optional[float]) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return np.linspace(0.0, 1.0, max(2, int(bins) + 1))

    x_min = float(np.min(x))
    x_max = float(np.max(x))
    if bin_width is not None and float(bin_width) > 0:
        width = float(bin_width)
        lo = math.floor(x_min / width) * width
        hi = math.ceil(x_max / width) * width
        if hi <= lo:
            hi = lo + width
        n_steps = max(1, int(round((hi - lo) / width)))
        return lo + np.arange(n_steps + 1, dtype=float) * width

    if x_max <= x_min:
        x_max = x_min + 1e-9
    return np.linspace(x_min, x_max, max(2, int(bins) + 1))


def _bin_width_for_group(group_name: str, args: argparse.Namespace) -> Optional[float]:
    if group_name == "flow":
        return args.bin_width_flow
    if group_name == "pressure":
        return args.bin_width_pressure
    if group_name == "water_quality":
        return args.bin_width_water_quality
    return args.bin_width_other


def _summary_rows(
    df: pd.DataFrame,
    signal_cols: Sequence[str],
    bins: int,
    args: argparse.Namespace,
    split_label: Optional[str] = None,
) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for col in signal_cols:
        x = pd.to_numeric(df[col], errors="coerce").dropna().to_numpy(dtype=float)
        if x.size == 0:
            continue
        q05, q50, q95 = np.quantile(x, [0.05, 0.5, 0.95])
        group_name = _group_for_column(col)
        edges = _hist_edges(x, bins=max(2, int(bins)), bin_width=_bin_width_for_group(group_name, args))
        counts, _ = np.histogram(x, bins=edges)
        peak_idx = int(np.argmax(counts))
        rows.append(
            {
                "signal_col": col,
                "group": group_name,
                "split": split_label or "all",
                "n": int(x.size),
                "mean": float(np.mean(x)),
                "std": float(np.std(x)),
                "min": float(np.min(x)),
                "p05": float(q05),
                "median": float(q50),
                "p95": float(q95),
                "max": float(np.max(x)),
                "peak_bin_left": float(edges[peak_idx]),
                "peak_bin_right": float(edges[peak_idx + 1]),
                "peak_count": int(counts[peak_idx]),
            }
        )
    return pd.DataFrame(rows).sort_values(["group", "signal_col"]).reset_index(drop=True)


def _render_group_pages(
    df: pd.DataFrame,
    *,
    signal_cols: Sequence[str],
    out_dir: Path,
    prefix: str,
    group_name: str,
    bins: int,
    cols_per_page: int,
    fig_width: float,
    fig_row_height: float,
    density: bool,
    log_y: bool,
    args: argparse.Namespace,
    title_prefix: str,
) -> List[str]:
    if not signal_cols:
        return []

    written: List[str] = []
    per_page = max(1, int(cols_per_page))
    pages = math.ceil(len(signal_cols) / per_page)

    for page_idx in range(pages):
        chunk = list(signal_cols[page_idx * per_page : (page_idx + 1) * per_page])
        n = len(chunk)
        ncols = 2 if n > 1 else 1
        nrows = math.ceil(n / ncols)
        fig, axes = plt.subplots(
            nrows=nrows,
            ncols=ncols,
            figsize=(fig_width, fig_row_height * nrows),
            dpi=140,
        )
        axes_list = np.atleast_1d(axes).reshape(-1)
        for ax, col in zip(axes_list, chunk):
            x = pd.to_numeric(df[col], errors="coerce").dropna().to_numpy(dtype=float)
            if x.size == 0:
                ax.set_title(f"{label_with_unit(col)} (no data)")
                ax.axis("off")
                continue
            edges = _hist_edges(
                x,
                bins=max(2, int(bins)),
                bin_width=_bin_width_for_group(group_name, args),
            )
            ax.hist(
                x,
                bins=edges,
                color="#4c78a8",
                edgecolor="#ffffff",
                linewidth=0.6,
                density=bool(density),
            )
            ax.set_title(label_with_unit(col), fontsize=10, fontweight="600")
            ax.set_xlabel(label_with_unit(col), fontsize=9)
            ax.set_ylabel("Density" if density else "Count", fontsize=9)
            if log_y:
                ax.set_yscale("log")
            ax.grid(True, alpha=0.22)
        for ax in axes_list[len(chunk) :]:
            ax.axis("off")
        fig.suptitle(
            alias_site_names(f"{title_prefix} | {group_name.title()} Histograms | page {page_idx + 1}/{pages}"),
            fontsize=13,
            fontweight="600",
        )
        fig.tight_layout(rect=[0, 0, 1, 0.97])
        out_png = out_dir / f"{prefix}_{group_name}_hist_page_{page_idx + 1:02d}.png"
        fig.savefig(out_png, bbox_inches="tight")
        plt.close(fig)
        written.append(str(out_png))
    return written


def main() -> None:
    args = build_argparser().parse_args()
    if not args.timestamp_col:
        args.timestamp_col = _default_timestamp_col(str(args.dataset_kind))
    if str(args.split_state_col or "").strip() == "state":
        args.split_state_col = _default_split_state_col(str(args.dataset_kind))
    split_state_col = _normalize_optional_col(args.split_state_col)

    files = _discover_files(
        args.local_root,
        args.site,
        args.date_from,
        args.date_to,
        dataset_kind=str(args.dataset_kind),
        window_s=args.window_s,
        stride_s=args.stride_s,
    )
    if not files:
        raise SystemExit("No parquet files found for site/date range")

    schema_cols = list(pd.read_parquet(files[0], engine="pyarrow").columns)
    if args.timestamp_col not in schema_cols:
        raise SystemExit(f"Timestamp column not found in schema: {args.timestamp_col}")
    if split_state_col and split_state_col not in schema_cols:
        raise SystemExit(f"Split state column not found in schema: {split_state_col}")

    signal_cols = _select_signal_cols(
        schema_cols=schema_cols,
        explicit=args.signal_col,
        include_regex=args.include_regex,
        exclude_regex=args.exclude_regex,
        max_cols=int(args.max_cols),
        dataset_kind=str(args.dataset_kind),
    )
    if not signal_cols:
        raise SystemExit("No flow/pressure signal columns selected")

    if args.verbose:
        print(f"[INFO] files={len(files)} signals={len(signal_cols)} selected={signal_cols}")

    df = _load_data(
        files=files,
        timestamp_col=args.timestamp_col,
        signal_cols=signal_cols,
        split_state_col=split_state_col,
        start=args.start,
        end=args.end,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = _sanitize(args.out_prefix or f"{args.site}_{args.date_from}_to_{args.date_to}")
    summary_frames: List[pd.DataFrame] = []
    out_csv = out_dir / f"{prefix}_signal_hist_summary.csv"

    title_prefix = alias_site_names(f"{args.site} | {args.date_from} to {args.date_to}")
    artifacts: Dict[str, List[str] | str] = {
        "summary_csv": str(out_csv),
    }

    split_frames = [("all", df)]
    if split_state_col:
        split_frames = []
        raw_values = [v for v in df["__split_state"].dropna().unique().tolist()]
        raw_values = sorted(raw_values, key=lambda v: _split_value_label(v))
        for raw_value in raw_values:
            split_frames.append((_split_value_label(raw_value), df[df["__split_state"] == raw_value].copy()))

    for split_name, split_df in split_frames:
        if split_df.empty:
            continue
        summary_frames.append(
            _summary_rows(
                split_df,
                signal_cols=signal_cols,
                bins=int(args.bins),
                args=args,
                split_label=split_name,
            )
        )
        summary_frames[-1]["bin_width"] = summary_frames[-1]["group"].map(
            lambda g: _bin_width_for_group(str(g), args)
        )
        split_prefix = prefix if split_name == "all" else f"{prefix}_{split_name}"
        split_title_prefix = title_prefix
        if split_state_col:
            split_title_prefix = f"{title_prefix} | {split_state_col}={split_name}"
        for group_name in ("flow", "pressure", "water_quality", "other"):
            group_cols = [c for c in signal_cols if _group_for_column(c) == group_name]
            if not group_cols:
                continue
            written = _render_group_pages(
                split_df,
                signal_cols=group_cols,
                out_dir=out_dir,
                prefix=split_prefix,
                group_name=group_name,
                bins=int(args.bins),
                cols_per_page=int(args.cols_per_page),
                fig_width=float(args.fig_width),
                fig_row_height=float(args.fig_row_height),
                density=bool(args.density),
                log_y=bool(args.log_y),
                args=args,
                title_prefix=split_title_prefix,
            )
            split_key = _sanitize(split_name)
            artifact_key = f"{group_name}_pages" if split_name == "all" else f"{split_key}_{group_name}_pages"
            artifacts[artifact_key] = written

    if not summary_frames:
        raise SystemExit("No summary/stat rows produced after filtering")
    summary_df = pd.concat(summary_frames, axis=0, ignore_index=True)
    summary_df.to_csv(out_csv, index=False)

    out_meta = out_dir / f"{prefix}_signal_hist_meta.json"
    meta = {
        "site": args.site,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "start": args.start,
        "end": args.end,
        "local_root": args.local_root,
        "dataset_kind": str(args.dataset_kind),
        "window_s": int(args.window_s) if args.window_s is not None else None,
        "stride_s": int(args.stride_s) if args.stride_s is not None else None,
        "timestamp_col": args.timestamp_col,
        "bins": int(args.bins),
        "density": bool(args.density),
        "log_y": bool(args.log_y),
        "bin_widths": {
            "flow": args.bin_width_flow,
            "pressure": args.bin_width_pressure,
            "water_quality": args.bin_width_water_quality,
            "other": args.bin_width_other,
        },
        "split_state_col": split_state_col,
        "files": [str(p) for p in files],
        "rows_loaded": int(df.shape[0]),
        "signal_cols": signal_cols,
        "artifacts": artifacts,
    }
    out_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"[OK] wrote {out_csv}")
    print(f"[OK] wrote {out_meta}")
    for key, value in artifacts.items():
        if isinstance(value, list):
            print(f"[OK] wrote {len(value)} {key}")


if __name__ == "__main__":
    main()
