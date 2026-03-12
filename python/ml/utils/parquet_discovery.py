from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import List, Optional


def _parse_date(text: str) -> date:
    s = str(text).strip()
    if not s:
        raise ValueError("Date is empty")
    return date.fromisoformat(s)


def _extract_partition_date(path: Path) -> Optional[date]:
    # Expected partition folder format: .../date=YYYY-MM-DD/filename.parquet
    parent = path.parent.name
    if not parent.startswith("date="):
        return None
    raw = parent.split("=", 1)[1].strip()
    try:
        return date.fromisoformat(raw)
    except Exception:
        return None


def discover_date_partitioned_parquets(
    dataset_root: Path,
    *,
    filename: str = "data.parquet",
    date_from: str = "",
    date_to: str = "",
) -> List[Path]:
    root = Path(dataset_root)
    if not root.exists():
        raise FileNotFoundError(f"dataset_root not found: {root}")

    d0 = _parse_date(date_from) if str(date_from).strip() else None
    d1 = _parse_date(date_to) if str(date_to).strip() else None
    if d0 and d1 and d0 > d1:
        raise ValueError(f"date_from ({d0.isoformat()}) cannot be after date_to ({d1.isoformat()})")

    paths = sorted(root.glob(f"date=*/{filename}"))
    out: List[Path] = []
    for p in paths:
        d = _extract_partition_date(p)
        if d is None:
            continue
        if d0 and d < d0:
            continue
        if d1 and d > d1:
            continue
        out.append(p)
    return out
