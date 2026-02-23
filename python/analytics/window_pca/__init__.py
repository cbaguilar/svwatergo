from .cli import main
from .io import read_parquet_local, read_s3_parquet, write_s3_bytes, write_json_local
from .loader import load_many
from .model import (
    PCAModelBundle,
    fit_pca,
    transform_pca,
    print_pca_loadings,
    decode_alarmword_bits,
    alarmword_active_mask,
)
from .plotting import plot_pca_2d_live, plot_pca_3d
from .selection import (
    select_pca_columns,
    DEFAULT_CONTROL_REGEX,
    DEFAULT_INCLUDE_REGEX,
    DEFAULT_MONOTONIC_EXCLUDE_REGEX,
)

__all__ = [
    "main",
    "read_parquet_local",
    "read_s3_parquet",
    "write_s3_bytes",
    "write_json_local",
    "load_many",
    "PCAModelBundle",
    "fit_pca",
    "transform_pca",
    "print_pca_loadings",
    "decode_alarmword_bits",
    "alarmword_active_mask",
    "plot_pca_2d_live",
    "plot_pca_3d",
    "select_pca_columns",
    "DEFAULT_CONTROL_REGEX",
    "DEFAULT_INCLUDE_REGEX",
    "DEFAULT_MONOTONIC_EXCLUDE_REGEX",
]
