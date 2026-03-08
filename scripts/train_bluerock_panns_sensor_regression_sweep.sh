#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-$HOME/svwatergo}"
BASE_SCRIPT="${BASE_SCRIPT:-$REPO/scripts/train_bluerock_panns_plc_pca_encoder.sh}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d_%H%M%S)}"

OUT_ROOT="${OUT_ROOT:-/mnt/d/datasets/svwatergo/derived/checkpoints/bluerock_10s_panns_sensor_regression_sweep_${RUN_TS}}"
LOG_ROOT="${LOG_ROOT:-/mnt/d/datasets/svwatergo/derived/logs/bluerock_10s_panns_sensor_regression_sweep_${RUN_TS}}"

mkdir -p "$OUT_ROOT" "$LOG_ROOT"

FLOW_COLS="permeateflow__mean_tw,deliveryflow__mean_tw,feedflow__mean_tw,concentrateflow__mean_tw,recycleflow__mean_tw,totalroflow__mean_tw,totalfeedflow__mean_tw,totalrecycleflow__mean_tw,totaldelflow__mean_tw,dailypermflow__mean_tw,permeateflow__d1,deliveryflow__d1,feedflow__d1,concentrateflow__d1,recycleflow__d1,totalroflow__d1,totalfeedflow__d1,totalrecycleflow__d1,totaldelflow__d1,dailypermflow__d1,sup_permeateflow_mean_tw,sup_deliveryflow_mean_tw,sup_feedflow_mean_tw,sup_concentrateflow_mean_tw,sup_totalroflow_mean_tw,sup_totalfeedflow_mean_tw,sup_totaldelflow_mean_tw,sup_dailypermflow_mean_tw,sup_permeateflow_d1,sup_deliveryflow_d1,sup_feedflow_d1,sup_concentrateflow_d1,sup_totalroflow_d1,sup_totalfeedflow_d1,sup_totaldelflow_d1,sup_dailypermflow_d1"
PRESSURE_COLS="inletpressure__mean_tw,concentratepressure__mean_tw,permeatepressure__mean_tw,ropressure__mean_tw,deliverypressure__mean_tw,feedpressure__mean_tw,inletpressure__d1,concentratepressure__d1,permeatepressure__d1,ropressure__d1,deliverypressure__d1,feedpressure__d1,sup_inletpressure_mean_tw,sup_concentratepressure_mean_tw,sup_permeatepressure_mean_tw,sup_ropressure_mean_tw,sup_deliverypressure_mean_tw,sup_feedpressure_mean_tw,sup_inletpressure_d1,sup_concentratepressure_d1,sup_permeatepressure_d1,sup_ropressure_d1,sup_deliverypressure_d1,sup_feedpressure_d1"
ALL_COLS="${FLOW_COLS},${PRESSURE_COLS}"

run_one() {
  local name="$1"
  local cols="$2"
  local out_dir="$OUT_ROOT/$name"
  local log_file="$LOG_ROOT/$name.log"

  echo "[RUN] $name"
  echo "      OUT_DIR=$out_dir"
  echo "      LOG=$log_file"

  OUT_DIR="$out_dir" \
  TASK_MODE="${TASK_MODE:-plc_pca_encoder}" \
  MAIN_TASK_WEIGHT="${MAIN_TASK_WEIGHT:-0.0}" \
  PANN_PCA_WEIGHT="${PANN_PCA_WEIGHT:-0.0}" \
  AUX_PLC_PCA="${AUX_PLC_PCA:-yes}" \
  AUX_PLC_TARGET_MODE="${AUX_PLC_TARGET_MODE:-raw}" \
  AUX_PLC_FEATURE_COLS="$cols" \
  AUX_PLC_INCLUDE_DUTY_COLS="${AUX_PLC_INCLUDE_DUTY_COLS:-yes}" \
  bash "$BASE_SCRIPT" 2>&1 | tee "$log_file"
}

run_one "flow" "$FLOW_COLS"
run_one "pressure" "$PRESSURE_COLS"
run_one "all" "$ALL_COLS"

echo "[DONE] outputs -> $OUT_ROOT"
echo "[DONE] logs -> $LOG_ROOT"
