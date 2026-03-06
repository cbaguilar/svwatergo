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
