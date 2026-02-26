from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from ..train.audio_plc_dataset import AudioPLCSource, build_labeled_audio_plc_dataset


def _broadcast_or_validate(name: str, vals: List[str], n: int, default: str | None = None) -> List[str | None]:
    if not vals:
        return [default] * n
    if len(vals) == 1 and n > 1:
        return [vals[0]] * n
    if len(vals) != n:
        raise SystemExit(f"{name} count must be 1 or match --mel-manifest count ({n}), got {len(vals)}")
    return list(vals)


def main() -> int:
    p = argparse.ArgumentParser(description="Attach PLC ropumprun labels to mel segment manifest rows")
    p.add_argument("--mel-manifest", action="append", required=True, help="Mel manifest parquet/csv (repeat for multiple cameras)")
    p.add_argument("--plc-rows", action="append", required=True, help="Aligned PLC rows parquet/csv (repeat or provide one to broadcast)")
    p.add_argument("--camera", action="append", help="Camera name(s); defaults to manifest stem")
    p.add_argument("--site", action="append", help="Optional site(s) override")
    p.add_argument("--plc-col", default="ropumprun", help="PLC label column to derive states from")
    p.add_argument("--timestamp-col", default=None, help="PLC timestamp column (default auto-detect plc_ts/plctime)")
    p.add_argument("--out-parquet", required=True, help="Output labeled dataset parquet")
    p.add_argument("--out-meta", default=None, help="Optional metadata JSON path")
    args = p.parse_args()

    mel_paths = [Path(x) for x in args.mel_manifest]
    plc_paths = [Path(x) for x in args.plc_rows]
    n = len(mel_paths)

    cam_vals = _broadcast_or_validate("--camera", args.camera or [], n, default=None)
    site_vals = _broadcast_or_validate("--site", args.site or [], n, default=None)
    plc_vals = _broadcast_or_validate("--plc-rows", [str(p) for p in plc_paths], n)

    sources = []
    for i, mel_path in enumerate(mel_paths):
        camera = cam_vals[i] or mel_path.parent.name or mel_path.stem
        sources.append(
            AudioPLCSource(
                camera=str(camera),
                mel_manifest=mel_path,
                plc_rows=Path(str(plc_vals[i])),
                site=str(site_vals[i]) if site_vals[i] else None,
                plc_col=str(args.plc_col),
                timestamp_col=str(args.timestamp_col) if args.timestamp_col else None,
            )
        )

    out_parquet, out_meta = build_labeled_audio_plc_dataset(
        sources,
        Path(args.out_parquet),
        out_meta=Path(args.out_meta) if args.out_meta else None,
    )
    print(f"Labeled dataset -> {out_parquet}")
    print(f"Metadata       -> {out_meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
