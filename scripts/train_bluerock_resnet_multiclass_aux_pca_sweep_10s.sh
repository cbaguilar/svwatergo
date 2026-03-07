#!/usr/bin/env bash
set -euo pipefail

# Sweep auxiliary PCA loss weight for bluerock ResNet multiclass training.
#
# Defaults:
# - fixed LR (no manual drops, no plateau)
# - auxiliary PCA enabled
# - unique output/log dir per sweep value
#
# Example:
#   bash scripts/train_bluerock_resnet_multiclass_aux_pca_sweep_10s.sh
#   AUX_WEIGHTS="0.1 0.3 0.5 1.0 2.0" EPOCHS=100 \
#     bash scripts/train_bluerock_resnet_multiclass_aux_pca_sweep_10s.sh

REPO="${REPO:-$HOME/svwatergo}"
BASE_OUT_ROOT="${BASE_OUT_ROOT:-/mnt/d/datasets/svwatergo/derived/checkpoints}"
BASE_PLOT_ROOT="${BASE_PLOT_ROOT:-/mnt/d/datasets/svwatergo/derived/plots}"
BASE_LOG_ROOT="${BASE_LOG_ROOT:-/mnt/d/datasets/svwatergo/derived/logs}"

AUX_WEIGHTS="${AUX_WEIGHTS:-0.1 0.3 0.5 1.0 2.0}"
EPOCHS="${EPOCHS:-100}"
LEARNING_RATE="${LEARNING_RATE:-5e-4}"
BATCH_SIZE="${BATCH_SIZE:-64}"
WEIGHT_DECAY="${WEIGHT_DECAY:-1e-4}"

RUN_TAG="${RUN_TAG:-$(date +%Y%m%d_%H%M%S)}"
RUN_ROOT="${RUN_ROOT:-bluerock_10s_resnet_multiclass_auxpca_sweep_${RUN_TAG}}"

SCRIPT_PATH="$REPO/scripts/train_bluerock_resnet_multiclass_10s.sh"
if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "[ERR] Missing base script: $SCRIPT_PATH" >&2
  exit 1
fi

mkdir -p "$BASE_OUT_ROOT" "$BASE_PLOT_ROOT" "$BASE_LOG_ROOT"

echo "[INFO] repo=$REPO"
echo "[INFO] sweep weights: $AUX_WEIGHTS"
echo "[INFO] epochs=$EPOCHS lr=$LEARNING_RATE batch=$BATCH_SIZE wd=$WEIGHT_DECAY"
echo "[INFO] run_root=$RUN_ROOT"

status=0
for w in $AUX_WEIGHTS; do
  w_tag="${w//./p}"
  out_dir="$BASE_OUT_ROOT/${RUN_ROOT}/auxw_${w_tag}"
  plot_png="$BASE_PLOT_ROOT/${RUN_ROOT}/auxw_${w_tag}_5panel.png"
  plot_meta="$BASE_PLOT_ROOT/${RUN_ROOT}/auxw_${w_tag}_5panel.json"
  log_file="$BASE_LOG_ROOT/${RUN_ROOT}/auxw_${w_tag}.log"

  mkdir -p "$out_dir" "$(dirname "$plot_png")" "$(dirname "$log_file")"

  echo
  echo "[RUN] AUX_PCA_WEIGHT=$w"
  echo "      OUT_DIR=$out_dir"
  echo "      LOG=$log_file"

  if ! (
    REPO="$REPO" \
    AUX_TARGET_PCA=yes \
    AUX_PCA_WEIGHT="$w" \
    EPOCHS="$EPOCHS" \
    LEARNING_RATE="$LEARNING_RATE" \
    BATCH_SIZE="$BATCH_SIZE" \
    WEIGHT_DECAY="$WEIGHT_DECAY" \
    LR_DROP_EPOCHS="" \
    LR_PLATEAU=no \
    OUT_DIR="$out_dir" \
    PLOT_PNG="$plot_png" \
    PLOT_META="$plot_meta" \
    bash "$SCRIPT_PATH"
  ) 2>&1 | tee "$log_file"; then
    echo "[FAIL] weight=$w (see $log_file)" >&2
    status=1
  else
    echo "[OK] weight=$w"
  fi
done

echo
echo "[DONE] sweep finished with status=$status"
echo "       checkpoints: $BASE_OUT_ROOT/$RUN_ROOT"
echo "       plots:       $BASE_PLOT_ROOT/$RUN_ROOT"
echo "       logs:        $BASE_LOG_ROOT/$RUN_ROOT"
exit "$status"
