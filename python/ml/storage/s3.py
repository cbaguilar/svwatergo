from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import pandas as pd

try:
    import boto3  # type: ignore
except Exception:
    boto3 = None


S3_URI_RE = re.compile(r"^s3://([^/]+)/(.+)$")


@dataclass(frozen=True)
class S3Object:
    bucket: str
    key: str
    size_bytes: int | None = None
    etag: str | None = None

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


def require_boto3() -> None:
    if boto3 is None:
        raise RuntimeError("boto3 not available. Install boto3 to use S3")


def s3_client():
    require_boto3()
    return boto3.client("s3")


def split_s3_uri(uri: str) -> Tuple[str, str]:
    m = S3_URI_RE.match(uri)
    if not m:
        raise ValueError(f"bad s3 uri: {uri}")
    return m.group(1), m.group(2)


def is_s3_uri(path: str) -> bool:
    return path.startswith("s3://")


def list_s3_objects(bucket: str, prefix: str) -> List[S3Object]:
    s3 = s3_client()
    out: List[S3Object] = []
    token: Optional[str] = None
    while True:
        kw = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        for obj in resp.get("Contents", []):
            out.append(
                S3Object(
                    bucket=bucket,
                    key=obj.get("Key"),
                    size_bytes=int(obj.get("Size") or 0),
                    etag=str(obj.get("ETag") or "").strip('"'),
                )
            )
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return out


def get_s3_bytes(bucket: str, key: str) -> bytes:
    s3 = s3_client()
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def put_s3_bytes(
    bucket: str,
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> None:
    s3 = s3_client()
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


def read_parquet_s3(bucket: str, key: str) -> pd.DataFrame:
    data = get_s3_bytes(bucket, key)
    return pd.read_parquet(io.BytesIO(data), engine="pyarrow")


def read_parquet_uri(uri: str) -> pd.DataFrame:
    if is_s3_uri(uri):
        b, k = split_s3_uri(uri)
        return read_parquet_s3(b, k)
    return pd.read_parquet(uri, engine="pyarrow")


def read_bytes_uri(uri: str) -> bytes:
    if is_s3_uri(uri):
        b, k = split_s3_uri(uri)
        return get_s3_bytes(b, k)
    return Path(uri).read_bytes()


def list_parquet_sources(
    *,
    sources: Iterable[str] | None = None,
    s3_bucket: str | None = None,
    s3_prefix: str | None = None,
    site: str | None = None,
    dates: Iterable[str] | None = None,
    window_s: int | None = None,
    stride_s: int | None = None,
    s3_key_template: str | None = None,
) -> List[str]:
    if sources:
        return list(sources)
    if not (s3_bucket and s3_prefix and site and dates):
        raise ValueError("Provide sources or (s3_bucket, s3_prefix, site, dates)")
    base = s3_prefix.rstrip("/")
    out = []
    for d in dates:
        if s3_key_template:
            key = s3_key_template.format(
                prefix=base, site=site, date=d, window_s=window_s, stride_s=stride_s
            )
        else:
            if not window_s:
                raise ValueError("window_s required for default layout")
            key = f"{base}/dataset=window_features/window_s={int(window_s)}/site={site}/date={d}/window_features.parquet"
            if stride_s:
                key = f"{base}/dataset=window_features/window_s={int(window_s)}/stride_s={int(stride_s)}/site={site}/date={d}/window_features.parquet"
        out.append(f"s3://{s3_bucket}/{key}")
    return out
