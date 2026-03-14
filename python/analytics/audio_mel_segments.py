#!/usr/bin/env python3
from __future__ import annotations

"""
Compatibility CLI wrapper.

Historically this script contained a separate mel-segment pipeline implementation.
To avoid behavior drift, it now delegates to python.ml.features.audio_mel.
"""

import sys
from pathlib import Path


def _import_impl():
    try:
        from python.ml.features.audio_mel import (  # type: ignore
            build_arg_parser,
            config_from_args,
            generate_mel_segments,
        )
        return build_arg_parser, config_from_args, generate_mel_segments
    except Exception:
        repo_root = Path(__file__).resolve().parents[2]
        repo_root_str = str(repo_root)
        if repo_root_str not in sys.path:
            sys.path.insert(0, repo_root_str)
        from python.ml.features.audio_mel import (  # type: ignore
            build_arg_parser,
            config_from_args,
            generate_mel_segments,
        )
        return build_arg_parser, config_from_args, generate_mel_segments


def main() -> None:
    build_arg_parser, config_from_args, generate_mel_segments = _import_impl()
    args = build_arg_parser().parse_args()
    cfg = config_from_args(args)
    generate_mel_segments(cfg)


if __name__ == "__main__":
    main()
