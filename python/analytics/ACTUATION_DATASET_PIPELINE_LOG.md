# Actuation Dataset Pipeline Log

This note records the critical stages and current behavior of the actuation-focused audio dataset pipeline in [`build_audio_actuation_dataset.py`](/home/cbaguilar/work/water/svwatergo/python/analytics/build_audio_actuation_dataset.py).

## Scope

The pipeline builds a site-specific 10s actuation dataset from audio plus PLC data. It is used downstream for:

- frozen PANN embedding caches
- actuation multilabel classifiers
- PCA visualizations
- PLC auxiliary targets

## Critical Stages

1. Audio source discovery and segmentation

- Inputs can include RPI audio and/or Wyze cameras.
- Audio is segmented into fixed windows using `window_seconds` and `stride_seconds`.
- Each segment receives a stable `sample_id` derived from source, path, and timestamps.

2. Mel generation

- Mel spectrogram shards are generated for each segment.
- Dataset build fails hard if expected mel outputs are missing.

3. PLC window-feature join

- For each segment, PLC-derived window features are computed over the same interval.
- These features are joined into the sample rows before labeling.
- Overlapping feature names are prefixed with `plc_` to avoid collisions.

4. Actuation label generation

- Per-actuator duty columns are mapped into `off`, `transition`, `on`, or `unknown`.
- The builder writes:
  - `*_duty_target`
  - `*_state`
  - `*_is_off`
  - `*_is_transition`
  - `*_is_on`
  - `*_is_unknown`
- Joint labels are also written:
  - `actuation_combo`
  - `actuation_bits`
  - `actuation_unknown`

5. Event-window grouping and split assignment

- Consecutive segments with the same actuation combo are grouped into `event_window_id`.
- Train/test/val split assignment is done at the event-window level.
- The split is combo-aware, not source-stratified.

6. Frozen audio embeddings

- The builder writes `embeddings_panns.npz`.
- When enabled, it also writes `embeddings_joined.parquet`.
- These are the caches now reused directly by the multilabel embedding trainer.

## New PLC PCA Stage

The builder now optionally fits a reusable PCA on the joined PLC/window features during dataset generation.

### Goal

This produces a stable PLC latent target at dataset-build time so downstream training does not need to refit PLC PCA repeatedly.

### Selection Logic

- Column selection uses the existing `window_pca.select_pca_columns(...)` path.
- That means the PLC PCA uses the same default include/exclude regex behavior as the scalable window-feature PCA tooling.
- Extra metadata and actuation-label columns are forcibly excluded from this dataset-builder PCA step.

### Fit Behavior

- By default, PLC PCA is fit on the `train` split only.
- If present, `state_unknown` / `state__unknown` rows are dropped from the PCA fit subset.
- Projection is then applied to all rows.

### Artifacts

The builder now writes:

- `samples.parquet`
  - now includes `plc_pca1`, `plc_pca2`, ... columns
- `plc_window_pca_targets.parquet`
  - keyed by `sample_id` and `split`
  - contains `plc_pca*` target columns
- `plc_window_pca_model.npz`
  - reusable PCA model bundle
- `plc_window_pca_model.json`
  - metadata including selected columns, explained variance ratio, and feature ranges

These artifact paths are also recorded in `build_report.json`.

## Downstream Training Notes

1. The actuation multilabel embedding trainer now supports `--embeddings-npz`.

- This avoids recomputing audio embeddings from raw clips when a dataset cache already exists.

2. The trainer also writes richer multilabel prediction detail into `pann_pca_true_vs_pred.parquet`.

- true multilabel combo
- predicted multilabel combo
- confidence summaries
- exact-match indicator
- hamming error
- BCE loss
- per-label truth / prediction / score / BCE columns

3. For classifier-only runs, the current training wrapper defaults to:

- `AUX_PLC_PCA=no`
- `PANN_PCA_WEIGHT=0.0`

That means the classifier is no longer trained to predict the auxiliary PANN PCA target by default.

## Rendering Notes

- The multilabel PCA panel renderer now supports `true_only` layout.
- The all-sites training wrapper uses `true_only` automatically when `PANN_PCA_WEIGHT=0`.
- This avoids rendering a misleading `Pred PCA` row when no auxiliary PCA target is active.

## Open Next Step

Raw audio clip PCA is still not generated during dataset build.

If we want symmetry with the new PLC PCA stage, the next logical artifact set would be:

- `audio_embedding_pca_targets.parquet`
- `audio_embedding_pca_model.npz`
- `audio_embedding_pca_model.json`

That would make both PLC PCA and audio-embedding PCA available as reusable dataset-time targets.
