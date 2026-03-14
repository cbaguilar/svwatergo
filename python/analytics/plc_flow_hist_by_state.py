#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

DEFAULT_STATE_COLS = [
    "wellpumprun",
    "feedpumprun",
    "ropumprun",
    "deliveryrun",
    "inletrun",
    "flushrun",
]


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Compute flow histograms and per-state summary stats from PLC parquet data. "
            "Useful for estimating mean flow rate by pump/state signals."
        )
    )
    p.add_argument(
        "--input-glob",
        action="append",
        default=None,
        help="Input parquet glob(s). Repeatable. Default: data/raw/plc/*/date=*/data.parquet",
    )
    p.add_argument("--site", default=None, help="Optional site filter (e.g. bluerock/pryorfarm/santateresa)")
    p.add_argument("--start", default=None, help="UTC start time (ISO-8601 inclusive)")
    p.add_argument("--end", default=None, help="UTC end time (ISO-8601 exclusive)")
    p.add_argument("--timestamp-col", default="plctime", help="Timestamp column")
    p.add_argument(
        "--state-col",
        action="append",
        default=None,
        help="State column(s) to use. Repeatable. Default picks common pump run columns.",
    )
    p.add_argument(
        "--flow-col",
        action="append",
        default=None,
        help="Flow column(s) to use. Repeatable. Default auto-detects non-total/non-daily *flow columns.",
    )
    p.add_argument("--bins", type=int, default=60, help="Histogram bins per flow/state, default: 60")
    p.add_argument("--include-total-flows", action="store_true", help="Include cumulative total*flow columns")
    p.add_argument("--include-daily-flows", action="store_true", help="Include cumulative daily*flow columns")
    p.add_argument("--out-dir", default="data/derived/plc_flow_hist_by_state", help="Output directory")
    p.add_argument("--prefix", default=None, help="Output file prefix")
    p.add_argument("--no-plot", action="store_true", help="Skip PNG histogram plots")
    return p


def _default_globs(input_globs: Optional[Sequence[str]]) -> List[str]:
    if input_globs:
        return list(input_globs)
    return ["data/raw/plc/*/date=*/data.parquet"]


def _expand_glob_pattern(pattern: str) -> List[Path]:
    return [Path(x) for x in sorted(glob.glob(pattern, recursive=True))]


def _site_from_path(path: Path) -> str:
    # Supports both:
    # .../plc/bluerock/date=YYYY-MM-DD/data.parquet
    # .../plc/site=bluerock/date=YYYY-MM-DD/data.parquet
    parts = path.parts
    if "plc" not in parts:
        return ""
    i = parts.index("plc")
    if i + 1 >= len(parts):
        return ""
    raw = parts[i + 1].strip().lower()
    if raw.startswith("site="):
        return raw.split("=", 1)[1]
    return raw


def _first_existing(cols: Sequence[str], name: str) -> Optional[str]:
    n = name.strip().lower()
    for c in cols:
        if c.strip().lower() == n:
            return c
    return None


def _detect_flow_cols(
    schema_cols: Sequence[str],
    explicit: Optional[Sequence[str]],
    include_total: bool,
    include_daily: bool,
) -> List[str]:
    if explicit:
        out: List[str] = []
        for c in explicit:
            found = _first_existing(schema_cols, c)
            if found:
                out.append(found)
        return sorted(set(out))

    out = []
    for c in schema_cols:
        cl = c.lower()
        if "flow" not in cl:
            continue
        if (not include_total) and cl.startswith("total"):
            continue
        if (not include_daily) and cl.startswith("daily"):
            continue
        out.append(c)
    return sorted(set(out))


def _detect_state_cols(schema_cols: Sequence[str], explicit: Optional[Sequence[str]]) -> List[str]:
    if explicit:
        out: List[str] = []
        for c in explicit:
            found = _first_existing(schema_cols, c)
            if found:
                out.append(found)
        return sorted(set(out))

    out = []
    for c in DEFAULT_STATE_COLS:
        found = _first_existing(schema_cols, c)
        if found:
            out.append(found)
    return sorted(set(out))


