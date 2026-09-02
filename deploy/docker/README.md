# Docker Compose Stack

This directory defines a reproducible local stack for SVWaterGo, the React frontend, and the warm Python audio inference service.

## Services

- `db`: Postgres 16 for API state and audio artifact metadata.
- `api`: Go server from `cmd/server`.
- `inference`: Python HTTP service from `python/analytics/inference_service.py`.
- `frontend`: Static `frontend/svwaternet` build served by nginx.

## Start

From the repo root:

```bash
mkdir -p data/analytics
cp deploy/docker/model_registry.example.json data/analytics/model_registry.json
docker compose -f deploy/docker/docker-compose.yml up --build
```

Open:

- Frontend: `http://localhost:3000/#/audio-inference`
- Go API health: `http://localhost:8080/health`
- Python inference health: `http://localhost:8788/health`

In the frontend header, select the `Localhost` backend if the browser is still configured for `svwaternet.org`.

## Model And Data Mounts

The compose file mounts local `data/` into both API and inference containers at `/app/data`. Keep trained models under `data/checkpoints/...` or update `data/analytics/model_registry.json` to point to the mounted model path.

The widget can use either:

- a direct model path such as `/app/data/checkpoints/.../audio_pca_svm_model.joblib`
- a registry ID such as `ropumprun-pca-svm`

The example registry is intentionally not copied into the image so models can be changed without rebuilding containers.

## Inference Dependencies

The default inference image supports the current PCA/SVM path: numpy, pandas, pyarrow, scikit-learn, joblib, boto3, and ffmpeg.

Torch/PANN models should use a derived image or an expanded requirements file. Keep that separate until the production model set is fixed, because the image size and CPU/GPU runtime choices are materially different.

## Production Notes

This compose stack is suitable for reproducible local validation and small internal deployments. For production, set real secrets, re-enable auth, use managed Postgres or durable volumes, and pin the model registry to approved model artifacts.
