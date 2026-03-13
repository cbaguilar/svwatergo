# ML Pipeline

This folder is a new, generalizable ML pipeline for datasets, features, training, and inference.

## Layout
- `registry/` Dataset registry (YAML for now).
- `ingest/` Manifest creation helpers.
- `features/` Feature extraction (audio mel implemented).
- `analysis/` PCA helpers.
- `train/` Labeled dataset build + PCA/SVM training/inference.
- `cli/` Thin CLI wrappers around library functions.

## Registry
Edit `python/ml/registry/datasets.yaml` and point datasets to manifest files.

## Example
```bash
python -m python.ml.cli.ingest --dataset example-audio-raw --version v1 --manifest data/manifests/example_audio_raw.jsonl data/raw/file1.wav
```

## Audio PLC Classifier (Initial PCA+SVM Pipeline)
Build a labeled dataset by joining mel segment manifests with aligned PLC rows (supports multiple cameras):

```bash
python -m python.ml.cli.audio_plc_dataset \
  --mel-manifest data/cam1/mel_manifest.parquet \
  --mel-manifest data/cam2/mel_manifest.parquet \
  --plc-rows data/plc/audio_clip_plc_rows.parquet \
  --camera cam1 \
  --camera cam2 \
  --plc-col ropumprun \
  --out-parquet data/derived/ropumprun_labeled_mels.parquet
```

Train a PCA+SVM model (start with `ropumprun=on` as positive):

```bash
python -m python.ml.cli.audio_pca_svm_train \
  --dataset data/derived/ropumprun_labeled_mels.parquet \
  --out-dir data/checkpoints/ropumprun_on_pca_svm \
  --task binary \
  --target-col ropumprun_label \
  --positive-label on \
  --n-components 8
```

Run inference from raw `wav`, rendered mel `webp`, or precomputed mel (`.npy`/`.npz`):

```bash
python -m python.ml.cli.audio_pca_svm_infer \
  --model data/checkpoints/ropumprun_on_pca_svm/audio_pca_svm_model.joblib \
  --wav /path/to/segment.wav
```

## Tiny CNN (Ropumprun) on Existing 10s Mels
Train tiny CNN (requires `torch` in your environment):

```bash
python -m python.ml.cli.audio_tiny_cnn_train \
  --dataset data/derived/ropumprun_labeled_mels_camera_5_2026-03-01_10s.parquet \
  --out-dir data/checkpoints/ropumprun_on_tiny_cnn_camera_5_2026-03-01_10s \
  --task binary \
  --target-col ropumprun_label \
  --positive-label on \
  --epochs 12 \
  --target-seconds 10
```

Use unified inference CLI for either model type:

```bash
# PCA+SVM
python -m python.ml.cli.audio_pca_svm_infer \
  --model data/checkpoints/ropumprun_on_pca_svm_camera_5_2026-03-01_10s/audio_pca_svm_model.joblib \
  --model-kind pca_svm \
  --wav /path/to/new.wav

# Tiny CNN
python -m python.ml.cli.audio_pca_svm_infer \
  --model data/checkpoints/ropumprun_on_tiny_cnn_camera_5_2026-03-01_10s/audio_tiny_cnn_model.pt \
  --model-kind tiny_cnn \
  --wav /path/to/new.wav

# Tiny CNN 4-panel
python -m python.ml.cli.audio_pca_svm_plot \
  --checkpoint-dir data/checkpoints/ropumprun_on_tiny_cnn_camera_5_2026-03-01_10s \
  --out-png data/plots/camera_5_2026-03-01_10s_tiny_cnn_4panel.png
```

One-shot script with existing `camera_5` data:

```bash
DATE=2026-03-01 PYTHON=python3 ./scripts/train_camera5_ropumprun_10s.sh
```

If torch is installed but import fails with `libtorch_cpu.so: cannot enable executable stack`:

```bash
execstack -c $CONDA_PREFIX/lib/python*/site-packages/torch/lib/*.so
```

## Time-Series Transformer (Parquet)
Train a small Transformer on raw parquet time-series to predict future windows.

Single horizon run:

```bash
python -m python.ml.cli.timeseries_transformer_train \
  --dataset data/raw/site_a_timeseries.parquet data/raw/site_b_timeseries.parquet \
  --out-dir data/checkpoints/timeseries_transformer_1h \
  --timestamp-col timestamp \
  --group-col site \
  --horizon 1h \
  --lookback 256 \
  --target-mode mean \
  --epochs 20 \
  --batch-size 128
```

Single horizon from date-partitioned raw PLC data:

```bash
python -m python.ml.cli.timeseries_transformer_train \
  --dataset-root data/raw/plc/bluerock \
  --dataset-filename data.parquet \
  --date-from 2025-01-01 \
  --date-to 2025-12-31 \
  --out-dir data/checkpoints/timeseries_transformer_2025_1h_raw \
  --timestamp-col plctime \
  --horizon 1h \
  --lookback 256
```

Horizon sweep (`1m`, `1h`, `6h`, `24h`):

```bash
DATASETS="data/raw/site_a_timeseries.parquet data/raw/site_b_timeseries.parquet" \
TIMESTAMP_COL=timestamp \
GROUP_COL=site \
OUT_ROOT=data/checkpoints/timeseries_transformer_sweep \
bash scripts/train_timeseries_transformer_horizon_sweep.sh
```

Horizon sweep across all 2025 date partitions:

