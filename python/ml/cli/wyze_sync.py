from __future__ import annotations

import argparse
from pathlib import Path

from ..storage.wyze_sync import sync_wyze_dump


def main() -> int:
    p = argparse.ArgumentParser(description="Validate and sync Wyze webm dumps to S3")
    p.add_argument("--root", required=True, help="Local wyze_dump root")
    p.add_argument("--bucket", required=True, help="S3 bucket")
    p.add_argument("--prefix", required=True, help="S3 prefix (e.g. wyze_dump)")
    p.add_argument("--manifest", required=True, help="Output manifest CSV path")
    p.add_argument("--min-size-bytes", type=int, default=1024)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    res = sync_wyze_dump(
        root=Path(args.root),
        bucket=args.bucket,
        prefix=args.prefix,
        out_manifest=Path(args.manifest),
        min_size_bytes=int(args.min_size_bytes),
        dry_run=bool(args.dry_run),
    )

    print(
        f"uploaded={res.uploaded} skipped={res.skipped} bad={res.bad} manifest={res.manifest_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
