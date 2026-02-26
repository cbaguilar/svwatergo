# ML Pipeline

This folder is a new, generalizable ML pipeline for datasets, features, training, and inference.

## Layout
- `registry/` Dataset registry (YAML for now).
- `ingest/` Manifest creation helpers.
- `features/` Feature extraction (TBD).
- `analysis/` PCA/UMAP (TBD).
- `train/` Training/inference (TBD).
- `cli/` Thin CLI wrappers around library functions.

## Registry
Edit `python/ml/registry/datasets.yaml` and point datasets to manifest files.

## Example
```bash
python -m python.ml.cli.ingest --dataset example-audio-raw --version v1 --manifest data/manifests/example_audio_raw.jsonl data/raw/file1.wav
```