```bash
DATASET_ROOT=data/raw/plc/bluerock \
DATASET_FILENAME=data.parquet \
DATE_FROM=2025-01-01 \
DATE_TO=2025-12-31 \
TIMESTAMP_COL=plctime \
OUT_ROOT=data/checkpoints/timeseries_transformer_sweep_2025_raw \
bash scripts/train_timeseries_transformer_horizon_sweep.sh
```

Outputs per run:
- `timeseries_transformer.pt`: model weights + normalization stats.
- `timeseries_transformer_metrics.json`: train/val/test metrics and training history.
- `timeseries_transformer_config.json`: feature list and model/data config.
- `timeseries_transformer_checkpoint_latest.pt`: recoverable latest checkpoint (model + optimizer + history).
- `timeseries_transformer_checkpoint_best.pt`: best validation checkpoint.
- `timeseries_transformer_learning_history.json`: epoch-by-epoch learning history (updated during training).

Resume a long run:

```bash
python -m python.ml.cli.timeseries_transformer_train \
  --dataset-root data/raw/plc/bluerock \
  --dataset-filename data.parquet \
  --date-from 2025-12-01 \
  --date-to 2025-12-31 \
  --out-dir data/checkpoints/timeseries_transformer_2025_12_1h_raw \
  --timestamp-col plctime \
  --horizon 1h \
  --epochs 60 \
  --resume-from data/checkpoints/timeseries_transformer_2025_12_1h_raw/timeseries_transformer_checkpoint_latest.pt
```

Backtest + plots per horizon:

```bash
python -m python.ml.cli.timeseries_transformer_backtest \
  --dataset-root data/raw/plc/bluerock \
  --dataset-filename data.parquet \
  --date-from 2025-01-01 \
  --date-to 2025-12-31 \
  --checkpoint-root data/checkpoints/timeseries_transformer_sweep \
  --out-dir data/checkpoints/timeseries_transformer_backtest \
  --timestamp-col plctime \
  --horizons 1m,1h,6h,24h
```

Note: `--model` accepts either `timeseries_transformer.pt` or training checkpoints like
`timeseries_transformer_checkpoint_best.pt` / `timeseries_transformer_checkpoint_latest.pt`.

Backtest outputs per horizon:
- `backtest_predictions.parquet`
- `backtest_metrics.json`
- `backtest_plot.png`

## Multi-Horizon Transformer (Single Shared Model)
Train one shared Transformer with multi-horizon outputs (`1m,1h,6h,24h`) and weighted loss.

```bash
DATASET_ROOT=/mnt/d/datasets/svwatergo/raw/plc/site=bluerock \
DATASET_FILENAME=data.parquet \
DATE_FROM=2025-12-01 \
DATE_TO=2025-12-31 \
TIMESTAMP_COL=plctime \
OUT_DIR=/mnt/d/datasets/svwatergo/derived/checkpoints/timeseries_transformer_multihorizon_2025_12_raw \
EPOCHS=10 \
HORIZONS=1m,1h,6h,24h \
HORIZON_WEIGHTS=1.0,1.0,1.5,2.0 \
bash scripts/train_timeseries_transformer_multihorizon.sh
```

Multi-horizon outputs:
- `timeseries_transformer_multihorizon.pt`
- `timeseries_transformer_multihorizon_metrics.json`
- `timeseries_transformer_multihorizon_config.json`
- `timeseries_transformer_multihorizon_learning_history.json`
- `timeseries_transformer_multihorizon_checkpoint_latest.pt`
- `timeseries_transformer_multihorizon_checkpoint_best.pt`

Split short/long multi-horizon runs with explicit task weights and window features:

```bash
DATASET_ROOT=/mnt/d/datasets/svwatergo/derived/dataset=window_features/window_s=10/site=bluerock \
DATASET_FILENAME=window_features.parquet \
DATE_FROM=2025-01-01 \
DATE_TO=2025-06-30 \
TIMESTAMP_COL=window_end_ts \
SITE=bluerock \
FEATURE_PRESET=window \
OUT_ROOT=/mnt/d/datasets/svwatergo/derived/checkpoints/timeseries_transformer_multihorizon_2025_h1_split \
SHORT_HORIZONS=1m,1h \
SHORT_TARGET_MODE=last \
SHORT_LOOKBACK=256 \
LONG_HORIZONS=6h,24h \
LONG_TARGET_MODE=mean \
LONG_LOOKBACK=512 \
REGRESSION_TASK_WEIGHT=1.0 \
BINARY_TASK_WEIGHT=0.5 \
STATE_TASK_WEIGHT=0.5 \
EPOCHS=10 \
DEVICE=cuda \
bash scripts/train_timeseries_transformer_multihorizon_split.sh
```

Feature presets for the multi-horizon trainer:
- `FEATURE_PRESET=auto`: current numeric auto-selection.
- `FEATURE_PRESET=raw`: expected raw PLC columns for `SITE`.
- `FEATURE_PRESET=window`: expected window-feature columns for `SITE`.

Multi-horizon backtest (single model -> per-horizon plots):

```bash
python -m python.ml.cli.timeseries_transformer_multihorizon_backtest \
  --model /mnt/d/datasets/svwatergo/derived/checkpoints/timeseries_transformer_multihorizon_2025_12_raw/timeseries_transformer_multihorizon.pt \
  --dataset-root /mnt/d/datasets/svwatergo/raw/plc/site=bluerock \
  --dataset-filename data.parquet \
  --date-from 2025-12-01 \
  --date-to 2025-12-31 \
  --out-dir /mnt/d/datasets/svwatergo/derived/checkpoints/timeseries_transformer_multihorizon_2025_12_raw/backtest \
  --timestamp-col plctime
```
