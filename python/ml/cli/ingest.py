from __future__ import annotations

import argparse
from pathlib import Path

from ..config import default_config
from ..ingest.ingest import ingest_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest files into a manifest")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--version", default=None)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()

    _ = default_config()
    files = [Path(p) for p in args.files]
    manifest_path = Path(args.manifest)
    res = ingest_files(files, manifest_path, dataset_name=args.dataset, dataset_version=args.version)
    print(f"Wrote {res.count} rows -> {res.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
