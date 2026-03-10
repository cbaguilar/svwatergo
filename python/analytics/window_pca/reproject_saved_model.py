#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .model import apply_controls_weight, extract_matrix

try:
    import joblib  # type: ignore
except Exception as e:
    raise SystemExit("Missing joblib. Install with: pip install joblib") from e


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Reproject data with a saved PCA model bundle (no PCA refit). "
            "Supports row filtering, PCA bounds clipping, and color column passthrough."
        )
    )
    p.add_argument("--model-joblib", required=True, help="Saved PCA model bundle from scalable_cli")

    p.add_argument("--input-parquet", action="append", default=[], help="Input parquet path (repeatable)")
    p.add_argument("--input-list", default=None, help="Text file with parquet paths (one per line)")
    p.add_argument("--input-glob", action="append", default=[], help="Glob pattern for parquet paths (repeatable)")

    p.add_argument("--where", default="", help="Optional pandas query string (applied before projection)")
    p.add_argument("--time-col", default="", help="Optional time column for range filtering")
    p.add_argument("--time-start", default="", help="Inclusive start timestamp")
    p.add_argument("--time-end", default="", help="Inclusive end timestamp")

    p.add_argument("--x-min", type=float, default=None)
    p.add_argument("--x-max", type=float, default=None)
    p.add_argument("--y-min", type=float, default=None)
    p.add_argument("--y-max", type=float, default=None)
    p.add_argument("--z-min", type=float, default=None)
    p.add_argument("--z-max", type=float, default=None)

    p.add_argument("--color-col", default="", help="Optional column to carry through for downstream color-by")
    p.add_argument(
        "--preserve-cols",
        default="window_start_ts,state__last,alarm__last,alarm__duty,deliveryrun__duty,ropumprun__duty,feedpumprun__duty,wellpumprun__duty",
        help="Comma-separated columns to preserve in output",
    )
    p.add_argument("--fill-value", type=float, default=0.0)
    p.add_argument("--clip-abs", type=float, default=None)
    p.add_argument("--max-points", type=int, default=0, help="Optional random cap after all filters")
    p.add_argument("--seed", type=int, default=0)

    p.add_argument("--out-parquet", required=True)
    p.add_argument("--out-meta", default="")
    p.add_argument("--verbose", action="store_true")
    return p


def _parse_csv_cols(s: str) -> List[str]:
    return [x.strip() for x in str(s).split(",") if x.strip()]


def _collect_inputs(args) -> List[str]:
    files: List[str] = []
    files.extend([str(x) for x in (args.input_parquet or []) if str(x).strip()])
    if args.input_list:
        for ln in Path(args.input_list).read_text(encoding="utf-8").splitlines():
            x = ln.strip()
            if x and not x.startswith("#"):
                files.append(x)
    for pat in (args.input_glob or []):
        for p in sorted(glob.glob(str(pat), recursive=True)):
            files.append(str(p))
    seen = set()
    out: List[str] = []
    for f in files:
        if f in seen:
            continue
        seen.add(f)
        out.append(f)
    return out


