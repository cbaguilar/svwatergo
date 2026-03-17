#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

ACTUATORS = (
    "ropumprun",
    "wellpumprun",
    "feedpumprun",
    "deliveryrun",
    "inletrun",
    "flushrun",
    "concbypassrun",
    "proddiversionrun",
)

ACTUATOR_ABBREV = {
    "ropumprun": "P2",
    "wellpumprun": "WP",
    "feedpumprun": "P1",
    "deliveryrun": "P3",
    "inletrun": "IN",
    "flushrun": "AV2",
    "concbypassrun": "CB",
    "proddiversionrun": "PD",
}


def _infer_site_name(path: Path) -> str:
    text = str(path)
    m = re.search(r"site=([^/]+)", text)
    if m:
        return str(m.group(1))
    return path.stem


def _parse_csv(text: str) -> List[str]:
    return [x.strip() for x in str(text or "").split(",") if x.strip()]


def _parse_label_map(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in str(text or "").split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _resolve_combo_col(df: pd.DataFrame, requested: str) -> str:
    req = str(requested or "").strip()
    candidates = [req] if req else []
    candidates.extend(["actuation_combo", "split_actuation_combo", "primary_class", "state__mode_tw"])
    for cand in candidates:
        if cand and cand in df.columns:
            return cand
    raise ValueError(f"Unable to resolve combo/state column from candidates: {candidates}")


def _resolve_source_col(df: pd.DataFrame, requested: str) -> str:
    req = str(requested or "").strip()
    candidates = [req] if req else []
    candidates.extend(["audio_source", "source_name", "source"])
    for cand in candidates:
        if cand and cand in df.columns:
            return cand
    raise ValueError(f"Unable to resolve source column from candidates: {candidates}")


def _available_actuators(df: pd.DataFrame, requested: Sequence[str]) -> List[str]:
    out: List[str] = []
    for actuator in requested:
        if f"{actuator}_state" in df.columns or f"{actuator}_duty_target" in df.columns:
            out.append(str(actuator))
    return out


def _load_and_tag_samples(paths: Sequence[str], site_names: Sequence[str]) -> pd.DataFrame:
    dfs: List[pd.DataFrame] = []
    if site_names and len(site_names) != len(paths):
        raise ValueError("site_names must be empty or match samples_parquet length")
    for i, p in enumerate(paths):
        path = Path(p)
        df = pd.read_parquet(path)
        site_name = site_names[i] if site_names else _infer_site_name(path)
        df = df.copy()
        if "site" not in df.columns:
            df["site"] = site_name
        else:
            df["site"] = df["site"].fillna(site_name).astype("string")
        dfs.append(df)
    if not dfs:
        raise ValueError("No sample parquet files loaded")
    return pd.concat(dfs, axis=0, ignore_index=True, sort=False)


def _display_scope_value(scope_type: str, scope_value: str, label_map: Dict[str, str]) -> str:
    scope_type = str(scope_type)
    scope_value = str(scope_value)
    if scope_type == "source" and "|" in scope_value:
        site_part, src_part = [x.strip() for x in scope_value.split("|", 1)]
        return f"{label_map.get(site_part, site_part)} | {src_part}"
    return label_map.get(scope_value, scope_value)


def _group_key_rows(df: pd.DataFrame, combo_col: str, source_col: str) -> Tuple[pd.DataFrame, Dict[Tuple[str, str], Dict[str, str]]]:
    rows: List[Dict[str, str]] = []
    meta: Dict[Tuple[str, str], Dict[str, str]] = {}
    for row in df.itertuples(index=False):
        combo = str(getattr(row, combo_col))
        source = str(getattr(row, source_col))
        site = str(getattr(row, "site"))
        for scope_type, scope_value in (
            ("source", f"{site} | {source}"),
            ("site", site),
            ("global", "All Sites"),
        ):
            key = (scope_type, scope_value, combo)
            rows.append({"scope_type": scope_type, "scope_value": scope_value, "combo": combo})
            meta[(scope_type, scope_value)] = {"scope_type": scope_type, "scope_value": scope_value}
    return pd.DataFrame(rows), meta


def _iter_shard_groups(df: pd.DataFrame) -> Iterable[Tuple[str, pd.DataFrame]]:
    for shard_path, g in df.groupby("mel_shard_path", sort=False):
        yield str(shard_path), g


def _binary_actuator_labels(df: pd.DataFrame, actuators: Sequence[str]) -> pd.DataFrame:
    out = df.copy()
    active_masks: List[np.ndarray] = []
    for actuator in actuators:
        state_col = f"{actuator}_state"
        duty_col = f"{actuator}_duty_target"
        if state_col in out.columns:
            active = out[state_col].astype("string").fillna("unknown").eq("on").to_numpy()
        elif duty_col in out.columns:
            active = pd.to_numeric(out[duty_col], errors="coerce").fillna(0.0).to_numpy(dtype=float) >= 0.5
        else:
            active = np.zeros(len(out), dtype=bool)
        out[f"__group__{actuator}"] = active
        active_masks.append(np.asarray(active, dtype=bool))
    if active_masks:
        all_off = ~np.logical_or.reduce(active_masks)
    else:
        all_off = np.ones(len(out), dtype=bool)
    out["__group__all_off"] = all_off
    return out


def _accumulate_group_means(
    df: pd.DataFrame,
    *,
    combo_col: str,
    source_col: str,
    group_mode: str,
    actuators: Sequence[str],
) -> Tuple[Dict[Tuple[str, str, str], np.ndarray], Dict[Tuple[str, str, str], int], Tuple[int, int]]:
    required = {"mel_shard_path", "mel_shard_local_index", combo_col, source_col, "site"}
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    df2 = df.dropna(subset=["mel_shard_path", "mel_shard_local_index"]).copy()
    df2["mel_shard_local_index"] = pd.to_numeric(df2["mel_shard_local_index"], errors="coerce")
    df2 = df2[df2["mel_shard_local_index"].notna()].copy()
    df2["mel_shard_local_index"] = df2["mel_shard_local_index"].astype(int)
    if group_mode == "binary_actuator":
        df2 = _binary_actuator_labels(df2, actuators)

    sums: Dict[Tuple[str, str, str], np.ndarray] = {}
    counts: Dict[Tuple[str, str, str], int] = defaultdict(int)
    mel_shape: Optional[Tuple[int, int]] = None

    for shard_path, g in _iter_shard_groups(df2):
        z = np.load(shard_path)
        key = "mel" if "mel" in z.files else z.files[0]
        mel = np.asarray(z[key], dtype=np.float32)
        if mel.ndim != 3:
            raise ValueError(f"Expected mel shard with 3 dims, got {mel.shape} from {shard_path}")
        if mel_shape is None:
            mel_shape = (int(mel.shape[1]), int(mel.shape[2]))
        idx = g["mel_shard_local_index"].to_numpy(dtype=int)
        subset = mel[idx]
        for row_i, row in enumerate(g.itertuples(index=False)):
            source = str(getattr(row, source_col))
            site = str(getattr(row, "site"))
            if group_mode == "binary_actuator":
                labels: List[str] = []
                for actuator in actuators:
                    if bool(g.iloc[row_i][f"__group__{actuator}"]):
                        labels.append(f"{ACTUATOR_ABBREV.get(actuator, actuator)} ON")
                if bool(g.iloc[row_i]["__group__all_off"]):
                    labels.append("All Off")
            else:
                labels = [str(getattr(row, combo_col))]
            sample = subset[row_i].astype(np.float64, copy=False)
            for label in labels:
                keys = [
                    ("source", f"{site} | {source}", label),
                    ("site", site, label),
                    ("global", "All Sites", label),
                ]
                for k in keys:
                    if k not in sums:
                        sums[k] = np.zeros_like(sample, dtype=np.float64)
                    sums[k] += sample
                    counts[k] += 1

    if mel_shape is None:
        raise ValueError("No mel shards loaded from selected rows")
    return sums, counts, mel_shape


def _build_summary_df(counts: Dict[Tuple[str, str, str], int]) -> pd.DataFrame:
    rows = [
        {"scope_type": k[0], "scope_value": k[1], "combo": k[2], "n_samples": int(v)}
        for k, v in sorted(counts.items())
    ]
    return pd.DataFrame(rows)


def _render_scope_grid(
    *,
    out_path: Path,
    title: str,
    means: Sequence[Tuple[str, np.ndarray, int]],
    vmin: float,
    vmax: float,
    cmap: str,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    n = len(means)
    if n <= 0:
        return
    ncols = min(4, max(1, n))
    nrows = int(math.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.0 * ncols, 3.2 * nrows), constrained_layout=True)
    axes = np.atleast_1d(axes).reshape(nrows, ncols)
    for ax, (combo, avg_mel, n_samples) in zip(axes.flat, means):
        im = ax.imshow(avg_mel, origin="lower", aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
        ax.set_title(f"{combo}\nN={n_samples}", fontsize=9)
        ax.set_xlabel("Frame")
        ax.set_ylabel("Mel Bin")
    for ax in axes.flat[n:]:
        ax.axis("off")
    fig.suptitle(title, fontsize=13)
    fig.colorbar(im, ax=axes.ravel().tolist(), fraction=0.025, pad=0.02)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description="Render mean mel images by combo/source/site/global grouping.")
    p.add_argument("--samples-parquet", nargs="+", required=True, help="One or more samples.parquet paths")
    p.add_argument("--site-names", default="", help="Optional comma-separated site names matching --samples-parquet order")
    p.add_argument("--combo-col", default="actuation_combo")
    p.add_argument("--source-col", default="audio_source")
    p.add_argument("--group-mode", default="combo", choices=["combo", "binary_actuator"])
    p.add_argument("--actuators", default="ropumprun,wellpumprun,feedpumprun,deliveryrun,inletrun,flushrun,concbypassrun,proddiversionrun")
    p.add_argument("--top-k", type=int, default=8, help="Top combos per scope to render")
    p.add_argument("--min-samples", type=int, default=1)
    p.add_argument("--cmap", default="magma")
    p.add_argument(
        "--site-label-map",
        default="bluerock=Site A,santateresa=Site B,pryorfarm=Site C",
        help="Comma-separated raw=display site label mapping used in titles",
    )
    p.add_argument("--out-dir", required=True)
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    site_names = _parse_csv(args.site_names)
    df = _load_and_tag_samples(args.samples_parquet, site_names)
    combo_col = _resolve_combo_col(df, args.combo_col)
    source_col = _resolve_source_col(df, args.source_col)
    actuators = _available_actuators(df, _parse_csv(args.actuators))
    group_mode = str(args.group_mode)
    label_map = _parse_label_map(args.site_label_map)

    sums, counts, _mel_shape = _accumulate_group_means(
        df,
        combo_col=combo_col,
        source_col=source_col,
        group_mode=group_mode,
        actuators=actuators,
    )
    summary = _build_summary_df(counts)
    summary = summary.loc[summary["n_samples"] >= int(args.min_samples)].reset_index(drop=True)
    if len(summary) <= 0:
        raise SystemExit("No groups remain after min-samples filtering.")

    mean_lookup: Dict[Tuple[str, str, str], np.ndarray] = {}
    all_vals: List[np.ndarray] = []
    for key, total in sums.items():
        n = counts.get(key, 0)
        if n <= 0:
            continue
        avg = (total / float(n)).astype(np.float32, copy=False)
        mean_lookup[key] = avg
        all_vals.append(avg.reshape(-1))
    all_concat = np.concatenate(all_vals, axis=0) if all_vals else np.asarray([0.0], dtype=np.float32)
    vmin = float(np.nanquantile(all_concat, 0.01))
    vmax = float(np.nanquantile(all_concat, 0.99))
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        vmin = float(np.nanmin(all_concat))
        vmax = float(np.nanmax(all_concat) + 1e-6)

    summary_csv = out_dir / "mean_mel_group_summary.csv"
    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_csv, index=False)

    for (scope_type, scope_value), g in summary.groupby(["scope_type", "scope_value"], sort=True):
        g2 = g.sort_values(["n_samples", "combo"], ascending=[False, True]).head(int(args.top_k)).reset_index(drop=True)
        items: List[Tuple[str, np.ndarray, int]] = []
        for row in g2.itertuples(index=False):
            key = (str(row.scope_type), str(row.scope_value), str(row.combo))
            avg = mean_lookup.get(key)
            if avg is None:
                continue
            items.append((str(row.combo), avg, int(row.n_samples)))
        if not items:
            continue
        safe_scope = re.sub(r"[^A-Za-z0-9._-]+", "_", str(scope_value))
        display_scope = _display_scope_value(str(scope_type), str(scope_value), label_map)
        out_path = out_dir / scope_type / f"{safe_scope}.png"
        _render_scope_grid(
            out_path=out_path,
            title=(
                f"Mean Mel by pooled binary actuator state | {scope_type}={display_scope}"
                if group_mode == "binary_actuator"
                else f"Mean Mel by {combo_col} | {scope_type}={display_scope}"
            ),
            means=items,
            vmin=vmin,
            vmax=vmax,
            cmap=str(args.cmap),
        )

    meta = {
        "samples_parquet": [str(x) for x in args.samples_parquet],
        "combo_col": str(combo_col),
        "source_col": str(source_col),
        "group_mode": group_mode,
        "actuators": actuators,
        "top_k": int(args.top_k),
        "min_samples": int(args.min_samples),
        "summary_csv": str(summary_csv),
        "scopes": sorted(summary["scope_type"].astype(str).unique().tolist()),
        "n_groups": int(len(summary)),
        "color_limits": {"vmin_q01": vmin, "vmax_q99": vmax},
    }
    (out_dir / "mean_mel_group_summary.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"[ok] summary -> {summary_csv}")
    print(f"[ok] plots   -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
