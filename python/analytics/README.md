# Analytics Python Libraries (Migrated from `svwaternet-site`)

This directory contains the reusable Python analytics code copied from the legacy
`../svwaternet-site/python` tree, without datasets or generated outputs.

Included packages:
- `window_features`: fixed-window feature engineering for PLC data
- `window_pca`: PCA fitting/transform + column selection utilities
- `window_umap`: optional UMAP wrappers (kept for parity, not required for phase 1)

Included wrapper CLIs:
- `s3_day_to_window_features.py`
- `pca_from_window_features.py`
- `umap_from_pca.py`

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
