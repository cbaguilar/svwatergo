# Production Audio Inference Roadmap

This roadmap turns the current audio/PLC research pipeline into a production feature for SVWaterNet: served model inference, persistent prediction history, and operator-facing visualization of audio-derived equipment state.

It is based on the ProQuest preview of Christian Bernardo Aguilar's 2026 UCLA MS thesis, "Passive Acoustic Sensing of Operational State in Distributed Water Treatment Systems," plus the current repository implementation.

## Thesis Basis

The thesis frames SVWaterNet as both production cyberinfrastructure and a research platform for distributed water treatment and desalination systems in small rural communities. The system has run for six years across three Salinas Valley sites, collecting more than one billion telemetry points from sensors, valves, and PLC state.

The audio inference contribution combines that telemetry with more than 30,000 recordings of pumps and actuators. The thesis uses pretrained audio embeddings as the backbone for state reconstruction models:

- A neural multilabel model predicts four pump states at a single site with 0.557 F1, with several individual pumps above 0.85 F1.
- Adding a low-dimensional PCA representation of continuous sensors as an auxiliary target improves discrete state prediction.
- A regression model using the same embedding backbone predicts flow readings from audio, with aggregate matched-domain R2 above 0.80 and some sensors above 0.98.

The production opportunity is to move this from offline reconstruction into live operational decision support: served inference, durable prediction records, and visual review inside SVWaterNet.

## Current Foundation

The repo already has a workable research-to-production spine:

- Go API and analytics job orchestration in `internal/api/analytics_handlers.go`, `internal/analytics/jobs.go`, and `internal/analytics/runner.go`.
- Audio inference request validation in `internal/analytics/audio_inference_contract.go`.
- A long-running Python HTTP inference service in `python/analytics/inference_service.py`.
- Python worker execution in `python/analytics/worker_main.py`.
- Model CLIs for PCA/SVM, Tiny CNN, and pretrained embedding multitask inference under `python/ml/cli/`.
- Audio source and artifact tracking through `internal/audio/store.go` and `internal/api/audio_handlers.go`.
- Operator dashboards in `frontend/svwaternet/src/views/dashboard/` and `frontend/svwaternet/src/views/detailed-dashboard/`.

The production gap is not basic inference. The gap is durable serving semantics, model/version management, prediction persistence, observability, and a frontend that makes audio-derived pump and flow reconstructions inspectable next to PLC state.

## Product Shape

The production feature should present audio inference as a site-level operational tool:

- Select a site, source, model version, and time range.
- Run inference on uploaded clips, S3-backed audio artifacts, or existing segmented windows.
- Display pump-state and flow-reconstruction timelines aligned to PLC state and audio playback.
- Show confidence, entropy/uncertainty, class probabilities, per-target pump states, and predicted flow traces.
- Let operators inspect disputed windows and export predictions for reporting or retraining.

This should not be a separate ML demo. It should live inside SVWaterNet as an operational diagnostic view.

## Serving Architecture

Use the existing Go API as the public control plane and the Python service as the model execution plane.

Control plane:

- `POST /api/v1/analytics/audio-inference-stage` stages uploaded WAV/audio files.
- `POST /api/v1/analytics/audio-inference-runs` creates an inference job.
- `GET /api/v1/analytics/jobs/:id` polls job state and result metadata.
- Future endpoints should expose model versions and persisted prediction windows.

Execution plane:

- `python/analytics/inference_service.py` remains a warm model-serving process.
- `ANALYTICS_INFERENCE_SERVICE_URL` selects service mode; without it, Go falls back to local Python worker execution.
- The service should load and cache model bundles by stable model key, not raw path only.
- The service should support sync inference for short uploads and async batch jobs for day-scale windows.

Production deployment:

- Run the Go API and Python inference service as separate systemd services or containers.
- Keep inference artifacts under a configured root such as `ANALYTICS_ARTIFACTS_ROOT`.
- Use CPU by default; allow CUDA only when explicitly configured and monitored.
- Add health checks for service liveness, model loadability, disk space, and queue latency.

## Model Registry

Add a simple model registry before adding a heavier ML platform.

Initial model record:

