#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SITE="${SITE:-bluerock}"
LOCAL_ROOT="${LOCAL_ROOT:-/mnt/d/datasets/svwatergo/derived}"
RAW_ROOT="${RAW_ROOT:-/mnt/d/datasets/svwatergo/raw/plc}"
DATE_FROM="${DATE_FROM:-2025-12-01}"
DATE_TO="${DATE_TO:-2025-12-31}"
WINDOW_S="${WINDOW_S:-10}"
OUT_DIR="${OUT_DIR:-/mnt/d/datasets/svwatergo/derived/plots/summarystats}"
PCA_MEANS_ONLY="${PCA_MEANS_ONLY:-no}"
DERIVATIVES_WEIGHT="${DERIVATIVES_WEIGHT:-1.0}"

COLOR_GRID="${COLOR_GRID:-yes}"
WINDOW_HISTOGRAMS="${WINDOW_HISTOGRAMS:-yes}"
KMEANS="${KMEANS:-yes}"
KMEANS_K="${KMEANS_K:-8}"
HDBSCAN="${HDBSCAN:-no}"
GENERATE_MISSING_WINDOWS="${GENERATE_MISSING_WINDOWS:-no}"

export SITE
export LOCAL_ROOT
export RAW_ROOT
export DATE_FROM
export DATE_TO
export WINDOW_S
export OUT_DIR
export PCA_MEANS_ONLY
export DERIVATIVES_WEIGHT
export COLOR_GRID
export WINDOW_HISTOGRAMS
export KMEANS
export KMEANS_K
export HDBSCAN
export GENERATE_MISSING_WINDOWS

if [[ "$PCA_MEANS_ONLY" == "yes" ]]; then
  export PCA_INCLUDE_REGEX="__mean_tw$"
  export PCA_EXCLUDE_REGEX="__duty$,__mode_tw$,__transitions$,^state_unknown$,^residualtank(level|depth)__"
fi

exec bash "$SCRIPT_DIR/pca_bluerock_noninteractive_open3d.sh"
