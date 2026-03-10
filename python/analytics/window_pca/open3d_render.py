from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Noninteractive Open3D renderer for PCA point clouds or voxel centroids.")
    p.add_argument("--input-parquet", required=True, help="Parquet with point rows (pca1,pca2,pca3) or voxel centers")
    p.add_argument("--mode", default="points", choices=["points", "voxels"])
    p.add_argument("--x-col", default="pca1")
    p.add_argument("--y-col", default="pca2")
    p.add_argument("--z-col", default="pca3")
    p.add_argument("--count-col", default="count", help="Voxel count/intensity column for mode=voxels")
    p.add_argument("--max-points", type=int, default=5_000_000, help="Random cap for rendering")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--point-size", type=float, default=1.0)
    p.add_argument("--x-min", type=float, default=None)
    p.add_argument("--x-max", type=float, default=None)
    p.add_argument("--y-min", type=float, default=None)
    p.add_argument("--y-max", type=float, default=None)
    p.add_argument("--z-min", type=float, default=None)
    p.add_argument("--z-max", type=float, default=None)
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--out-image", required=True, help="Output PNG path")
    p.add_argument("--out-ply", default="", help="Optional output point cloud PLY path")
    return p


def _colorize(n: int, values: np.ndarray | None = None) -> np.ndarray:
    if n <= 0:
        return np.empty((0, 3), dtype=np.float64)
    if values is None or len(values) != n:
        return np.full((n, 3), 0.85, dtype=np.float64)
    v = np.log1p(np.asarray(values, dtype=np.float64))
    v -= np.nanmin(v)
    d = np.nanmax(v)
    if not np.isfinite(d) or d <= 0:
        t = np.zeros_like(v)
    else:
        t = np.clip(v / d, 0.0, 1.0)
    # Simple warm gradient without matplotlib dependency.
    r = np.clip(1.5 * t, 0.0, 1.0)
    g = np.clip(1.5 * (1.0 - np.abs(t - 0.5) * 2.0), 0.0, 1.0)
    b = np.clip(1.5 * (1.0 - t), 0.0, 1.0)
    return np.column_stack([r, g, b]).astype(np.float64)


def _downsample(points: np.ndarray, max_points: int, seed: int, colors: np.ndarray | None) -> tuple[np.ndarray, np.ndarray | None]:
    if max_points <= 0 or len(points) <= max_points:
        return points, colors
    rng = np.random.default_rng(int(seed))
    idx = rng.choice(len(points), size=int(max_points), replace=False)
    if colors is None:
        return points[idx], None
    return points[idx], colors[idx]


def main() -> None:
    args = _build_argparser().parse_args()

    try:
        import open3d as o3d  # type: ignore
    except Exception as e:
        raise SystemExit(f"Open3D is required. Install with: pip install open3d. Error: {e}") from e

    df = pd.read_parquet(args.input_parquet)
    for c in (args.x_col, args.y_col, args.z_col):
        if c not in df.columns:
            raise SystemExit(f"Missing coordinate column: {c}")

    xyz = df[[args.x_col, args.y_col, args.z_col]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float64)
    good = np.isfinite(xyz[:, 0]) & np.isfinite(xyz[:, 1]) & np.isfinite(xyz[:, 2])
    xyz = xyz[good]
    if len(xyz) == 0:
        raise SystemExit("No finite points to render")

    colors = None
    if args.mode == "voxels" and args.count_col in df.columns:
        w = pd.to_numeric(df[args.count_col], errors="coerce").to_numpy(dtype=np.float64)
        w = w[good]
        colors = _colorize(len(xyz), w)
    else:
        colors = _colorize(len(xyz), None)

    # Optional bound clipping in PCA coordinates.
    xmin, xmax = args.x_min, args.x_max
    ymin, ymax = args.y_min, args.y_max
    zmin, zmax = args.z_min, args.z_max
    mask = np.ones(len(xyz), dtype=bool)
    if xmin is not None:
        mask &= xyz[:, 0] >= float(xmin)
    if xmax is not None:
        mask &= xyz[:, 0] <= float(xmax)
    if ymin is not None:
        mask &= xyz[:, 1] >= float(ymin)
    if ymax is not None:
        mask &= xyz[:, 1] <= float(ymax)
    if zmin is not None:
        mask &= xyz[:, 2] >= float(zmin)
    if zmax is not None:
        mask &= xyz[:, 2] <= float(zmax)
    if not np.any(mask):
        raise SystemExit("No points remain after applying bounds")
    xyz = xyz[mask]
    if colors is not None:
        colors = colors[mask]

    xyz, colors = _downsample(xyz, int(args.max_points), int(args.seed), colors)

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz)
    if colors is not None:
        pcd.colors = o3d.utility.Vector3dVector(colors)

    if str(args.out_ply).strip():
        out_ply = Path(args.out_ply)
        out_ply.parent.mkdir(parents=True, exist_ok=True)
        o3d.io.write_point_cloud(str(out_ply), pcd)

    out_img = Path(args.out_image)
    out_img.parent.mkdir(parents=True, exist_ok=True)

    vis = o3d.visualization.Visualizer()
    vis.create_window(width=int(args.width), height=int(args.height), visible=False)
    vis.add_geometry(pcd)
    opt = vis.get_render_option()
    opt.point_size = float(args.point_size)
    opt.background_color = np.array([1.0, 1.0, 1.0], dtype=np.float64)
    vis.poll_events()
    vis.update_renderer()
    vis.capture_screen_image(str(out_img), do_render=True)
    vis.destroy_window()

    print(f"[OK] image -> {out_img}")
    if str(args.out_ply).strip():
        print(f"[OK] ply -> {args.out_ply}")


if __name__ == "__main__":
    main()
