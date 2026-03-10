# Example Commands (audio conda env assumed)

## Generate window features for a single day
```bash
python3 s3_day_to_window_features.py \
  --site bluerock \
  --day 2025-12-01 \
  --timestamp-col plctime \
  --s3-bucket svwaternet \
  --s3-prefix exports/postgres/plc \
  --out-dir ./derived \
  --window-seconds 10
```

## Generate window features for 7 days starting Dec 1, 2025
```bash
SITE=bluerock
WINDOW_S=10
S3_BUCKET=svwaternet
S3_PREFIX=exports/postgres/plc
OUT_DERIVED=./derived

for i in {0..6}; do
  DAY=$(date -d "2025-12-01 +$i day" +%F)
  echo "Generating windows for $DAY"
  python3 s3_day_to_window_features.py \
    --site "$SITE" \
    --day "$DAY" \
    --timestamp-col plctime \
    --s3-bucket "$S3_BUCKET" \
    --s3-prefix "$S3_PREFIX" \
    --out-dir "$OUT_DERIVED" \
    --window-seconds "$WINDOW_S"
done
```

## PCA 3D for 7 days (state palette)
```bash
LIST=/tmp/window_features_7days.txt
> "$LIST"
for i in {0..6}; do
  DAY=$(date -d "2025-12-01 +$i day" +%F)
  echo "./derived/dataset=window_features/window_s=10/site=bluerock/date=${DAY}/window_features.parquet" >> "$LIST"
done

python3 pca_from_window_features.py \
  --input-list "$LIST" \
  --n-components 10 \
  --plot-3d \
  --plot-3d-color-col state__last \
  --plot-3d-color-discrete \
  --plot-3d-hover-col window_start_ts \
  --plot-3d-max-points 200000 \
  --plot-3d-point-size 3 \
  --out-dir ./pca_out \
  --out-prefix bluerock_7days \
  --controls-off
```

## PCA 3D colored by delivery duty
```bash
python3 pca_from_window_features.py \
  --input-list /tmp/window_features_7days.txt \
  --n-components 10 \
  --plot-3d \
  --plot-3d-color-col deliveryrun__duty \
  --plot-3d-hover-col window_start_ts \
  --plot-3d-max-points 200000 \
  --plot-3d-point-size 3 \
  --out-dir ./pca_out \
  --out-prefix bluerock_7days \
  --controls-off
```

## PCA 3D with faint path (discrete state colors)
```bash
python3 pca_from_window_features.py \
  --input-list /tmp/window_features_7days.txt \
  --n-components 10 \
  --plot-3d \
  --plot-3d-color-col state__last \
  --plot-3d-color-discrete \
  --plot-3d-path \
  --plot-3d-path-time-col window_start_ts \
  --plot-3d-path-opacity 0.2 \
  --plot-3d-path-width 1.5 \
  --plot-3d-hover-col window_start_ts \
  --plot-3d-max-points 200000 \
  --plot-3d-point-size 3 \
  --out-dir ./pca_out \
  --out-prefix bluerock_7days \
  --controls-off
```

## Month run (December 2025) + PCA 3D state palette
```bash
SITE=bluerock
WINDOW_S=10
S3_BUCKET=svwaternet
S3_PREFIX=exports/postgres/plc
OUT_DERIVED=./derived

for DAY in $(seq -f "2025-12-%02g" 1 31); do
  echo "Generating windows for $DAY"
  python3 s3_day_to_window_features.py \
    --site "$SITE" \
    --day "$DAY" \
    --timestamp-col plctime \
    --s3-bucket "$S3_BUCKET" \
    --s3-prefix "$S3_PREFIX" \
    --out-dir "$OUT_DERIVED" \
    --window-seconds "$WINDOW_S"
done

LIST=/tmp/window_features_dec2025.txt
> "$LIST"
for DAY in $(seq -f "2025-12-%02g" 1 31); do
  echo "./derived/dataset=window_features/window_s=10/site=bluerock/date=${DAY}/window_features.parquet" >> "$LIST"
done

python3 pca_from_window_features.py \
  --input-list "$LIST" \
  --n-components 10 \
  --plot-3d \
  --plot-3d-color-col state__last \
  --plot-3d-color-discrete \
  --plot-3d-hover-col window_start_ts \
  --plot-3d-max-points 200000 \
  --plot-3d-point-size 3 \
  --out-dir ./pca_out \
  --out-prefix bluerock_dec2025 \
  --controls-off
```

