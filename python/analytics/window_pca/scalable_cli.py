from __future__ import annotations

import argparse
import datetime as dt
import json
import time
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .model import apply_controls_weight, extract_matrix, fit_pca
from .selection import select_pca_columns


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(str(s))


def _daterange(d0: dt.date, d1: dt.date) -> List[dt.date]:
    if d1 < d0:
        raise SystemExit("--date-to must be >= --date-from")
    n = (d1 - d0).days
    return [d0 + dt.timedelta(days=i) for i in range(n + 1)]


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Scalable noninteractive PCA pipeline for window_features. "
            "Fits PCA on a bounded sample, then projects all matching files "
            "and emits render-friendly density artifacts."
        )
    )
    p.add_argument("--local-root", required=True, help="Root directory containing window_features parquet files")
    p.add_argument("--site", required=True)
    p.add_argument("--date-from", required=True, help="Start date YYYY-MM-DD (inclusive, UTC)")
    p.add_argument("--date-to", required=True, help="End date YYYY-MM-DD (inclusive, UTC)")
    p.add_argument("--window-s", type=int, default=None)
    p.add_argument("--stride-s", type=int, default=None)
    p.add_argument("--input-list", default=None, help="Optional text file with explicit parquet file paths")

    p.add_argument("--pca-cols", default=None, help="Comma-separated PCA columns (optional)")
    p.add_argument("--include-regex", action="append", default=[])
    p.add_argument("--exclude-regex", action="append", default=[])
    p.add_argument("--include-cols-file", default=None)
    p.add_argument("--exclude-cols-file", default=None)
    p.add_argument("--drop-cols", default=None)
    p.add_argument("--drop-unknown", action="store_true", help="Drop state_unknown==1 rows")

    p.add_argument("--n-components", type=int, default=3)
    p.add_argument("--no-standardize", action="store_true")
    p.add_argument("--fill-value", type=float, default=0.0)
    p.add_argument("--clip-abs", type=float, default=None)
    p.add_argument("--controls-weight", type=float, default=1.0)
    p.add_argument("--controls-off", action="store_true")
    p.add_argument("--control-regex", action="append", default=[])

    p.add_argument("--fit-sample-per-file", type=int, default=2000)
    p.add_argument("--fit-max-samples", type=int, default=2_000_000)
    p.add_argument("--fit-seed", type=int, default=0)
    p.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "cpu", "gpu"],
        help="Projection backend. gpu uses cupy for score projection if available.",
    )

    p.add_argument("--write-projections", action="store_true", help="Write projected parquet per source")
    p.add_argument("--projection-compression", default="snappy")
    p.add_argument(
        "--preserve-cols",
        default="window_start_ts,state__last,alarm__duty,deliveryrun__duty,ropumprun__duty",
        help="Comma-separated pass-through columns in projected parquet output",
    )

    p.add_argument(
        "--render-mode",
        default="both",
        choices=["none", "heatmap", "points", "both"],
        help="Noninteractive render artifacts to generate",
    )
    p.add_argument("--hist-bins-2d", type=int, default=1200)
    p.add_argument("--hist-bins-3d", type=int, default=160)
    p.add_argument("--range-q-low", type=float, default=0.005)
    p.add_argument("--range-q-high", type=float, default=0.995)
    p.add_argument("--max-render-points", type=int, default=2_000_000)
    p.add_argument("--color-grid", action="store_true", help="Render 3D color-point grid atlas")
    p.add_argument(
        "--color-cols",
        default="",
        help="Comma-separated columns for color grid. If empty, regex-based selection is used.",
    )
    p.add_argument("--color-include-regex", action="append", default=[])
    p.add_argument("--color-exclude-regex", action="append", default=[])
    p.add_argument("--color-max-cols", type=int, default=18, help="Max color columns for grid rendering")
    p.add_argument("--color-grid-cols-per-page", type=int, default=9, help="Subplots per grid page")

    p.add_argument("--out-dir", default="./pca_out")
    p.add_argument("--out-prefix", default="bluerock_alltime")
    p.add_argument("--verbose", action="store_true")
    return p


