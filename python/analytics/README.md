# Analytics Python Libraries (Migrated from `svwaternet-site`)

This directory contains the reusable Python analytics code copied from the legacy
`../svwaternet-site/python` tree, without datasets or generated outputs.

Included packages:
- `window_features`: fixed-window feature engineering for PLC data
- `window_pca`: PCA fitting/transform + column selection utilities
- `window_umap`: optional UMAP wrappers (kept for parity, not required for phase 1)
- `digital_twin`: discrete mode-aware twin scaffold for treatment systems (IDLE/PRODUCE/FLUSH)

Included wrapper CLIs:
- `s3_day_to_window_features.py`
- `pca_from_window_features.py`
- `umap_from_pca.py`
- `audio_manifest.py` (audio indexing/relabel manifest; no destructive renames)
- `audio_s3_tag_manifest.py` (apply start/end/day tags to existing S3 objects from manifest)
- `audio_s3_copy_manifest.py` (copy objects to derived start-labeled/day-partitioned prefix)
- `digital_twin_sim.py` (simulate treatment twin trajectories to CSV/JSON)

## Current status

This is a code import + API scaffolding phase. The Go backend (`/api/v1/analytics/*`)
currently accepts analytics job requests and stores them in an in-memory job registry,
but does not yet execute Python jobs.

## Productionization plan (short)

1. Add a Python worker entrypoint that accepts a JSON job spec.
2. Refactor `window_features.pipeline` to expose a pure `DataFrame -> features` function.
3. Keep plotting out of worker execution paths.
4. Store artifacts in local cache first, then promote to S3.
5. Expose artifact metadata and presigned S3 downloads from `svwatergo`.

## Notes

- This directory intentionally excludes `derived/`, `pca_out/`, `cluster_out/`, and other datasets/artifacts.
- The CLIs are retained for local development and regression checks.

## Audio manifest / relabel planning

Use `audio_manifest.py` to index S3 audio clips whose filenames contain end timestamps
(e.g. `bluerock_1751639587.775598.wav`), derive start timestamps, and generate a
human-readable, start-labeled destination key plan partitioned by day.

Example:

```bash
python3 python/analytics/audio_manifest.py \
  --bucket svwn-audio-files \
  --prefix bluerock/ \
  --site bluerock \
  --clip-seconds 10 \
  --timezone America/Los_Angeles \
  --out-dir ./data \
  --emit-copy-plan
```

This writes:
- `audio_manifest.parquet/csv`
- metadata JSON
- optional copy-plan CSV/JSON (source key -> derived start-labeled key)

Recommended safe workflow:

```bash
# 1) Build manifest using measured local WAV durations (preferred)
python3 python/analytics/audio_manifest.py \
  --bucket svwn-audio-files \
  --prefix bluerock/ \
  --site bluerock \
  --local-root /run/media/cbaguilar/T7/audio_data \
  --timezone America/Los_Angeles \
  --out-dir ./data \
  --emit-copy-plan

# 2) Dry-run object tagging
python3 python/analytics/audio_s3_tag_manifest.py \
  --manifest ./data/dataset=audio_manifest/site=bluerock/audio_manifest.parquet \
  --dry-run \
  --limit 5

# 3) Apply tags (optional merge with existing tags)
python3 python/analytics/audio_s3_tag_manifest.py \
  --manifest ./data/dataset=audio_manifest/site=bluerock/audio_manifest.parquet \
  --merge-existing-tags

# 4) Dry-run derived copies
python3 python/analytics/audio_s3_copy_manifest.py \
  --manifest ./data/dataset=audio_manifest/site=bluerock/audio_manifest.parquet \
  --dry-run \
  --limit 5

# 5) Copy to new derived prefix, skip objects already copied
python3 python/analytics/audio_s3_copy_manifest.py \
  --manifest ./data/dataset=audio_manifest/site=bluerock/audio_manifest.parquet \
  --skip-existing
```

## Daily power usage from PLC parquet

Compute daily `powermeter` usage from raw PLC parquet partitions:

```bash
python3 python/analytics/calc_daily_power_usage.py \
  --input-glob '/mnt/d/datasets/svwatergo/raw/plc/*/date=*/data.parquet' \
  --year 2025
```

By default this writes a CSV, parquet copy, summary JSON, a per-site daily power bar chart PNG,
and a per-site daily permeate-delta bar chart PNG to
`/mnt/d/datasets/svwatergo/derived/daily_power_usage`.
