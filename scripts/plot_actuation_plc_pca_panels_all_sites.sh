#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

SITE_LIST="${SITE_LIST:-bluerock,pryorfarm,santateresa}"
WINDOW_S="${WINDOW_S:-10}"
PROJECTION="${PROJECTION:-3d}"
COMBO_COL="${COMBO_COL:-actuation_bits}"
ACTUATORS="${ACTUATORS:-ropumprun,wellpumprun,feedpumprun,deliveryrun,flushrun}"
COMBO_TOP_K="${COMBO_TOP_K:-0}"
DROP_UNKNOWN="${DROP_UNKNOWN:-yes}"
QUANTILE_LIMITS="${QUANTILE_LIMITS:-1,99}"
POINT_SIZE="${POINT_SIZE:-10}"
ALPHA="${ALPHA:-0.6}"
X_COL="${X_COL:-plc_pca1}"
Y_COL="${Y_COL:-plc_pca2}"
Z_COL="${Z_COL:-plc_pca3}"

resolve_paths() {
  local site="$1"
  case "$site" in
    bluerock)
      INPUT_PARQUET="/mnt/d/datasets/svwatergo/derived/dataset=audio_actuation_dataset/site=bluerock/window_s=${WINDOW_S}/samples.parquet"
      OUT_DIR="/mnt/d/datasets/svwatergo/derived/plots/bluerock_actuation_plc_pca_panels"
      TITLE_PREFIX="Bluerock PLC PCA"
      ;;
    pryorfarm)
      INPUT_PARQUET="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm/dataset=audio_actuation_dataset/site=pryorfarm/window_s=${WINDOW_S}/samples.parquet"
      OUT_DIR="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm/plots/pryorfarm_actuation_plc_pca_panels"
      TITLE_PREFIX="Pryor Farm PLC PCA"
      ;;
    santateresa)
      INPUT_PARQUET="/mnt/d/datasets/svwatergo/derived_wyze_santateresa/dataset=audio_actuation_dataset/site=santateresa/window_s=${WINDOW_S}/samples.parquet"
      OUT_DIR="/mnt/d/datasets/svwatergo/derived_wyze_santateresa/plots/santateresa_actuation_plc_pca_panels"
      TITLE_PREFIX="Santa Teresa PLC PCA"
      ;;
    *)
      echo "unknown site: $site" >&2
      exit 2
      ;;
  esac
}

cd "$REPO"

IFS=',' read -r -a SITES <<< "$SITE_LIST"
for SITE in "${SITES[@]}"; do
  SITE="$(echo "$SITE" | xargs)"
  [[ -n "$SITE" ]] || continue
  resolve_paths "$SITE"
  echo "[RUN] plot PLC PCA panels site=$SITE"
  echo "      input=$INPUT_PARQUET"
  echo "      out_dir=$OUT_DIR"
  INPUT_PARQUET="$INPUT_PARQUET" \
  OUT_DIR="$OUT_DIR" \
  TITLE_PREFIX="$TITLE_PREFIX" \
  PROJECTION="$PROJECTION" \
  COMBO_COL="$COMBO_COL" \
  ACTUATORS="$ACTUATORS" \
  COMBO_TOP_K="$COMBO_TOP_K" \
  DROP_UNKNOWN="$DROP_UNKNOWN" \
  QUANTILE_LIMITS="$QUANTILE_LIMITS" \
  POINT_SIZE="$POINT_SIZE" \
  ALPHA="$ALPHA" \
  X_COL="$X_COL" \
  Y_COL="$Y_COL" \
  Z_COL="$Z_COL" \
  PYTHON="$PYTHON" \
  bash "$SCRIPT_DIR/plot_actuation_plc_pca_panels.sh"
done
