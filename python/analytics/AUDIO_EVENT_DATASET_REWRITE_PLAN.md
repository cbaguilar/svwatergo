# Audio Event Dataset Rewrite Plan

## Objective
Build a generalizable audio dataset generation pipeline for:
- audio-based state inference, and
- optional sound-to-sensor regression.

The builder must output training-ready artifacts and deterministic train/test/val splits so training code does not implement data plumbing.

## Scope
- Full rewrite of `python/analytics/build_bluerock_audio_dataset.py`.
- Make logic site-agnostic; no hardcoded `bluerock` behavior in core pipeline.
- Implement Bluerock first, with direct extension paths for Santa Teresa and Pryorfarm.

## Input Data Contracts

### Audio
- RPi WAV clips in flat folder, filename timestamp represents clip **end** time.
- Wyze WEBM clips in `camera=*/date=*`, filename timestamp represents clip **start** time.
- Bluerock Wyze sources currently: `camera=Bluerock_Cam_1`, `camera=Bluerock_Cam_2`, `camera=camera_5`.

### PLC
- Daily parquet at `plc/site=<site>/date=<YYYY-MM-DD>/data.parquet` (with fallback roots allowed).
- PLC interval feature computation uses existing API:
  - `generate_window_features_for_intervals_df(...)`.

## Processing Defaults (v1)
- Output audio: mono WAV at 16 kHz.
- Segment window: 10.0 seconds.
- Stride: 10.0 seconds (no overlap).
- Segment normalization: trim/pad to exact window size.
- Wyze corruption rule: skip input files `< 4096` bytes.
- Decode failures or malformed timestamps: skip and report.

## End-to-End Pipeline
1. Discover sources and available days.
2. Convert/normalize audio to WAV and build source manifests.
3. Segment into fixed windows.
4. Compute PLC interval features for each audio segment.
5. Assign event windows (contiguous PLC activity windows) and event labels.
6. Generate mel spectrograms for all valid segments.
7. Build deterministic grouped train/test/val splits.
8. Emit manifests, dataset stats, and QA report.

## Event Labeling Specification

### Base Class Conditions
- `quiet`: full-segment requirement: `ropumprun == 0` AND `deliveryrun == 0` for the entire segment.
- `producing`: any overlap with `ropumprun == 1`.
- `delivering`: any overlap with `deliveryrun == 1`.
- `flushing`: any overlap with `state in {4, 5}`.

### Precedence (single primary label)
- `flushing` supersedes all.
- `delivering` supersedes `producing`.
- `producing` supersedes `quiet`.

### Multi-state/Transition Metadata
Store both:
- `primary_class` (single class after precedence), and
- overlap metadata for auditability:
  - `overlap_s_quiet`, `overlap_s_producing`, `overlap_s_delivering`, `overlap_s_flushing`,
  - `is_transition_segment`, `transition_count`, `states_seen`.

## Event Window Indexing
- Pre-scan PLC timeline per day to build contiguous event windows.
- Assign `event_window_id` with stable format: `site/date/class/idx`.
- Attach each segment to an event window (primary by max overlap).

## Split Strategy

### Goals
- Target 70/15/15 train/test/val.
- Ratio drift is acceptable to reduce leakage.

### Leakage Control Priority
1. Audio source separation.
2. Day separation.
3. Event window separation.

### Mechanics
- Deterministic split with fixed seed.
- Grouped assignment by `audio_source + day + event_window_id`.
- Emit assignment reason and group keys for auditability.

## Mandatory Mel Spectrogram Generation
Mel generation is a build-time requirement, not training-time preprocessing.

### Requirements
- Generate mel spectrograms for **all valid audio segments**.
- Include all splits and any retained non-supervised rows.
- Store mel outputs in shards with per-row pointers.
- Persist mel config in metadata for reproducibility.

### Mel Config (persisted)
- `sample_rate`, `n_fft`, `win_length`, `hop_length`, `n_mels`, `fmin`, `fmax`, `power`, `log_eps`, `dtype`.

### Row Linkage
Each sample row must include mel references, e.g.:
- `mel_shard_path` (or relpath),
- `mel_index_in_shard` (or equivalent lookup key).

### Integrity
- If a segment expected in supervised splits has missing mel output, build must fail or quarantine row explicitly.

## Output Artifacts
- `samples.parquet`: canonical row-per-segment table with metadata, labels, PLC features, and mel pointers.
- `split_manifest.parquet`: train/test/val assignments with deterministic grouping metadata.
- `dataset_index.parquet`: partition index across site/source/day.
- `class_stats.parquet` and/or `class_stats.json`: counts/duration/samples by class/source/day/split.
- `build_report.json`: corruption/skips/decode failures/missing PLC coverage.

## Required Canonical Columns
- Identity: `sample_id`, `site`, `audio_source`, `camera`, `day_utc`.
- Time: `segment_start_ts_utc`, `segment_end_ts_utc`, `segment_duration_s`.
- Paths: `wav_path`, `mel_shard_path`, `mel_index_in_shard` (or equivalent).
- PLC quality: `window_match_found`, `state_unknown`, `n_rows`, stale/coverage flags.
- Labels: `primary_class`, overlap seconds, transition fields.
- Split: `split`, `split_seed`, grouping identifiers.

## Generalization Requirements
- Site/camera/source mappings must be config-driven.
- No site-specific constants in core split/label logic.
- Reuse same pipeline contract for Bluerock, Santa Teresa, Pryorfarm.

## Acceptance Criteria
- End-to-end build succeeds for Bluerock raw data.
- Wyze `<4KB` files are skipped and counted.
- Label precedence and quiet full-window rule are enforced exactly.
- Train/test/val outputs are deterministic and leakage-auditable.
- Mel spectrograms exist and are linked for all included segments.
- Training loop can consume split outputs directly without additional data pipeline code.
