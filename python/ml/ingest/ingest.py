from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..utils.io import write_jsonl


@dataclass(frozen=True)
class IngestResult:
    manifest_path: Path
    count: int


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ingest_files(
    files: Iterable[Path],
    manifest_path: Path,
    dataset_name: str,
    dataset_version: str | None = None,
    extra_meta: dict | None = None,
) -> IngestResult:
    rows = []
    extra_meta = extra_meta or {}
    for p in files:
        rows.append(
            {
                "dataset": dataset_name,
                "version": dataset_version,
                "path": str(p),
                "sha256": _hash_file(p),
                "meta": extra_meta,
            }
        )
    write_jsonl(manifest_path, rows)
    return IngestResult(manifest_path=manifest_path, count=len(rows))
