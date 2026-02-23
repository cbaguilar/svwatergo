from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Union

import pandas as pd

try:
    import boto3  # type: ignore
except Exception:
    boto3 = None


def read_parquet_local(path: Union[str, Path]) -> pd.DataFrame:
    return pd.read_parquet(str(path), engine="pyarrow")


def s3_client():
    if boto3 is None:
        raise RuntimeError("boto3 not available. Install boto3 or use local files.")
    return boto3.client("s3")


def read_s3_parquet(bucket: str, key: str) -> pd.DataFrame:
    s3 = s3_client()
    obj = s3.get_object(Bucket=bucket, Key=key)
    data = obj["Body"].read()
    return pd.read_parquet(io.BytesIO(data), engine="pyarrow")


def write_s3_bytes(
    bucket: str,
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> None:
    s3 = s3_client()
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


def write_json_local(obj: dict, out_path: Union[str, Path]) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
