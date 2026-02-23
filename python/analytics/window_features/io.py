from __future__ import annotations

import datetime as dt
import io
import json
from pathlib import Path
from typing import Tuple

import pandas as pd

try:
    import boto3  # type: ignore
except Exception:
    boto3 = None


def day_to_range_utc(day_str: str) -> Tuple[pd.Timestamp, pd.Timestamp]:
    d = dt.date.fromisoformat(day_str)
    start = pd.Timestamp(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc))
    return start, start + pd.Timedelta(days=1)


def default_s3_data_key(prefix: str, site: str, day: str, parquet_filename: str = "data.parquet") -> str:
    base = f"{prefix.rstrip('/')}/site={site}/date={day}"
    return f"{base}/{parquet_filename}"


def s3_get_bytes(bucket: str, key: str) -> bytes:
    if boto3 is None:
        raise RuntimeError("boto3 not available")
    s3 = boto3.client("s3")
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def read_parquet_bytes_to_df(parquet_bytes: bytes) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(parquet_bytes), engine="pyarrow")


def ensure_parent_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def write_parquet_local(df: pd.DataFrame, out_path: Path, compression: str = "snappy") -> None:
    ensure_parent_dir(out_path)
    df.to_parquet(out_path, engine="pyarrow", compression=compression, index=False)


def write_json_local(obj: dict, out_path: Path) -> None:
    ensure_parent_dir(out_path)
    out_path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
