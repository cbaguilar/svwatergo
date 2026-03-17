#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="${REPO:-$REPO_DEFAULT}"

SITE_LIST="${SITE_LIST:-bluerock,pryorfarm,santateresa}"
WINDOW_S="${WINDOW_S:-10}"
PROJECTION="${PROJECTION:-3d}"
QUANTILE_LIMITS="${QUANTILE_LIMITS:-1,99}"
POINT_SIZE="${POINT_SIZE:-8}"
ALPHA="${ALPHA:-0.45}"
COLOR_COLS="${COLOR_COLS:-ml__true_label,ml__pred_label,ml__pred_confidence_mean,ml__pred_confidence_combo,ml__exact_match,ml__hamming_error,ml__bce_loss,audio_source}"

resolve_site_paths() {
  local site="$1"
  case "$site" in
    bluerock)
      INPUT_PARQUET="/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_${WINDOW_S}s_panns_actuation_5bool_multilabel/pann_pca_true_vs_pred.parquet"
      OUT_PNG="/mnt/d/datasets/svwatergo/derived/plots/bluerock_${WINDOW_S}s_panns_actuation_5bool_multilabel_true_pred_panels.png"
      TITLE_PREFIX="Bluerock 5-Actuation Multilabel PCA"
      ;;
    pryorfarm)
      INPUT_PARQUET="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm/checkpoints/pryorfarm_${WINDOW_S}s_panns_actuation_5bool_multilabel/pann_pca_true_vs_pred.parquet"
      OUT_PNG="/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm/plots/pryorfarm_${WINDOW_S}s_panns_actuation_5bool_multilabel_true_pred_panels.png"
      TITLE_PREFIX="Pryor Farm 5-Actuation Multilabel PCA"
      ;;
    santateresa)
      INPUT_PARQUET="/mnt/d/datasets/svwatergo/derived_wyze_santateresa/checkpoints/santateresa_${WINDOW_S}s_panns_actuation_5bool_multilabel/pann_pca_true_vs_pred.parquet"
      OUT_PNG="/mnt/d/datasets/svwatergo/derived_wyze_santateresa/plots/santateresa_${WINDOW_S}s_panns_actuation_5bool_multilabel_true_pred_panels.png"
      TITLE_PREFIX="Santa Teresa 5-Actuation Multilabel PCA"
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
  resolve_site_paths "$SITE"
  echo "[RUN] site=$SITE"
  echo "      input=$INPUT_PARQUET"
  echo "      out=$OUT_PNG"
  "$PYTHON" python/analytics/plot_multilabel_pca_true_pred_panels.py \
    --input-parquet "$INPUT_PARQUET" \
    --out-png "$OUT_PNG" \
    --projection "$PROJECTION" \
    --quantile-limits "$QUANTILE_LIMITS" \
    --point-size "$POINT_SIZE" \
    --alpha "$ALPHA" \
    --title-prefix "$TITLE_PREFIX" \
    --color-cols "$COLOR_COLS"
done
