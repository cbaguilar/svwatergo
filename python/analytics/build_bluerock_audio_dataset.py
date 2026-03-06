#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path


def main() -> None:
    # Backward-compatible shim; canonical entrypoint is build_audio_event_dataset.py.
    target = Path(__file__).with_name("build_audio_event_dataset.py")
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()