def _discover_sources(
    *,
    local_root: str,
    site: str,
    date_from: str,
    date_to: str,
    window_s: Optional[int],
    stride_s: Optional[int],
    input_list: Optional[str],
) -> List[str]:
    out: List[str] = []
    root = Path(local_root)
    days = [d.isoformat() for d in _daterange(_parse_date(date_from), _parse_date(date_to))]

    for d in days:
        found_for_day = False
        if window_s is not None:
            ws = int(window_s)
            candidates: List[Path] = []
            if stride_s is not None and int(stride_s) != ws:
                candidates.append(
                    root
                    / f"window_s={ws}"
                    / f"stride_s={int(stride_s)}"
                    / f"site={site}"
                    / f"date={d}"
                    / "window_features.parquet"
                )
            candidates.append(
                root
                / f"window_s={ws}"
                / f"site={site}"
                / f"date={d}"
                / "window_features.parquet"
            )
            for c in candidates:
                if c.exists():
                    out.append(str(c))
                    found_for_day = True
                    break
        else:
            c = root / f"site={site}" / f"date={d}" / "window_features.parquet"
            if c.exists():
                out.append(str(c))
                found_for_day = True

        if not found_for_day:
            patterns: List[str] = []
            if window_s is not None:
                ws = int(window_s)
                if stride_s is not None and int(stride_s) != ws:
                    patterns.append(
                        f"**/window_s={ws}/stride_s={int(stride_s)}/site={site}/date={d}/window_features.parquet"
                    )
                patterns.append(f"**/window_s={ws}/site={site}/date={d}/window_features.parquet")
            else:
                patterns.append(f"**/site={site}/date={d}/window_features.parquet")
            for pat in patterns:
                for p in sorted(root.glob(pat)):
                    out.append(str(p))

    if input_list:
        for ln in Path(input_list).read_text(encoding="utf-8").splitlines():
            x = ln.strip()
            if x and not x.startswith("#"):
                out.append(x)

    seen = set()
    uniq = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def _source_date(src: str) -> str:
    m = re.search(r"/date=(\d{4}-\d{2}-\d{2})/", src)
    if m:
        return m.group(1)
    return "unknown"


def _sample_df(df: pd.DataFrame, n: int, rng: np.random.Generator) -> pd.DataFrame:
    if n <= 0 or len(df) <= n:
        return df
    idx = rng.choice(len(df), size=int(n), replace=False)
    return df.iloc[np.asarray(idx, dtype=np.int64)].copy()


def _resolve_backend(name: str) -> Tuple[str, object]:
    b = str(name).strip().lower()
    if b == "cpu":
        return "cpu", None
    try:
        import cupy as cp  # type: ignore

        return "gpu", cp
    except Exception as e:
        if b == "gpu":
            raise SystemExit(f"Requested --backend=gpu but cupy is unavailable: {e}") from e
    return "cpu", None


def _project_scores(Xw: np.ndarray, components: np.ndarray, backend: str, cp_mod: object) -> np.ndarray:
    if backend == "gpu":
        cp = cp_mod
        Xg = cp.asarray(Xw, dtype=cp.float32)
        Cg = cp.asarray(components.T, dtype=cp.float32)
        Zg = Xg @ Cg
        return cp.asnumpy(Zg).astype("float64", copy=False)
    return (Xw @ components.T).astype("float64", copy=False)


def _ensure_axis_range(lo: float, hi: float) -> Tuple[float, float]:
    if not np.isfinite(lo) or not np.isfinite(hi):
        return -1.0, 1.0
    if hi <= lo:
        mid = float(lo)
        return mid - 1.0, mid + 1.0
    return float(lo), float(hi)


def _render_heatmaps(
    h12: np.ndarray,
    h13: np.ndarray,
    h23: np.ndarray,
    *,
    out_png: Path,
    title: str,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(20, 6), constrained_layout=True)
    mats = [(h12, "PC1 vs PC2"), (h13, "PC1 vs PC3"), (h23, "PC2 vs PC3")]
    for ax, (h, ttl) in zip(axes, mats):
        img = ax.imshow(np.log1p(h.T), origin="lower", aspect="auto", cmap="inferno")
        ax.set_title(ttl)
        ax.set_xlabel("bin-x")
        ax.set_ylabel("bin-y")
        fig.colorbar(img, ax=ax, fraction=0.046, pad=0.04, label="log(1 + count)")
    fig.suptitle(title)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=170)
    plt.close(fig)


