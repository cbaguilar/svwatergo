from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .io import read_parquet_local, read_s3_parquet


def parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def daterange_inclusive(d0: dt.date, d1: dt.date) -> List[dt.date]:
    if d1 < d0:
        raise ValueError("date-to must be >= date-from")
    n = (d1 - d0).days
    return [d0 + dt.timedelta(days=i) for i in range(n + 1)]


def load_many(
    *,
    input_file: Optional[str],
    input_list: Optional[str],
    local_root: Optional[str],
    s3_bucket: Optional[str],
    s3_prefix: Optional[str],
    site: Optional[str],
    day: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    window_s: Optional[int],
    stride_s: Optional[int],
    s3_key_template: Optional[str],
    verbose: bool = True,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    sources: List[str] = []

    if input_file:
        sources.append(input_file)

    if input_list:
        for ln in Path(input_list).read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            sources.append(ln)

    dates: List[str] = []
    if day:
        dates = [day]
    elif date_from and date_to:
        ds = daterange_inclusive(parse_date(date_from), parse_date(date_to))
        dates = [d.isoformat() for d in ds]

    if local_root and site and dates:
        root = Path(local_root)
        for d in dates:
            if window_s is not None:
                patterns: List[str] = []
                if stride_s is not None and int(stride_s) != int(window_s):
                    patterns.append(
                        f"**/window_s={int(window_s)}/stride_s={int(stride_s)}/site={site}/date={d}/window_features.parquet"
                    )
                else:
                    patterns.append(
                        f"**/window_s={int(window_s)}/site={site}/date={d}/window_features.parquet"
                    )
                for pat in patterns:
                    for p in sorted(root.glob(pat)):
                        sources.append(str(p))
            else:
                pat = f"**/site={site}/date={d}/window_features.parquet"
                for p in sorted(root.glob(pat)):
                    sources.append(str(p))

    if s3_bucket and s3_prefix and site and dates:
        base = s3_prefix.rstrip("/")
        if s3_key_template:
            for d in dates:
                key = s3_key_template.format(prefix=base, site=site, date=d, window_s=window_s, stride_s=stride_s)
                sources.append(f"s3://{s3_bucket}/{key}")
        else:
            if window_s is None:
                raise SystemExit(
                    "Using default S3 layout requires --window-s (or provide --s3-key-template)."
                )
            for d in dates:
                if stride_s is not None and int(stride_s) != int(window_s):
                    key = (
                        f"{base}/dataset=window_features"
                        f"/window_s={int(window_s)}"
                        f"/stride_s={int(stride_s)}"
                        f"/site={site}"
                        f"/date={d}"
                        f"/window_features.parquet"
                    )
                else:
                    key = (
                        f"{base}/dataset=window_features"
                        f"/window_s={int(window_s)}"
                        f"/site={site}"
                        f"/date={d}"
                        f"/window_features.parquet"
                    )
                sources.append(f"s3://{s3_bucket}/{key}")

    seen = set()
    uniq_sources: List[str] = []
    for s in sources:
        if s not in seen:
            seen.add(s)
            uniq_sources.append(s)

    if not uniq_sources:
        raise SystemExit(
            "No inputs found. Provide --input-file/--input-list or (local-root/s3 + site + date range)."
        )

    dfs: List[pd.DataFrame] = []
    loaded: List[str] = []
    failed: List[str] = []

    for src in uniq_sources:
        try:
            if src.startswith("s3://"):
                m = re.match(r"^s3://([^/]+)/(.+)$", src)
                if not m:
                    raise ValueError(f"Bad s3 URI: {src}")
                b = m.group(1)
                k = m.group(2)
                df = read_s3_parquet(b, k)
            else:
                df = read_parquet_local(src)
            dfs.append(df)
            loaded.append(src)
            if verbose:
                print(f"[load] {src} rows={len(df)} cols={len(df.columns)}")
        except Exception as e:
            failed.append(src)
            if verbose:
                print(f"[skip] {src} ({type(e).__name__}: {e})")

    if not dfs:
        raise SystemExit("All inputs failed to load.")

    out = pd.concat(dfs, ignore_index=True, sort=False)

    meta: Dict[str, object] = {
        "n_sources_total": len(uniq_sources),
        "n_sources_loaded": len(loaded),
        "n_sources_failed": len(failed),
        "sources_loaded": loaded[:200],
        "sources_failed": failed[:200],
        "n_rows": int(len(out)),
        "n_cols": int(len(out.columns)),
    }
    return out, meta
