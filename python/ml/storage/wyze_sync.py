from __future__ import annotations

import csv
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from .s3 import put_s3_bytes


DATE_RE = re.compile(r"date=(\d{4}-\d{2}-\d{2})")
CAM_RE = re.compile(r"camera=([^/]+)")


@dataclass(frozen=True)
class SyncItem:
    local_path: Path
    camera: str
    date_utc: str
    s3_key: str
    size_bytes: int


@dataclass(frozen=True)
class SyncResult:
    uploaded: int
    skipped: int
    bad: int
    manifest_path: Path


def infer_camera(path: Path) -> str:
    m = CAM_RE.search(str(path))
    if m:
        return m.group(1)
    return "unknown"


def infer_date(path: Path) -> str:
    m = DATE_RE.search(str(path))
    if m:
        return m.group(1)
    return "unknown"


def build_s3_key(prefix: str, camera: str, date_utc: str, filename: str) -> str:
    base = prefix.strip("/")
    return f"{base}/camera={camera}/date={date_utc}/{filename}"


def list_webm_files(root: Path) -> List[Path]:
    return sorted(root.rglob("*.webm"))


def ffprobe_ok(path: Path) -> bool:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,codec_type,duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise RuntimeError("ffprobe not found. Install ffmpeg to enable validation.")
    if res.returncode != 0:
        return False
    try:
        data = json.loads(res.stdout or "{}")
    except Exception:
        return False
    streams = data.get("streams") or []
    return any(s.get("codec_type") == "audio" for s in streams)


def build_sync_items(root: Path, prefix: str) -> List[SyncItem]:
    items: List[SyncItem] = []
    for p in list_webm_files(root):
        camera = infer_camera(p)
        date_utc = infer_date(p)
        key = build_s3_key(prefix, camera, date_utc, p.name)
        items.append(
            SyncItem(
                local_path=p,
                camera=camera,
                date_utc=date_utc,
                s3_key=key,
                size_bytes=p.stat().st_size,
            )
        )
    return items


def sync_wyze_dump(
    *,
    root: Path,
    bucket: str,
    prefix: str,
    out_manifest: Path,
    min_size_bytes: int = 1024,
    dry_run: bool = False,
) -> SyncResult:
    items = build_sync_items(root, prefix)
    out_manifest.parent.mkdir(parents=True, exist_ok=True)

    uploaded = skipped = bad = 0
    with out_manifest.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "local_path",
                "camera",
                "date_utc",
                "size_bytes",
                "s3_bucket",
                "s3_key",
                "status",
                "reason",
            ],
        )
        writer.writeheader()

        for item in items:
            if item.size_bytes < min_size_bytes:
                bad += 1
                writer.writerow(
                    {
                        "local_path": str(item.local_path),
                        "camera": item.camera,
                        "date_utc": item.date_utc,
                        "size_bytes": item.size_bytes,
                        "s3_bucket": bucket,
                        "s3_key": item.s3_key,
                        "status": "bad",
                        "reason": "too_small",
                    }
                )
                continue

            ok = ffprobe_ok(item.local_path)
            if not ok:
                bad += 1
                writer.writerow(
                    {
                        "local_path": str(item.local_path),
                        "camera": item.camera,
                        "date_utc": item.date_utc,
                        "size_bytes": item.size_bytes,
                        "s3_bucket": bucket,
                        "s3_key": item.s3_key,
                        "status": "bad",
                        "reason": "ffprobe_failed",
                    }
                )
                continue

            if dry_run:
                skipped += 1
                writer.writerow(
                    {
                        "local_path": str(item.local_path),
                        "camera": item.camera,
                        "date_utc": item.date_utc,
                        "size_bytes": item.size_bytes,
                        "s3_bucket": bucket,
                        "s3_key": item.s3_key,
                        "status": "dry_run",
                        "reason": "dry_run",
                    }
                )
                continue

            put_s3_bytes(bucket, item.s3_key, item.local_path.read_bytes(), "video/webm")
            uploaded += 1
            writer.writerow(
                {
                    "local_path": str(item.local_path),
                    "camera": item.camera,
                    "date_utc": item.date_utc,
                    "size_bytes": item.size_bytes,
                    "s3_bucket": bucket,
                    "s3_key": item.s3_key,
                    "status": "uploaded",
                    "reason": "ok",
                }
            )

    return SyncResult(uploaded=uploaded, skipped=skipped, bad=bad, manifest_path=out_manifest)