def _render_points(sample_points: np.ndarray, *, out_png: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if sample_points.size == 0:
        return
    x = sample_points[:, 0]
    y = sample_points[:, 1]
    z = sample_points[:, 2]

    fig = plt.figure(figsize=(10, 9), constrained_layout=True)
    ax = fig.add_subplot(111, projection="3d")
    ax.scatter(x, y, z, s=1, alpha=0.15, c="black", linewidths=0)
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.set_zlabel("PC3")
    ax.set_title(title)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=180)
    plt.close(fig)


def _is_discrete_col(name: str, s: pd.Series) -> bool:
    n = str(name).lower()
    if ("state" in n) or ("mode" in n):
        return True
    if pd.api.types.is_bool_dtype(s):
        return True
    if pd.api.types.is_integer_dtype(s):
        return s.nunique(dropna=True) <= 24
    return False


def _render_color_grid_pages(
    df: pd.DataFrame,
    *,
    color_cols: List[str],
    cols_per_page: int,
    out_dir: Path,
    out_prefix: str,
    title_prefix: str,
) -> List[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if len(df) == 0 or len(color_cols) == 0:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    emitted: List[str] = []
    per_page = max(1, int(cols_per_page))
    n_pages = (len(color_cols) + per_page - 1) // per_page

    for p in range(n_pages):
        sub = color_cols[p * per_page : (p + 1) * per_page]
        n = len(sub)
        ncol = min(3, n)
        nrow = (n + ncol - 1) // ncol
        fig = plt.figure(figsize=(6.0 * ncol, 5.2 * nrow), constrained_layout=True)

        for i, c in enumerate(sub, start=1):
            ax = fig.add_subplot(nrow, ncol, i, projection="3d")
            d = df[["pca1", "pca2", "pca3", c]].copy()
            for x in ("pca1", "pca2", "pca3"):
                d[x] = pd.to_numeric(d[x], errors="coerce")
            good = np.isfinite(d["pca1"]) & np.isfinite(d["pca2"]) & np.isfinite(d["pca3"])
            d = d.loc[good]
            if len(d) == 0:
                ax.set_title(f"{c} (no finite points)")
                continue

            s = d[c]
            if _is_discrete_col(c, s):
                codes, _ = pd.factorize(s.astype(str).fillna("nan"), sort=True)
                ax.scatter(
                    d["pca1"],
                    d["pca2"],
                    d["pca3"],
                    c=codes,
                    cmap="tab20",
                    s=1,
                    alpha=0.18,
                    linewidths=0,
                )
            else:
                cnum = pd.to_numeric(s, errors="coerce").to_numpy(dtype=np.float64)
                sc = ax.scatter(
                    d["pca1"],
                    d["pca2"],
                    d["pca3"],
                    c=cnum,
                    cmap="viridis",
                    s=1,
                    alpha=0.18,
                    linewidths=0,
                )
                fig.colorbar(sc, ax=ax, fraction=0.03, pad=0.02)

            ax.set_title(c)
            ax.set_xlabel("PC1")
            ax.set_ylabel("PC2")
            ax.set_zlabel("PC3")

        fig.suptitle(f"{title_prefix} (page {p+1}/{n_pages})")
        out = out_dir / f"{out_prefix}_pc123_color_grid_{p+1:02d}.png"
        fig.savefig(out, dpi=180)
        plt.close(fig)
        emitted.append(str(out))

    return emitted


def _hist3d_sparse_df(hist3d: np.ndarray, ranges: Dict[str, Tuple[float, float]]) -> pd.DataFrame:
    nz = np.nonzero(hist3d)
    if len(nz[0]) == 0:
        return pd.DataFrame(columns=["bin_x", "bin_y", "bin_z", "pc1", "pc2", "pc3", "count"])
    ix = nz[0].astype("int32")
    iy = nz[1].astype("int32")
    iz = nz[2].astype("int32")
    ct = hist3d[nz].astype("int64")
    b = hist3d.shape[0]

    x0, x1 = ranges["pc1"]
    y0, y1 = ranges["pc2"]
    z0, z1 = ranges["pc3"]
    sx = (x1 - x0) / b
    sy = (y1 - y0) / b
    sz = (z1 - z0) / b

    return pd.DataFrame(
        {
            "bin_x": ix,
            "bin_y": iy,
            "bin_z": iz,
            "pc1": x0 + (ix.astype("float64") + 0.5) * sx,
            "pc2": y0 + (iy.astype("float64") + 0.5) * sy,
            "pc3": z0 + (iz.astype("float64") + 0.5) * sz,
            "count": ct,
        }
    )


def _update_reservoir(
    current: np.ndarray,
    incoming: np.ndarray,
    max_points: int,
    rng: np.random.Generator,
) -> np.ndarray:
    if max_points <= 0 or incoming.size == 0:
        return current
    if current.size == 0:
        if len(incoming) <= max_points:
            return incoming.copy()
        idx = rng.choice(len(incoming), size=max_points, replace=False)
        return incoming[idx].copy()

    merged = np.vstack([current, incoming])
    if len(merged) <= max_points:
        return merged
    idx = rng.choice(len(merged), size=max_points, replace=False)
    return merged[idx].copy()


def _update_reservoir_df(
    current: pd.DataFrame,
    incoming: pd.DataFrame,
    max_points: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    if max_points <= 0 or len(incoming) == 0:
        return current
    if len(current) == 0:
        if len(incoming) <= max_points:
            return incoming.copy()
        idx = rng.choice(len(incoming), size=max_points, replace=False)
        return incoming.iloc[np.asarray(idx, dtype=np.int64)].copy()

    merged = pd.concat([current, incoming], ignore_index=True, sort=False)
    if len(merged) <= max_points:
        return merged
    idx = rng.choice(len(merged), size=max_points, replace=False)
    return merged.iloc[np.asarray(idx, dtype=np.int64)].copy()


def _filter_rows(df: pd.DataFrame, drop_unknown: bool) -> pd.DataFrame:
    out = df
    if "n_rows" in out.columns:
        out = out[pd.to_numeric(out["n_rows"], errors="coerce").fillna(0).astype(int) > 0]
    if drop_unknown and "state_unknown" in out.columns:
        out = out[pd.to_numeric(out["state_unknown"], errors="coerce").fillna(0).astype(int) == 0]
    return out


def _parse_csv_cols(s: Optional[str]) -> List[str]:
    if not s:
        return []
    return [x.strip() for x in str(s).split(",") if x.strip()]


def _hist2d_add(
    hist: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    x_rng: Tuple[float, float],
    y_rng: Tuple[float, float],
) -> None:
    h, _, _ = np.histogram2d(x, y, bins=hist.shape[0], range=[list(x_rng), list(y_rng)])
    hist += h.astype(np.uint64)


def _hist3d_add(
    hist: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    x_rng: Tuple[float, float],
    y_rng: Tuple[float, float],
    z_rng: Tuple[float, float],
) -> None:
    b = int(hist.shape[0])
    x0, x1 = x_rng
    y0, y1 = y_rng
    z0, z1 = z_rng
    sx = (x1 - x0) / b
    sy = (y1 - y0) / b
    sz = (z1 - z0) / b
    if sx <= 0 or sy <= 0 or sz <= 0:
        return

    ix = np.floor((x - x0) / sx).astype(np.int64)
    iy = np.floor((y - y0) / sy).astype(np.int64)
    iz = np.floor((z - z0) / sz).astype(np.int64)
    good = (ix >= 0) & (ix < b) & (iy >= 0) & (iy < b) & (iz >= 0) & (iz < b)
    if not np.any(good):
        return
    lin = ix[good] + b * (iy[good] + b * iz[good])
    cnt = np.bincount(lin, minlength=b * b * b)
    hist += cnt.reshape((b, b, b)).astype(np.uint64)


def _save_json(obj: Dict[str, object], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _source_schema_cols(path: str) -> List[str]:
    try:
        import pyarrow.parquet as pq  # type: ignore
    except Exception:
        df = pd.read_parquet(path, engine="pyarrow")
        return list(df.columns)
    sch = pq.read_schema(path)
    return list(sch.names)


def _ensure_cols(df: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    missing = [c for c in cols if c not in df.columns]
    if not missing:
        return df
    out = df.copy()
    for c in missing:
        out[c] = np.nan
    return out


def _projection_out_path(out_dir: Path, site: str, src: str) -> Path:
    d = _source_date(src)
    return out_dir / "projections" / f"site={site}" / f"date={d}" / "pca_projection.parquet"


def _default_color_include_regex() -> List[str]:
    return [
        r"^state(__|$)",
        r"^ropumprun__duty$",
        r"^wellpumprun__duty$",
        r"^feedpumprun__duty$",
        r"flow",
        r"press|pressure",
        r"tank.*level|level.*tank",
        r"daily.*flow",
        r"dailyperm",
        r"dailyfeed",
    ]


def _pick_color_cols(
    schema_cols: Sequence[str],
    *,
    explicit_cols: List[str],
    include_regex: List[str],
    exclude_regex: List[str],
    max_cols: int,
) -> List[str]:
    if explicit_cols:
        return [c for c in explicit_cols if c in schema_cols]
    inc = include_regex[:] if include_regex else _default_color_include_regex()
    inc_regs = [re.compile(p, re.IGNORECASE) for p in inc]
    exc_regs = [re.compile(p, re.IGNORECASE) for p in (exclude_regex or [])]
    picked: List[str] = []
    for c in schema_cols:
        if any(r.search(c) for r in inc_regs) and not any(r.search(c) for r in exc_regs):
            picked.append(c)
    seen = set()
    out: List[str] = []
    for c in picked:
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out[: max(0, int(max_cols))]


def main() -> None:
    args = _build_argparser().parse_args()
    t0 = time.time()
    t_discover0 = t0
    if args.controls_off:
        args.controls_weight = 0.0

    if args.verbose:
        print(
            "[start] scalable PCA "
            f"site={args.site} range={args.date_from}..{args.date_to} "
            f"window_s={args.window_s} backend={args.backend} render_mode={args.render_mode}"
        )

    sources = _discover_sources(
        local_root=args.local_root,
        site=args.site,
        date_from=args.date_from,
        date_to=args.date_to,
        window_s=args.window_s,
        stride_s=args.stride_s,
        input_list=args.input_list,
    )
    if not sources:
        raise SystemExit("No input sources discovered.")
    t_discover1 = time.time()

    if args.verbose:
        print(f"[discover] sources={len(sources)}")

    schema_cols = _source_schema_cols(sources[0])
    explicit_cols = _parse_csv_cols(args.pca_cols)
    always_exclude = _parse_csv_cols(args.drop_cols)
    cols = select_pca_columns(
        pd.DataFrame(columns=schema_cols),
        explicit_cols=explicit_cols if explicit_cols else None,
        include_regex=list(args.include_regex),
        exclude_regex=list(args.exclude_regex),
        include_cols_file=args.include_cols_file,
        exclude_cols_file=args.exclude_cols_file,
        always_exclude=always_exclude,
    )
    if not cols:
        raise SystemExit("No PCA columns selected. Use --pca-cols or include regexes.")

    preserve_cols = _parse_csv_cols(args.preserve_cols)
    color_cols = _pick_color_cols(
        schema_cols,
        explicit_cols=_parse_csv_cols(args.color_cols),
        include_regex=list(args.color_include_regex or []),
        exclude_regex=list(args.color_exclude_regex or []),
        max_cols=int(args.color_max_cols),
    )
    read_cols = sorted(set(cols + preserve_cols + color_cols + ["n_rows", "state_unknown"]))
    if args.verbose and args.color_grid:
        print(f"[color-grid] selected_cols={len(color_cols)} cols={color_cols}")

    rng = np.random.default_rng(int(args.fit_seed))
    t_fit_sample0 = time.time()
    sample_parts: List[pd.DataFrame] = []
    n_fit_rows_read = 0
    for i, src in enumerate(sources):
        src_cols = _source_schema_cols(src)
        use_cols = [c for c in read_cols if c in src_cols]
        df = pd.read_parquet(src, columns=use_cols, engine="pyarrow")
        df = _ensure_cols(df, cols)
        df = _filter_rows(df, bool(args.drop_unknown))
        n_fit_rows_read += len(df)
        if len(df) == 0:
            continue
        sdf = _sample_df(df[cols], int(args.fit_sample_per_file), rng)
        if len(sdf):
            sample_parts.append(sdf)
        if args.verbose and ((i + 1) % 25 == 0):
            elapsed = max(1e-9, time.time() - t0)
            print(
                f"[fit-sample] files={i+1}/{len(sources)} sampled_parts={len(sample_parts)} "
                f"rows_read={n_fit_rows_read} elapsed_s={elapsed:.1f}"
            )

    if not sample_parts:
        raise SystemExit("No rows available for PCA fit sample.")
    t_fit_sample1 = time.time()

    t_fit0 = time.time()
    df_fit = pd.concat(sample_parts, ignore_index=True, sort=False)
    if len(df_fit) > int(args.fit_max_samples):
        df_fit = _sample_df(df_fit, int(args.fit_max_samples), rng)

    control_regex = list(args.control_regex) if args.control_regex else None
    bundle = fit_pca(
        df_fit,
        cols,
        n_components=int(args.n_components),
        whiten=False,
        standardize=not bool(args.no_standardize),
        fill_value=float(args.fill_value),
        clip_abs=args.clip_abs,
        controls_weight=float(args.controls_weight),
        control_regex=control_regex,
    )
    t_fit1 = time.time()
    if args.verbose:
        elapsed = max(1e-9, time.time() - t0)
        print(
            f"[fit] rows_used={len(df_fit)} cols={len(cols)} "
            f"explained_var_sum={float(np.sum(bundle.pca.explained_variance_ratio_)):.4f} "
            f"elapsed_s={elapsed:.1f}"
        )

    backend, cp_mod = _resolve_backend(str(args.backend))
    components = bundle.pca.components_.astype("float64", copy=False)

    Xfit = extract_matrix(df_fit, cols, fill_value=float(args.fill_value), clip_abs=args.clip_abs)
    Xfit_s = bundle.scaler.transform(Xfit)
    Xfit_w = apply_controls_weight(Xfit_s, bundle.control_mask, bundle.controls_weight)
    Zfit = _project_scores(Xfit_w, components, backend, cp_mod)

    qlo = float(args.range_q_low)
    qhi = float(args.range_q_high)
    if not (0.0 <= qlo < qhi <= 1.0):
        raise SystemExit("--range-q-low/high must satisfy 0 <= low < high <= 1")

    p1_lo, p1_hi = _ensure_axis_range(*np.quantile(Zfit[:, 0], [qlo, qhi]))
    p2_lo, p2_hi = _ensure_axis_range(*np.quantile(Zfit[:, 1], [qlo, qhi]))
    p3_lo, p3_hi = _ensure_axis_range(*np.quantile(Zfit[:, 2], [qlo, qhi]))
    ranges = {"pc1": (p1_lo, p1_hi), "pc2": (p2_lo, p2_hi), "pc3": (p3_lo, p3_hi)}

    bins2d = int(args.hist_bins_2d)
    bins3d = int(args.hist_bins_3d)
    hist12 = np.zeros((bins2d, bins2d), dtype=np.uint64)
    hist13 = np.zeros((bins2d, bins2d), dtype=np.uint64)
    hist23 = np.zeros((bins2d, bins2d), dtype=np.uint64)
    hist3d = np.zeros((bins3d, bins3d, bins3d), dtype=np.uint64)

    point_sample = np.empty((0, 3), dtype=np.float64)
    color_sample_df = pd.DataFrame()
    project_rows = 0
    out_dir = Path(args.out_dir)
    projection_manifest: List[Dict[str, object]] = []
    rows_by_date: Dict[str, int] = {}
    files_by_date: Dict[str, int] = {}
    t_project0 = time.time()

    for i, src in enumerate(sources):
        src_cols = _source_schema_cols(src)
        use_cols = [c for c in read_cols if c in src_cols]
        df = pd.read_parquet(src, columns=use_cols, engine="pyarrow")
        df = _ensure_cols(df, cols)
        df = _filter_rows(df, bool(args.drop_unknown))
        if len(df) == 0:
            continue

        X = extract_matrix(df, cols, fill_value=float(args.fill_value), clip_abs=args.clip_abs)
        Xs = bundle.scaler.transform(X)
        Xw = apply_controls_weight(Xs, bundle.control_mask, bundle.controls_weight)
        Z = _project_scores(Xw, components, backend, cp_mod)

        finite = np.isfinite(Z[:, 0]) & np.isfinite(Z[:, 1]) & np.isfinite(Z[:, 2])
        if not np.any(finite):
            continue
        Z = Z[finite]
        df = df.iloc[np.nonzero(finite)[0]].reset_index(drop=True)

        x = Z[:, 0]
        y = Z[:, 1]
        z = Z[:, 2]

        if args.render_mode in {"heatmap", "both"}:
            _hist2d_add(hist12, x, y, ranges["pc1"], ranges["pc2"])
            _hist2d_add(hist13, x, z, ranges["pc1"], ranges["pc3"])
            _hist2d_add(hist23, y, z, ranges["pc2"], ranges["pc3"])
            _hist3d_add(hist3d, x, y, z, ranges["pc1"], ranges["pc2"], ranges["pc3"])

        if args.render_mode in {"points", "both"}:
            point_sample = _update_reservoir(point_sample, Z[:, :3], int(args.max_render_points), rng)
            if args.color_grid and color_cols:
                keep_color = [c for c in color_cols if c in df.columns]
                if keep_color:
                    cdf = df[keep_color].copy()
                    cdf["pca1"] = x.astype("float64")
                    cdf["pca2"] = y.astype("float64")
                    cdf["pca3"] = z.astype("float64")
                    color_sample_df = _update_reservoir_df(
                        color_sample_df,
                        cdf,
                        int(args.max_render_points),
                        rng,
                    )

        if args.write_projections:
            keep_cols = [c for c in preserve_cols if c in df.columns]
            out_df = df[keep_cols].copy()
            out_df["pca1"] = x.astype("float64")
            out_df["pca2"] = y.astype("float64")
            out_df["pca3"] = z.astype("float64")
            out_pq = _projection_out_path(out_dir, args.site, src)
            out_pq.parent.mkdir(parents=True, exist_ok=True)
            out_df.to_parquet(out_pq, index=False, compression=str(args.projection_compression))
            projection_manifest.append(
                {
                    "source": src,
                    "output_projection": str(out_pq),
                    "rows": int(len(out_df)),
                    "date": _source_date(src),
                }
            )

        project_rows += len(Z)
        d = _source_date(src)
        rows_by_date[d] = int(rows_by_date.get(d, 0) + len(Z))
        files_by_date[d] = int(files_by_date.get(d, 0) + 1)
        if args.verbose and ((i + 1) % 25 == 0):
            elapsed = max(1e-9, time.time() - t0)
            rate = project_rows / elapsed
            print(
                f"[project] files={i+1}/{len(sources)} rows={project_rows} "
                f"rows_per_s={rate:.1f} elapsed_s={elapsed:.1f}"
            )
    t_project1 = time.time()

    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / f"{args.out_prefix}_model.joblib"
    meta_path = out_dir / f"{args.out_prefix}_metadata.json"
    points_parquet = out_dir / f"{args.out_prefix}_point_sample.parquet"
    heatmap_png = out_dir / f"{args.out_prefix}_pc_heatmaps.png"
    scatter_png = out_dir / f"{args.out_prefix}_pc123_points.png"
    voxels_parquet = out_dir / f"{args.out_prefix}_pc123_voxels.parquet"
    hist_npz = out_dir / f"{args.out_prefix}_histograms.npz"
    projection_manifest_path = out_dir / f"{args.out_prefix}_projection_manifest.json"

    try:
        import joblib  # type: ignore
    except Exception as e:
        raise SystemExit("Missing joblib. Install with: pip install joblib") from e

    joblib.dump(
        {
            "cols": bundle.cols,
            "scaler": bundle.scaler,
            "pca": bundle.pca,
            "control_mask": bundle.control_mask,
            "controls_weight": bundle.controls_weight,
            "controls_regex": bundle.controls_regex,
            "feature_ranges": bundle.feature_ranges,
        },
        model_path,
    )

    if args.render_mode in {"heatmap", "both"}:
        _render_heatmaps(
            hist12,
            hist13,
            hist23,
            out_png=heatmap_png,
            title=f"{args.site} PCA density ({args.date_from}..{args.date_to})",
        )
        vox = _hist3d_sparse_df(hist3d, ranges)
        vox.to_parquet(voxels_parquet, index=False)
        np.savez_compressed(
            hist_npz,
            hist_pc12=hist12,
            hist_pc13=hist13,
            hist_pc23=hist23,
            hist_pc123=hist3d,
        )

    if args.render_mode in {"points", "both"} and len(point_sample):
        pd.DataFrame(
            {"pca1": point_sample[:, 0], "pca2": point_sample[:, 1], "pca3": point_sample[:, 2]}
        ).to_parquet(points_parquet, index=False)
        _render_points(
            point_sample,
            out_png=scatter_png,
            title=f"{args.site} PCA point sample ({len(point_sample):,} points)",
        )

    color_grid_paths: List[str] = []
    color_grid_dir = out_dir / f"{args.out_prefix}_color_grids"
    if args.color_grid and args.render_mode in {"points", "both"} and len(color_sample_df):
        color_grid_paths = _render_color_grid_pages(
            color_sample_df,
            color_cols=[c for c in color_cols if c in color_sample_df.columns],
            cols_per_page=int(args.color_grid_cols_per_page),
            out_dir=color_grid_dir,
            out_prefix=args.out_prefix,
            title_prefix=f"{args.site} PCA 3D color grid",
        )
    t_render1 = time.time()

    _save_json({"projections": projection_manifest}, projection_manifest_path)

    explained = bundle.pca.explained_variance_ratio_.astype("float64").tolist()
    meta: Dict[str, object] = {
        "created_utc": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
        "site": args.site,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "n_sources": int(len(sources)),
        "n_rows_fit_read": int(n_fit_rows_read),
        "n_rows_fit_used": int(len(df_fit)),
        "n_rows_projected": int(project_rows),
        "cols_selected": cols,
        "n_components": int(args.n_components),
        "standardize": not bool(args.no_standardize),
        "fill_value": float(args.fill_value),
        "clip_abs": args.clip_abs,
        "controls_weight": float(bundle.controls_weight),
        "controls_regex": list(bundle.controls_regex),
        "backend_requested": str(args.backend),
        "backend_used": backend,
        "fit_sample_per_file": int(args.fit_sample_per_file),
        "fit_max_samples": int(args.fit_max_samples),
        "fit_seed": int(args.fit_seed),
        "drop_unknown": bool(args.drop_unknown),
        "pca_cols_explicit": explicit_cols,
        "preserve_cols": preserve_cols,
        "color_grid": bool(args.color_grid),
        "color_cols_selected": color_cols,
        "color_grid_cols_per_page": int(args.color_grid_cols_per_page),
        "explained_variance_ratio": explained,
        "explained_variance_ratio_sum": float(np.sum(bundle.pca.explained_variance_ratio_)),
        "render_mode": args.render_mode,
        "hist_bins_2d": bins2d,
        "hist_bins_3d": bins3d,
        "pc_ranges": {
            "pc1": [p1_lo, p1_hi],
            "pc2": [p2_lo, p2_hi],
            "pc3": [p3_lo, p3_hi],
        },
        "source_stats": {
            "n_days_with_sources": int(len(files_by_date)),
            "requested_days": [d.isoformat() for d in _daterange(_parse_date(args.date_from), _parse_date(args.date_to))],
            "rows_projected_by_date": dict(sorted(rows_by_date.items())),
            "files_by_date": dict(sorted(files_by_date.items())),
            "sources_sample": sources[:200],
        },
        "timing_sec": {
            "discover": float(t_discover1 - t_discover0),
            "fit_sample_read": float(t_fit_sample1 - t_fit_sample0),
            "fit_pca": float(t_fit1 - t_fit0),
            "project": float(t_project1 - t_project0),
            "render_and_write": float(t_render1 - t_project1),
            "total": float(t_render1 - t0),
        },
        "artifacts": {
            "model_joblib": str(model_path),
            "metadata_json": str(meta_path),
            "projection_manifest_json": str(projection_manifest_path),
            "heatmap_png": str(heatmap_png) if args.render_mode in {"heatmap", "both"} else "",
            "voxel_parquet": str(voxels_parquet) if args.render_mode in {"heatmap", "both"} else "",
            "hist_npz": str(hist_npz) if args.render_mode in {"heatmap", "both"} else "",
            "point_sample_parquet": str(points_parquet) if args.render_mode in {"points", "both"} else "",
            "point_sample_png": str(scatter_png) if args.render_mode in {"points", "both"} else "",
            "color_grid_dir": str(color_grid_dir) if len(color_grid_paths) else "",
            "color_grid_pngs": color_grid_paths,
        },
    }
    _save_json(meta, meta_path)
    if args.verbose:
        elapsed = max(1e-9, time.time() - t0)
        rate = (project_rows / elapsed) if project_rows > 0 else 0.0
        print(f"[done] rows={project_rows} elapsed_s={elapsed:.1f} rows_per_s={rate:.1f}")

    print(f"[OK] model -> {model_path}")
    print(f"[OK] meta -> {meta_path}")
    if args.write_projections:
        print(f"[OK] projections manifest -> {projection_manifest_path}")
    if args.render_mode in {"heatmap", "both"}:
        print(f"[OK] heatmap -> {heatmap_png}")
        print(f"[OK] voxels -> {voxels_parquet}")
    if args.render_mode in {"points", "both"} and len(point_sample):
        print(f"[OK] point sample -> {points_parquet}")
        print(f"[OK] point plot -> {scatter_png}")
    if len(color_grid_paths):
        print(f"[OK] color grid -> {color_grid_dir}")


if __name__ == "__main__":
    main()