- `model_id`
- `version`
- `model_kind`: `pca_svm`, `tiny_cnn`, `pretrained_embedding_multitask`
- `site_scope`: single site, multi-site, or global
- `target_mode`: multiclass, multilabel, or regression
- `targets`
- `auxiliary_targets`: optional PCA/system-state targets used during training
- `artifact_uri`
- `metrics_uri`
- `training_dataset_uri`
- `created_at`
- `created_by`
- `notes`

The existing `AudioInferenceRequest` already accepts `model_id`, `version`, `model_path`, `model_uri`, and `model_kind`. The next step is to resolve `model_id/version` server-side and avoid requiring operators to know filesystem paths.

## Prediction Storage

Persist inference output as first-class operational data, not only job artifacts.

Suggested table family:

- `audio_inference_runs`: request, status, model version, site, source, time range, created user.
- `audio_prediction_windows`: one row per audio segment/window.
- `audio_prediction_scores`: normalized probabilities or regression outputs per target/class.
- `audio_prediction_artifacts`: parquet/json/plot/audio references for the run.

Minimum window fields:

- `run_id`
- `site`
- `source_key`
- `segment_start_time`
- `segment_end_time`
- `audio_artifact_id`
- `model_id`
- `model_version`
- `pred_label`
- `pred_confidence`
- `pred_entropy`
- `predicted_flow_json`
- `prediction_json`

This enables dashboard queries without reopening arbitrary parquet artifacts.

## Visualization

Add an Audio Inference Explorer route in the current React app.

Recommended UI:

- Top controls: site, source, model version, time range, run button.
- Timeline: stacked PLC state, predicted pump state, predicted flow, confidence, and uncertainty.
- Audio strip: playable clips aligned to selected windows.
- Detail panel: selected window metadata, class probabilities, regression outputs, truth labels when available, and links to artifacts.
- Review table: sortable low-confidence windows, model/PLC disagreements, and audio/flow reconstruction outliers.

The existing notebook `python/ml/docs/Audio_Inference_Explorer.ipynb` proves the concept. The production version should move the same inspection loop into `frontend/svwaternet` and fetch data from Go APIs.

## Implementation Milestones

1. Registry and contracts

Add model registry types and API endpoints. Extend `AudioInferenceRequest.Validate()` to allow `pretrained_embedding_multitask` and regression outputs. Add tests for request normalization and validation.

2. Durable jobs

Move analytics job state out of the in-memory `analytics.Store` into SQL. Keep the current API shape so frontend polling does not change.

3. Prediction persistence

Have `run_audio_inference_job()` write normalized prediction rows for classification and regression outputs, then update Go to ingest them into SQL after job success.

4. Explorer backend

Add query endpoints for prediction windows by site/source/model/time range. Include optional PLC alignment columns for dashboard overlays.

5. Explorer frontend

Create `frontend/svwaternet/src/views/audio-inference/AudioInferenceExplorer.js`, add a route, and add a nav item. Reuse CoreUI and existing dashboard query helpers. The first version should prioritize time-aligned review of audio, pump predictions, PLC truth, and predicted flow.

6. Production serving

Package `python/analytics/inference_service.py` with explicit dependencies, startup config, health checks, model cache limits, and deployment docs.

7. Model governance

Store metrics and source data lineage for each model version. Track whether models were trained for a single source, pooled across sources, or pooled across sites. Add operator-facing labels that distinguish research models from production-approved models.

## Thesis Alignment

The production feature should explicitly extend these thesis contributions:

- SVWaterNet as long-running cyberinfrastructure for live monitoring and research analysis.
- Passive acoustic sensing as a low-cost way to reconstruct treatment-system operation.
- PCA system-state representations as auxiliary learning targets.
- Pretrained audio embeddings as the reusable backbone for pump classification and flow regression.
- Multi-source and multi-site evaluation as the basis for model-version metadata and operator trust.

Remaining thesis details to add from the full PDF:

- Full model comparison tables from Chapter 4.
- Source-specific and pooled-model generalization results.
- Stated limitations and future work.
- Exact dataset split methodology and audio-source descriptions.

## Near-Term Next Step

The best next implementation step is milestone 1 plus the first half of milestone 5:

- Add `pretrained_embedding_multitask` to the Go contract.
- Add a model registry API shape.
- Add a frontend Audio Inference Explorer skeleton that can list jobs and eventually render persisted prediction windows.

That gives the project a credible production surface while keeping inference execution compatible with the Python pipeline that already exists.