def _ensure_cols(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    miss = [c for c in cols if c not in df.columns]
    if not miss:
        return df
    out = df.copy()
    for c in miss:
        out[c] = np.nan
    return out


def _apply_filters(df: pd.DataFrame, args) -> pd.DataFrame:
    out = df
    if str(args.where).strip():
        out = out.query(str(args.where), engine="python")

    tc = str(args.time_col).strip()
    if tc and tc in out.columns and (str(args.time_start).strip() or str(args.time_end).strip()):
        ts = pd.to_datetime(out[tc], errors="coerce", utc=True)
        mask = pd.Series(np.ones(len(out), dtype=bool), index=out.index)
        if str(args.time_start).strip():
            t0 = pd.to_datetime(str(args.time_start), utc=True, errors="coerce")
            if pd.notna(t0):
                mask &= ts >= t0
        if str(args.time_end).strip():
            t1 = pd.to_datetime(str(args.time_end), utc=True, errors="coerce")
            if pd.notna(t1):
                mask &= ts <= t1
        out = out.loc[mask]
    return out


def _apply_pca_bounds(df: pd.DataFrame, args) -> pd.DataFrame:
    out = df
    if args.x_min is not None:
        out = out[out["pca1"] >= float(args.x_min)]
    if args.x_max is not None:
        out = out[out["pca1"] <= float(args.x_max)]
    if args.y_min is not None:
        out = out[out["pca2"] >= float(args.y_min)]
    if args.y_max is not None:
        out = out[out["pca2"] <= float(args.y_max)]
    if args.z_min is not None:
        out = out[out["pca3"] >= float(args.z_min)]
    if args.z_max is not None:
        out = out[out["pca3"] <= float(args.z_max)]
    return out


def main() -> None:
    args = _build_argparser().parse_args()
    t0 = dt.datetime.utcnow()
    model_path = Path(args.model_joblib)
    if not model_path.exists():
        raise SystemExit(f"model not found: {model_path}")

    m = joblib.load(model_path)
    req = ["cols", "scaler", "pca", "control_mask", "controls_weight"]
    miss = [k for k in req if k not in m]
    if miss:
        raise SystemExit(f"model bundle missing keys: {miss}")

    cols = list(m["cols"])
    scaler = m["scaler"]
    pca = m["pca"]
    control_mask = np.asarray(m["control_mask"], dtype=bool)
    controls_weight = float(m["controls_weight"])

    in_files = _collect_inputs(args)
    if not in_files:
        raise SystemExit("No input files. Provide --input-parquet, --input-list, or --input-glob.")

    preserve_cols = _parse_csv_cols(args.preserve_cols)
    color_col = str(args.color_col).strip()
    if color_col:
        preserve_cols = list(dict.fromkeys(preserve_cols + [color_col]))

    rng = np.random.default_rng(int(args.seed))
    out_parts: List[pd.DataFrame] = []
    rows_in = 0
    rows_after_select = 0
    rows_out = 0

    for i, fp in enumerate(in_files):
        p = Path(fp)
        if not p.exists():
            if args.verbose:
                print(f"[skip] missing file: {fp}")
            continue
        df = pd.read_parquet(p, engine="pyarrow")
        rows_in += int(len(df))
        if len(df) == 0:
            continue

        df = _apply_filters(df, args)
        rows_after_select += int(len(df))
        if len(df) == 0:
            continue

        df = _ensure_cols(df, cols)
        X = extract_matrix(df, cols, fill_value=float(args.fill_value), clip_abs=args.clip_abs)
        Xs = scaler.transform(X)
        Xw = apply_controls_weight(Xs, control_mask, controls_weight)
        Z = pca.transform(Xw)

        out_df = pd.DataFrame(
            {
                "pca1": Z[:, 0].astype("float64"),
                "pca2": Z[:, 1].astype("float64"),
                "pca3": Z[:, 2].astype("float64"),
            }
        )
        keep = [c for c in preserve_cols if c in df.columns]
        if keep:
            out_df = pd.concat([df[keep].reset_index(drop=True), out_df], axis=1)
        out_df = _apply_pca_bounds(out_df, args)
        if len(out_df) == 0:
            continue
        out_parts.append(out_df)
        rows_out += int(len(out_df))
        if args.verbose:
            print(f"[project] {i+1}/{len(in_files)} file={fp} rows_out={len(out_df)}")

    if not out_parts:
        raise SystemExit("No output rows after selection/projection/bounds.")

    out = pd.concat(out_parts, ignore_index=True, sort=False)
    if int(args.max_points) > 0 and len(out) > int(args.max_points):
        out = out.sample(n=int(args.max_points), random_state=int(args.seed)).reset_index(drop=True)

    out_path = Path(args.out_parquet)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)

    meta = {
        "created_utc": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
        "model_joblib": str(model_path),
        "n_input_files": len(in_files),
        "rows_input_total": int(rows_in),
        "rows_after_row_selection": int(rows_after_select),
        "rows_output_before_sample": int(rows_out),
        "rows_output_final": int(len(out)),
        "cols_model": cols,
        "controls_weight": controls_weight,
        "filters": {
            "where": str(args.where),
            "time_col": str(args.time_col),
            "time_start": str(args.time_start),
            "time_end": str(args.time_end),
            "bounds": {
                "x_min": args.x_min,
                "x_max": args.x_max,
                "y_min": args.y_min,
                "y_max": args.y_max,
                "z_min": args.z_min,
                "z_max": args.z_max,
            },
            "fill_value": float(args.fill_value),
            "clip_abs": args.clip_abs,
            "max_points": int(args.max_points),
            "seed": int(args.seed),
        },
        "preserve_cols": preserve_cols,
        "color_col": color_col,
        "out_parquet": str(out_path),
    }

    out_meta = Path(args.out_meta) if str(args.out_meta).strip() else out_path.with_suffix(".metadata.json")
    out_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"[OK] wrote {out_path}")
    print(f"[OK] wrote {out_meta}")


if __name__ == "__main__":
    main()
