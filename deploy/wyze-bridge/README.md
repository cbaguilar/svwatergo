# Wyze Bridge Deployment

This setup runs one `docker-wyze-bridge` container for all of your cameras and stores recordings locally under:

- `deploy/wyze-bridge/record/camera=<name>/date=<YYYY-MM-DD>/`

That path shape matches the existing sync tooling in this repo.

## 1) Configure credentials

```bash
cd deploy/wyze-bridge
cp .env.example .env
```

Edit `.env` and choose one auth method:

- `WYZE_EMAIL` + `WYZE_PASSWORD` + `API_ID` + `API_KEY`, or
- `REFRESH_TOKEN` (or `ACCESS_TOKEN`)

For Google-sign-in Wyze accounts, token auth is often easiest.

## 2) Start container

```bash
docker compose up -d
```

Open the Web UI:

- `http://<host-ip>:5000`

## 3) Verify streams and recording

```bash
docker compose logs -f wyze-bridge
ls -la record
```

## 4) Sync recordings to S3 with existing pipeline

From repo root:

```bash
python -m python.ml.cli.wyze_sync \
  --root deploy/wyze-bridge/record \
  --bucket <your-bucket> \
  --prefix wyze_dump \
  --manifest data/manifests/wyze_sync_manifest.csv
```

## Notes

- Avoid exposing bridge ports to the public internet.
- If `WYZE_PASSWORD` contains `$`, escape as `$$` in `.env`.
- `FILTER_NAMES` can limit ingest to selected cameras.
