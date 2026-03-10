from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .pipeline import (
    generate_window_features_for_day,
    generate_window_features_for_df,
    write_window_features_outputs,
)
from .specs import PIPELINES


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate fixed-window feature vectors from one day of S3 Parquet data."
    )
    p.add_argument("--site", required=True)
    p.add_argument("--day", required=True, help="YYYY-MM-DD (UTC)")
    p.add_argument("--timestamp-col", default=None)

    p.add_argument("--s3-bucket", required=False)
    p.add_argument("--s3-prefix", required=False)
    p.add_argument(
        "--local-root",
        default=None,
        help="Optional local raw root containing site=.../date=.../data.parquet. If set, local input is used instead of S3.",
    )

    p.add_argument("--out-dir", default="./derived")
    p.add_argument("--compression", default="snappy")
    p.add_argument("--max-gap-stale-s", type=float, default=300.0)

    p.add_argument("--window-seconds", type=int, default=60, help="Window length in seconds (default: 60)")
    p.add_argument(
        "--stride-seconds",
        type=int,
        default=None,
        help="Stride between windows in seconds (default: window length)",
    )

    return p


def main() -> None:
    args = build_argparser().parse_args()

    if args.site not in PIPELINES:
        raise SystemExit(f"Unknown site: {args.site} (known: {sorted(PIPELINES)})")

    if args.local_root:
        raw_path = Path(args.local_root) / f"site={args.site}" / f"date={args.day}" / "data.parquet"
        if not raw_path.exists():
            raise SystemExit(f"local raw parquet not found: {raw_path}")
        df = pd.read_parquet(raw_path, engine="pyarrow")
        feat, meta, report = generate_window_features_for_df(
            site=args.site,
            day=args.day,
            df=df,
            source=str(raw_path),
            timestamp_col=args.timestamp_col,
            window_seconds=args.window_seconds,
            stride_seconds=args.stride_seconds,
            max_gap_stale_s=args.max_gap_stale_s,
        )
    else:
        if not args.s3_bucket or not args.s3_prefix:
            raise SystemExit("Provide --local-root OR both --s3-bucket and --s3-prefix")
        feat, meta, report = generate_window_features_for_day(
            site=args.site,
            day=args.day,
            s3_bucket=args.s3_bucket,
            s3_prefix=args.s3_prefix,
            timestamp_col=args.timestamp_col,
            window_seconds=args.window_seconds,
            stride_seconds=args.stride_seconds,
            max_gap_stale_s=args.max_gap_stale_s,
        )

    print(f"Reading {meta['source']}")

    print(json.dumps(report, indent=2))

    out_parquet, _out_csv, out_meta = write_window_features_outputs(
        feat,
        meta,
        out_dir=Path(args.out_dir),
        window_seconds=args.window_seconds,
        stride_seconds=args.stride_seconds,
        site=args.site,
        day=args.day,
        compression=args.compression,
    )

    print(f"[OK] wrote {out_parquet}")
    print(f"[OK] wrote {out_meta}")


if __name__ == "__main__":
    main()