def _coerce_state_values(s: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(s):
        return s.astype(int)

    if pd.api.types.is_numeric_dtype(s):
        x = pd.to_numeric(s, errors="coerce")
        uniq = sorted(set(float(v) for v in x.dropna().unique()))
        if len(uniq) <= 2 and set(uniq).issubset({0.0, 1.0}):
            return x.astype("Int64")
        return x

    txt = s.astype(str).str.strip().str.lower()
    mapping = {
        "true": 1,
        "false": 0,
        "on": 1,
        "off": 0,
        "1": 1,
        "0": 0,
        "yes": 1,
        "no": 0,
    }
    return txt.map(mapping).astype("Int64")


def _sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")


def _load_data(
    files: Sequence[Path],
    timestamp_col: str,
    flow_cols: Sequence[str],
    state_cols: Sequence[str],
    site: Optional[str],
    start: Optional[str],
    end: Optional[str],
) -> pd.DataFrame:
    start_ts = pd.Timestamp(start, tz="UTC") if start else None
    end_ts = pd.Timestamp(end, tz="UTC") if end else None
    site_norm = site.strip().lower() if site else None

    keep_cols = [timestamp_col] + list(flow_cols) + list(state_cols)
    keep_cols = sorted(set(keep_cols))

    rows: List[pd.DataFrame] = []
    for fp in files:
        path_site = _site_from_path(fp)
        if site_norm and path_site and path_site != site_norm:
            continue

        try:
            df = pd.read_parquet(fp, columns=keep_cols)
        except Exception:
            df = pd.read_parquet(fp)
            missing = [c for c in keep_cols if c not in df.columns]
            if missing:
                continue
            df = df[keep_cols]

        if df.empty:
            continue

        out = pd.DataFrame()
        out["__ts"] = pd.to_datetime(df[timestamp_col], utc=True, errors="coerce")
        out["__site_path"] = path_site
        for c in flow_cols:
            out[c] = pd.to_numeric(df[c], errors="coerce")
        for c in state_cols:
            out[c] = _coerce_state_values(df[c])

        if start_ts is not None:
            out = out[out["__ts"] >= start_ts]
        if end_ts is not None:
            out = out[out["__ts"] < end_ts]

        out = out[out["__ts"].notna()]
        if not out.empty:
            rows.append(out)

    if not rows:
        raise SystemExit("No rows found after filtering")

    df_all = pd.concat(rows, axis=0, ignore_index=True)
    df_all = df_all.sort_values("__ts", kind="mergesort").reset_index(drop=True)
    return df_all


def _compute_hist_and_summary(
    df: pd.DataFrame,
    flow_cols: Sequence[str],
    state_cols: Sequence[str],
    bins: int,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    hist_rows: List[Dict[str, float | int | str]] = []
    sum_rows: List[Dict[str, float | int | str]] = []

    for flow in flow_cols:
        for state_col in state_cols:
            d = df[[flow, state_col]].copy()
            d = d[d[flow].notna() & d[state_col].notna()]
            if d.empty:
                continue

            # Use one shared binning per (flow,state_col) so ON/OFF compare directly.
            x_all = d[flow].to_numpy(dtype=float)
            x_min = float(np.nanmin(x_all))
            x_max = float(np.nanmax(x_all))
            if not np.isfinite(x_min) or not np.isfinite(x_max):
                continue
            if x_max <= x_min:
                x_max = x_min + 1e-9
            edges = np.linspace(x_min, x_max, max(2, int(bins) + 1))

            for state_value in sorted(d[state_col].dropna().unique()):
                x = d.loc[d[state_col] == state_value, flow].to_numpy(dtype=float)
                if x.size == 0:
                    continue
                counts, _ = np.histogram(x, bins=edges)
                density, _ = np.histogram(x, bins=edges, density=True)

                for i in range(len(counts)):
                    hist_rows.append(
                        {
                            "flow_col": flow,
                            "state_col": state_col,
                            "state_value": int(state_value) if float(state_value).is_integer() else float(state_value),
                            "bin_left": float(edges[i]),
                            "bin_right": float(edges[i + 1]),
                            "count": int(counts[i]),
                            "density": float(density[i]) if np.isfinite(density[i]) else 0.0,
                        }
                    )

                q05, q50, q95 = np.quantile(x, [0.05, 0.5, 0.95])
                sum_rows.append(
                    {
                        "flow_col": flow,
                        "state_col": state_col,
                        "state_value": int(state_value) if float(state_value).is_integer() else float(state_value),
                        "n": int(x.size),
                        "mean": float(np.mean(x)),
                        "std": float(np.std(x)),
                        "min": float(np.min(x)),
                        "p05": float(q05),
                        "median": float(q50),
                        "p95": float(q95),
                        "max": float(np.max(x)),
                    }
                )

    hist_df = pd.DataFrame(hist_rows)
    sum_df = pd.DataFrame(sum_rows)
    return hist_df, sum_df


def _save_plots(hist_df: pd.DataFrame, out_dir: Path, prefix: str) -> int:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:
        return 0

    n_written = 0
    keys = hist_df[["flow_col", "state_col"]].drop_duplicates()
    for _, row in keys.iterrows():
        flow_col = str(row["flow_col"])
        state_col = str(row["state_col"])
        d = hist_df[(hist_df["flow_col"] == flow_col) & (hist_df["state_col"] == state_col)].copy()
        if d.empty:
            continue
        fig, ax = plt.subplots(figsize=(9, 4.5), dpi=130)
        for sv in sorted(d["state_value"].unique()):
            s = d[d["state_value"] == sv].copy()
            centers = 0.5 * (s["bin_left"].to_numpy() + s["bin_right"].to_numpy())
            ax.plot(centers, s["density"].to_numpy(), label=f"{state_col}={sv}", lw=1.6)
        ax.set_title(f"{flow_col} by {state_col}")
        ax.set_xlabel(flow_col)
        ax.set_ylabel("Density")
        ax.grid(True, alpha=0.25)
        ax.legend()
        fig.tight_layout()
        out_png = out_dir / f"{prefix}_{_sanitize(flow_col)}_by_{_sanitize(state_col)}.png"
        fig.savefig(out_png)
        plt.close(fig)
        n_written += 1
    return n_written


def main() -> None:
    args = build_argparser().parse_args()
    globs = _default_globs(args.input_glob)

    files: List[Path] = []
    for g in globs:
        files.extend(_expand_glob_pattern(g))
    files = sorted(set(files))
    if not files:
        raise SystemExit("No parquet files matched --input-glob")

    schema_cols = list(pq.read_schema(files[0]).names)
    if args.timestamp_col not in schema_cols:
        raise SystemExit(f"Timestamp column not found in schema: {args.timestamp_col}")

    flow_cols = _detect_flow_cols(
        schema_cols=schema_cols,
        explicit=args.flow_col,
        include_total=bool(args.include_total_flows),
        include_daily=bool(args.include_daily_flows),
    )
    if not flow_cols:
        raise SystemExit("No flow columns selected")

    state_cols = _detect_state_cols(schema_cols=schema_cols, explicit=args.state_col)
    if not state_cols:
        raise SystemExit("No state columns selected")

    df = _load_data(
        files=files,
        timestamp_col=args.timestamp_col,
        flow_cols=flow_cols,
        state_cols=state_cols,
        site=args.site,
        start=args.start,
        end=args.end,
    )

    hist_df, sum_df = _compute_hist_and_summary(
        df=df,
        flow_cols=flow_cols,
        state_cols=state_cols,
        bins=int(args.bins),
    )
    if hist_df.empty or sum_df.empty:
        raise SystemExit("No histogram/stat rows produced (check flow/state columns and filters)")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = str(args.prefix or args.site or "all_sites")
    prefix = _sanitize(prefix)

    out_hist = out_dir / f"{prefix}_flow_hist_by_state.csv"
    out_sum = out_dir / f"{prefix}_flow_summary_by_state.csv"
    out_meta = out_dir / f"{prefix}_flow_hist_by_state_meta.json"
    hist_df.to_csv(out_hist, index=False)
    sum_df.to_csv(out_sum, index=False)

    plots_written = 0
    if not args.no_plot:
        plots_written = _save_plots(hist_df, out_dir=out_dir, prefix=prefix)

    meta = {
        "input_globs": globs,
        "site": args.site,
        "start": args.start,
        "end": args.end,
        "timestamp_col": args.timestamp_col,
        "state_cols": state_cols,
        "flow_cols": flow_cols,
        "files_matched": len(files),
        "rows_loaded": int(df.shape[0]),
        "hist_rows": int(hist_df.shape[0]),
        "summary_rows": int(sum_df.shape[0]),
        "plots_written": int(plots_written),
        "artifacts": {
            "hist_csv": str(out_hist),
            "summary_csv": str(out_sum),
        },
    }
    out_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"[OK] wrote {out_hist}")
    print(f"[OK] wrote {out_sum}")
    if not args.no_plot:
        print(f"[OK] wrote {plots_written} plot(s) in {out_dir}")
    print(f"[OK] wrote {out_meta}")


if __name__ == "__main__":
    main()