## Single day (Sep 26, 2025) + PCA 3D path colored by alarm duty
```bash
SITE=bluerock
DAY=2025-09-26
WINDOW_S=10
S3_BUCKET=svwaternet
S3_PREFIX=exports/postgres/plc
OUT_DERIVED=./derived

python3 s3_day_to_window_features.py \
  --site "$SITE" \
  --day "$DAY" \
  --timestamp-col plctime \
  --s3-bucket "$S3_BUCKET" \
  --s3-prefix "$S3_PREFIX" \
  --out-dir "$OUT_DERIVED" \
  --window-seconds "$WINDOW_S"

python3 pca_from_window_features.py \
  --input-file "./derived/dataset=window_features/window_s=10/site=${SITE}/date=${DAY}/window_features.parquet" \
  --n-components 10 \
  --plot-3d \
  --plot-3d-color-col alarm__duty \
  --plot-3d-hover-col window_start_ts \
  --plot-3d-path \
  --plot-3d-path-time-col window_start_ts \
  --plot-3d-path-opacity 0.2 \
  --plot-3d-path-width 1.5 \
  --plot-3d-max-points 200000 \
  --plot-3d-point-size 3 \
  --out-dir ./pca_out \
  --out-prefix bluerock_2025-09-26 \
  --controls-off
```

## Noninteractive dense PCA pipeline (month/all-time ready)
```bash
python3 -m python.analytics.window_pca.scalable_cli \
  --local-root ./derived \
  --site bluerock \
  --date-from 2025-12-01 \
  --date-to 2025-12-31 \
  --window-s 10 \
  --n-components 3 \
  --controls-off \
  --backend auto \
  --fit-sample-per-file 2000 \
  --fit-max-samples 2000000 \
  --write-projections \
  --render-mode both \
  --hist-bins-2d 1200 \
  --hist-bins-3d 160 \
  --max-render-points 2000000 \
  --out-dir ./pca_out \
  --out-prefix bluerock_dec2025_noninteractive
```

Outputs:
- `*_pc_heatmaps.png` static 2D density maps (`PC1-PC2`, `PC1-PC3`, `PC2-PC3`)
- `*_pc123_voxels.parquet` sparse 3D voxel counts for dense-cloud rendering
- `*_point_sample.parquet` bounded direct-point sample

## Noninteractive Open3D render from voxel cloud
```bash
python3 -m python.analytics.window_pca.open3d_render \
  --input-parquet ./pca_out/bluerock_dec2025_noninteractive_pc123_voxels.parquet \
  --mode voxels \
  --x-col pc1 --y-col pc2 --z-col pc3 \
  --count-col count \
  --max-points 3000000 \
  --point-size 1.0 \
  --out-image ./pca_out/bluerock_dec2025_open3d.png \
  --out-ply ./pca_out/bluerock_dec2025_open3d.ply
```

## One-command month run + Open3D screenshot
```bash
SITE=bluerock \
LOCAL_ROOT=/mnt/d/datasets/svwatergo/derived \
DATE_FROM=2025-12-01 \
DATE_TO=2025-12-31 \
WINDOW_S=10 \
BACKEND=auto \
OUT_DIR=/mnt/d/datasets/svwatergo/derived/plots/pca_noninteractive \
scripts/pca_bluerock_noninteractive_open3d.sh
```
