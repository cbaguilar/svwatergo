#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


def _ensure_repo_on_syspath() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


_ensure_repo_on_syspath()


from python.analytics.build_audio_event_dataset import (
    _build_rpi_stage,
    _build_wyze_stage,
    _canonical_audio_source,
    _canonical_wyze_camera,
    _import_ml_audio_mel,
    _import_window_features_pipeline,
    _label_segments_with_plc_overlap,
    _parse_bool_text,
    _read_plc_day,
    _resolve_paths,
    _segment_source_day,
    _stable_group_sort_key,
    _window_features_for_segments,
)
from python.ml.train.audio_pretrained_embeddings import _PannsBackend, _extract_embeddings
from python.analytics.window_pca.model import fit_pca, transform_pca
from python.analytics.window_pca.selection import select_pca_columns


ACTUATORS: tuple[str, ...] = (
    "ropumprun",
    "wellpumprun",
    "feedpumprun",
    "deliveryrun",
    "inletrun",
    "flushrun",
    "concbypassrun",
    "proddiversionrun",
)


def _parse_csv_list(text: str) -> List[str]:
    return [x.strip() for x in str(text).split(",") if x.strip()]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Build actuation-focused audio dataset: segment audio, generate mel spectrograms, "
            "attach PLC window features, derive off/transition/on actuator labels, stratify by "
            "joint actuation combo, and optionally extract PANN embeddings."
        )
    )
    p.add_argument("--site", default="bluerock", help="Site label")
    p.add_argument("--raw-root", default="/mnt/d/datasets/svwatergo/raw", help="Root with plc/, rpi_audio/, wyze_dump/")
    p.add_argument("--out-root", default="/mnt/d/datasets/svwatergo/derived", help="Output root")
    p.add_argument("--plc-root", default="", help="PLC root (default: <raw-root>/plc)")
    p.add_argument("--plc-fallback-root", default="", help="Optional fallback PLC root")
    p.add_argument("--rpi-root", default="", help="RPI WAV root (default: <raw-root>/rpi_audio/<site>)")
    p.add_argument("--wyze-root", default="", help="Wyze root (default: <raw-root>/wyze_dump)")
    p.add_argument("--include-rpi", action="store_true", help="Include RPI audio source")
    p.add_argument("--include-wyze", action="store_true", help="Include Wyze sources")
    p.add_argument("--wyze-camera", action="append", default=[], help="Limit to specific Wyze camera name (repeatable)")
    p.add_argument("--date", action="append", default=[], help="Limit to YYYY-MM-DD (repeatable)")

    p.add_argument("--sample-rate", type=int, default=16000)
    p.add_argument("--window-seconds", type=float, default=10.0)
    p.add_argument("--stride-seconds", type=float, default=10.0)
    p.add_argument("--max-event-gap-seconds", type=float, default=60.0)
    p.add_argument("--max-event-window-seconds", type=float, default=200.0)
    p.add_argument("--max-gap-stale-s", type=float, default=300.0)
    p.add_argument("--wyze-min-size-bytes", type=int, default=4096)
    p.add_argument("--wyze-convert-workers", type=int, default=4)

    p.add_argument("--split-seed", type=int, default=1337)
    p.add_argument("--train-ratio", type=float, default=0.70)
    p.add_argument("--test-ratio", type=float, default=0.15)
    p.add_argument("--val-ratio", type=float, default=0.15)
    p.add_argument(
        "--split-actuators",
        default="ropumprun,wellpumprun,feedpumprun,deliveryrun,flushrun",
        help="Comma-separated actuator subset used for split stratification key",
    )
    p.add_argument(
        "--split-min-positive-count",
        type=int,
        default=3,
        help="Minimum positive row count required in val and test for each split actuator",
    )

    p.add_argument("--mel-n-fft", type=int, default=1024)
    p.add_argument("--mel-win-length", type=int, default=1024)
    p.add_argument("--mel-hop-length", type=int, default=256)
    p.add_argument("--mel-n-mels", type=int, default=64)
    p.add_argument("--mel-fmin", type=float, default=20.0)
    p.add_argument("--mel-fmax", type=float, default=8000.0)
    p.add_argument("--mel-power", type=float, default=2.0)
    p.add_argument("--mel-log-eps", type=float, default=1e-10)
    p.add_argument(
        "--mel-normalization",
        default="legacy",
        choices=["legacy", "none", "log_db", "log10", "log1p_zscore", "log10_median_sub"],
    )
    p.add_argument("--mel-dtype", choices=["float16", "float32"], default="float32")
    p.add_argument("--mel-shard-size", type=int, default=1024)

    p.add_argument(
        "--skip-existing",
        dest="skip_existing",
        action="store_true",
        default=True,
        help="Skip converting/rewriting outputs that already exist (default: enabled)",
    )
    p.add_argument("--no-skip-existing", dest="skip_existing", action="store_false")
    p.add_argument("--skip-wyze-conversion", action="store_true")
    p.add_argument("--embedding-device", default="cuda", choices=["cuda", "cpu"])
    p.add_argument("--embedding-target-seconds", type=float, default=10.0)
    p.add_argument("--embedding-batch-size", type=int, default=32)
    p.add_argument("--embedding-num-workers", type=int, default=8)
    p.add_argument("--embedding-log-every", type=int, default=512)
    p.add_argument(
        "--write-embeddings-joined",
        nargs="?",
        const=True,
        default=True,
        type=_parse_bool_text,
        help="Write embedding vectors as a joined parquet alongside the npz cache (yes/no)",
    )
    p.add_argument(
        "--write-plc-pca",
        nargs="?",
        const=True,
        default=True,
        type=_parse_bool_text,
        help="Fit and write PLC/window-feature PCA targets alongside the actuation dataset (yes/no)",
    )
    p.add_argument("--plc-pca-components", type=int, default=8)
    p.add_argument("--plc-pca-fill-value", type=float, default=0.0)
    p.add_argument("--plc-pca-clip-abs", type=float, default=None)
    p.add_argument("--plc-pca-controls-weight", type=float, default=1.0)
    p.add_argument("--plc-pca-fit-split", default="train", choices=["train", "all"])
    p.add_argument("--plc-pca-cols", default="", help="Optional explicit PLC PCA columns")
    p.add_argument("--plc-pca-include-regex", action="append", default=[])
    p.add_argument("--plc-pca-exclude-regex", action="append", default=[])
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def _find_duty_col(df: pd.DataFrame, actuator: str) -> str:
    candidates = [
        f"{actuator}_duty",
        f"sup_{actuator}_duty",
        f"{actuator}__duty",
        f"plc_{actuator}__duty",
    ]
    for c in candidates:
        if c in df.columns:
            return c
    return ""


def _bucket_duty(series: pd.Series, *, eps: float = 1e-6) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    out = pd.Series(np.full(len(x), "unknown", dtype=object), index=x.index, dtype="string")
    known = x.notna()
    out.loc[known & (x <= eps)] = "off"
    out.loc[known & (x >= 1.0 - eps)] = "on"
    out.loc[known & (x > eps) & (x < 1.0 - eps)] = "transition"
    return out


def _build_actuation_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    combo_parts: List[pd.Series] = []
    bit_parts: List[pd.Series] = []
    state_code = {"off": "0", "transition": "1", "on": "2", "unknown": "u"}

    for actuator in ACTUATORS:
        duty_col = _find_duty_col(out, actuator)
        if duty_col:
            duty = pd.to_numeric(out[duty_col], errors="coerce")
        else:
            duty = pd.Series(np.nan, index=out.index, dtype=float)
        out[f"{actuator}_duty_target"] = duty.astype(float)
        state = _bucket_duty(duty)
        out[f"{actuator}_state"] = state
        out[f"{actuator}_is_off"] = state.eq("off")
        out[f"{actuator}_is_transition"] = state.eq("transition")
        out[f"{actuator}_is_on"] = state.eq("on")
        out[f"{actuator}_is_unknown"] = state.eq("unknown")
        combo_parts.append(pd.Series(f"{actuator}=", index=out.index, dtype="string") + state.astype("string"))
        bit_parts.append(state.map(state_code).fillna("u").astype("string"))

    combo_df = pd.concat(combo_parts, axis=1)
    bits_df = pd.concat(bit_parts, axis=1)
    out["actuation_combo"] = combo_df.agg("|".join, axis=1).astype("string")
    out["actuation_bits"] = bits_df.agg("".join, axis=1).astype("string")
    out["actuation_unknown"] = out[[f"{a}_is_unknown" for a in ACTUATORS]].any(axis=1)
    return out


def _build_selected_actuation_key(df: pd.DataFrame, actuators: Sequence[str]) -> pd.DataFrame:
    out = df.copy()
    combo_parts: List[pd.Series] = []
    bit_parts: List[pd.Series] = []
    state_code = {"off": "0", "transition": "1", "on": "2", "unknown": "u"}
    used: List[str] = []
    for actuator in actuators:
        state_col = f"{actuator}_state"
        if state_col not in out.columns:
            raise ValueError(f"Missing state column for split actuator: {state_col}")
        state = out[state_col].astype("string").fillna("unknown")
        combo_parts.append(pd.Series(f"{actuator}=", index=out.index, dtype="string") + state.astype("string"))
        bit_parts.append(state.map(state_code).fillna("u").astype("string"))
        used.append(str(actuator))
    combo_df = pd.concat(combo_parts, axis=1)
    bits_df = pd.concat(bit_parts, axis=1)
    out["split_actuators"] = ",".join(used)
    out["split_actuation_combo"] = combo_df.agg("|".join, axis=1).astype("string")
    out["split_actuation_bits"] = bits_df.agg("".join, axis=1).astype("string")
    return out


def _attach_event_windows_for_combo(
    df: pd.DataFrame,
    *,
    combo_col: str,
    max_gap_seconds: float,
    max_window_seconds: float,
) -> pd.DataFrame:
    out = df.copy()
    out["segment_start_ts_utc"] = pd.to_datetime(out["segment_start_ts_utc"], utc=True, errors="coerce")
    out["segment_end_ts_utc"] = pd.to_datetime(out["segment_end_ts_utc"], utc=True, errors="coerce")
    out = out.sort_values(["audio_source", "day_utc", "segment_start_ts_utc", "sample_id"]).reset_index(drop=True)

    event_ids: List[str] = []
    last_key: Optional[tuple[str, str]] = None
    last_combo = ""
    last_end: Optional[pd.Timestamp] = None
    window_start: Optional[pd.Timestamp] = None
    idx = -1
    max_window_s = float(max_window_seconds)

    for row in out.itertuples(index=False):
        key = (str(row.audio_source), str(row.day_utc))
        combo = str(getattr(row, combo_col))
        start = pd.Timestamp(row.segment_start_ts_utc)
        end = pd.Timestamp(row.segment_end_ts_utc)

        new_window = False
        if key != last_key or combo != last_combo or last_end is None:
            new_window = True
        else:
            gap_s = float((start - last_end).total_seconds())
            if gap_s > float(max_gap_seconds):
                new_window = True
            elif max_window_s > 0 and window_start is not None:
                window_duration_s = float((end - window_start).total_seconds())
                if window_duration_s > max_window_s:
                    new_window = True

        if new_window:
            idx += 1
            window_start = start

        event_ids.append(f"{row.site}/{row.day_utc}/{combo}/{idx:06d}")
        last_key = key
        last_combo = combo
        last_end = end

    out["event_window_id"] = pd.Series(event_ids, dtype="string")
    return out


def _split_assign_by_combo(
    df: pd.DataFrame,
    *,
    combo_col: str,
    split_actuators: Sequence[str],
    min_positive_count: int,
    seed: int,
    train_ratio: float,
    test_ratio: float,
    val_ratio: float,
) -> pd.DataFrame:
    if df.empty:
        out = df.copy()
        out["split"] = pd.Series([], dtype="string")
        return out

    out = df.copy()
    out["split_group_id"] = out["event_window_id"].astype("string")
    grp = (
        out.groupby("split_group_id", as_index=False)
        .agg(
            n_rows=("split_group_id", "size"),
            combo=(combo_col, "first"),
        )
    )
    grp["_hash"] = grp["split_group_id"].map(lambda s: _stable_group_sort_key(str(s), seed))
    grp = grp.sort_values(["n_rows", "_hash"], ascending=[False, True]).reset_index(drop=True)

    total = int(grp["n_rows"].sum())
    target = {
        "train": max(0, int(round(train_ratio * total))),
        "test": max(0, int(round(test_ratio * total))),
        "val": max(0, int(round(val_ratio * total))),
    }
    current = {"train": 0, "test": 0, "val": 0}

    combos = sorted(grp["combo"].astype(str).unique().tolist())
    combo_current_rows = {k: {"train": 0, "test": 0, "val": 0} for k in combos}
    combo_current_windows = {k: {"train": 0, "test": 0, "val": 0} for k in combos}
    combo_target_rows: Dict[str, Dict[str, int]] = {}
    combo_target_windows: Dict[str, Dict[str, int]] = {}
    for combo in combos:
        m = grp["combo"].astype(str) == combo
        rows_total = int(grp.loc[m, "n_rows"].sum())
        win_total = int(m.sum())
        combo_target_rows[combo] = {
            "train": max(0, int(round(train_ratio * rows_total))),
            "test": max(0, int(round(test_ratio * rows_total))),
            "val": max(0, int(round(val_ratio * rows_total))),
        }
        combo_target_windows[combo] = {
            "train": max(0, int(round(train_ratio * win_total))),
            "test": max(0, int(round(test_ratio * win_total))),
            "val": max(0, int(round(val_ratio * win_total))),
        }

    group_to_split: Dict[str, str] = {}
    positive_col_names = [f"{a}_split_positive" for a in split_actuators]
    for actuator in split_actuators:
        duty_col = f"{actuator}_duty_target"
        if duty_col not in out.columns:
            raise ValueError(f"Missing duty target for split actuator: {duty_col}")
        out[f"{actuator}_split_positive"] = (
            pd.to_numeric(out[duty_col], errors="coerce") >= 0.5
        ).fillna(False)
    group_pos = (
        out.groupby("split_group_id", as_index=False)[positive_col_names]
        .sum()
    )
    group_pos_map: Dict[str, Dict[str, int]] = {}
    for row in group_pos.itertuples(index=False):
        gid = str(row.split_group_id)
        group_pos_map[gid] = {
            actuator: int(getattr(row, f"{actuator}_split_positive"))
            for actuator in split_actuators
        }
    split_positive_counts = {
        "train": {str(a): 0 for a in split_actuators},
        "test": {str(a): 0 for a in split_actuators},
        "val": {str(a): 0 for a in split_actuators},
    }

    def _delta_error(cur_v: int, proj_v: int, target_v: int) -> float:
        cur_over = max(0, cur_v - target_v)
        proj_over = max(0, proj_v - target_v)
        cur_err = abs(cur_v - target_v) + (cur_over * 2)
        proj_err = abs(proj_v - target_v) + (proj_over * 2)
        return float(proj_err - cur_err)

    def _cost(combo: str, n: int, split: str) -> float:
        cw_cur = combo_current_windows[combo][split]
        cw_proj = cw_cur + 1
        cw_target = combo_target_windows[combo][split]
        cr_cur = combo_current_rows[combo][split]
        cr_proj = cr_cur + int(n)
        cr_target = combo_target_rows[combo][split]
        g_cur = current[split]
        g_proj = g_cur + int(n)
        g_target = target[split]
        return (
            14.0 * _delta_error(cw_cur, cw_proj, cw_target)
            + 2.0 * _delta_error(cr_cur, cr_proj, cr_target)
            + 1.0 * _delta_error(g_cur, g_proj, g_target)
        )

    def _assign(gid: str, combo: str, n: int, allowed: Optional[Sequence[str]] = None) -> None:
        if gid in group_to_split:
            return
        choices = list(allowed) if allowed else ["train", "test", "val"]
        split = min(choices, key=lambda sp: _cost(combo, n, sp))
        group_to_split[gid] = split
        current[split] += int(n)
        combo_current_rows[combo][split] += int(n)
        combo_current_windows[combo][split] += 1
        pos_node = group_pos_map.get(gid, {})
        for actuator in split_actuators:
            split_positive_counts[split][str(actuator)] += int(pos_node.get(str(actuator), 0))

    def _reassign(gid: str, combo: str, n: int, new_split: str) -> None:
        old_split = group_to_split.get(gid)
        if old_split == new_split or old_split is None:
            return
        current[old_split] -= int(n)
        combo_current_rows[combo][old_split] -= int(n)
        combo_current_windows[combo][old_split] -= 1
        current[new_split] += int(n)
        combo_current_rows[combo][new_split] += int(n)
        combo_current_windows[combo][new_split] += 1
        pos_node = group_pos_map.get(gid, {})
        for actuator in split_actuators:
            val = int(pos_node.get(str(actuator), 0))
            split_positive_counts[old_split][str(actuator)] -= val
            split_positive_counts[new_split][str(actuator)] += val
        group_to_split[gid] = new_split

    for combo in combos:
        combo_rows = grp[grp["combo"].astype(str) == combo].sort_values("_hash").reset_index(drop=True)
        if combo_rows.empty:
            continue
        n_groups = int(len(combo_rows))
        if n_groups >= 3:
            seed_splits = ["train", "test", "val"]
        elif n_groups == 2:
            seed_splits = ["train", "test"]
        else:
            seed_splits = ["train"]
        for i in range(min(len(seed_splits), len(combo_rows))):
            row = combo_rows.iloc[i]
            _assign(str(row["split_group_id"]), str(row["combo"]), int(row["n_rows"]), allowed=[seed_splits[i]])
        for i in range(len(seed_splits), len(combo_rows)):
            row = combo_rows.iloc[i]
            _assign(str(row["split_group_id"]), str(row["combo"]), int(row["n_rows"]), allowed=None)

    for row in grp.itertuples(index=False):
        gid = str(row.split_group_id)
        if gid not in group_to_split:
            _assign(gid, str(row.combo), int(row.n_rows), allowed=None)

    min_pos = max(0, int(min_positive_count))
    if min_pos > 0 and len(split_actuators) > 0:
        grp_rows = {
            str(row.split_group_id): {"combo": str(row.combo), "n_rows": int(row.n_rows)}
            for row in grp.itertuples(index=False)
        }
        for target_split in ("test", "val"):
            for actuator in split_actuators:
                actuator = str(actuator)
                need = min_pos - int(split_positive_counts[target_split][actuator])
                if need <= 0:
                    continue
                candidate_ids: List[str] = []
                for gid, meta in grp_rows.items():
                    old_split = group_to_split.get(gid, "")
                    if old_split == target_split:
                        continue
                    gain = int(group_pos_map.get(gid, {}).get(actuator, 0))
                    if gain <= 0:
                        continue
                    if old_split in ("test", "val"):
                        donor_after = int(split_positive_counts[old_split][actuator]) - gain
                        if donor_after < min_pos:
                            continue
                    candidate_ids.append(gid)
                candidate_ids = sorted(
                    candidate_ids,
                    key=lambda gid: (
                        0 if group_to_split.get(gid) == "train" else 1,
                        _cost(grp_rows[gid]["combo"], grp_rows[gid]["n_rows"], target_split)
                        - _cost(grp_rows[gid]["combo"], grp_rows[gid]["n_rows"], group_to_split.get(gid, "train")),
                        grp_rows[gid]["n_rows"],
                        gid,
                    ),
                )
                for gid in candidate_ids:
                    if split_positive_counts[target_split][actuator] >= min_pos:
                        break
                    meta = grp_rows[gid]
                    _reassign(gid, meta["combo"], meta["n_rows"], target_split)

    out["split"] = out["split_group_id"].map(group_to_split).astype("string")
    out["split_seed"] = int(seed)
    out["split_target_train"] = float(train_ratio)
    out["split_target_test"] = float(test_ratio)
    out["split_target_val"] = float(val_ratio)
    out["split_min_positive_count"] = int(min_positive_count)
    for actuator in split_actuators:
        out[f"{actuator}_split_positive"] = out[f"{actuator}_split_positive"].astype(bool)
    return out


def _build_stats(samples: pd.DataFrame) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "n_rows": int(len(samples)),
        "n_sources": int(samples["audio_source"].nunique()) if "audio_source" in samples.columns else 0,
        "n_days": int(samples["day_utc"].nunique()) if "day_utc" in samples.columns else 0,
        "n_combos": int(samples["actuation_combo"].nunique()) if "actuation_combo" in samples.columns else 0,
    }
    by_combo = (
        samples.groupby(["split", "actuation_combo"], dropna=False)
        .size()
        .reset_index(name="n_samples")
        .sort_values(["split", "n_samples"], ascending=[True, False])
    )
    stats["by_split_combo"] = by_combo.to_dict(orient="records")
    by_source = (
        samples.groupby(["split", "audio_source"], dropna=False)
        .size()
        .reset_index(name="n_samples")
        .sort_values(["split", "n_samples"], ascending=[True, False])
    )
    stats["by_split_source"] = by_source.to_dict(orient="records")
    if "split_actuation_combo" in samples.columns:
        by_split_key = (
            samples.groupby(["split", "split_actuation_combo"], dropna=False)
            .size()
            .reset_index(name="n_samples")
            .sort_values(["split", "n_samples"], ascending=[True, False])
        )
        stats["by_split_split_combo"] = by_split_key.to_dict(orient="records")
    split_positive_stats: Dict[str, Dict[str, int]] = {}
    for col in sorted([c for c in samples.columns if c.endswith("_split_positive")]):
        actuator = col[: -len("_split_positive")]
        split_positive_stats[actuator] = {
            str(k): int(v)
            for k, v in samples.groupby("split")[col].sum().sort_index().to_dict().items()
        }
    if split_positive_stats:
        stats["split_positive_counts"] = split_positive_stats
    return stats


def _write_outputs(
    *,
    samples: pd.DataFrame,
    out_dataset_root: Path,
    args: argparse.Namespace,
    site: str,
    missing_mels: int,
    embedding_npz: Optional[Path],
    embedding_joined: Optional[Path],
    plc_pca_targets_path: Optional[Path],
    plc_pca_model_path: Optional[Path],
    plc_pca_meta_path: Optional[Path],
) -> None:
    out_dataset_root.mkdir(parents=True, exist_ok=True)
    samples_path = out_dataset_root / "samples.parquet"
    split_manifest_path = out_dataset_root / "split_manifest.parquet"
    stats_path = out_dataset_root / "combo_stats.json"
    report_path = out_dataset_root / "build_report.json"

    samples.to_parquet(samples_path, index=False)

    split_cols = [
        "sample_id",
        "site",
        "audio_source",
        "camera",
        "day_utc",
        "segment_start_ts_utc",
        "segment_end_ts_utc",
        "actuation_combo",
        "actuation_bits",
        "split_actuators",
        "split_actuation_combo",
        "split_actuation_bits",
        "event_window_id",
        "split_group_id",
        "split",
        "split_seed",
        "split_min_positive_count",
    ]
    split_manifest = samples[[c for c in split_cols if c in samples.columns]].copy()
    split_manifest.to_parquet(split_manifest_path, index=False)

    stats = _build_stats(samples)
    stats_path.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = {
        "site": site,
        "window_seconds": float(args.window_seconds),
        "stride_seconds": float(args.stride_seconds),
        "sample_rate": int(args.sample_rate),
        "n_samples": int(len(samples)),
        "n_missing_mels": int(missing_mels),
        "n_actuation_combos": int(samples["actuation_combo"].nunique()),
        "outputs": {
            "samples_parquet": str(samples_path),
            "split_manifest_parquet": str(split_manifest_path),
            "combo_stats_json": str(stats_path),
            "embedding_npz": (str(embedding_npz) if embedding_npz else None),
            "embedding_joined_parquet": (str(embedding_joined) if embedding_joined else None),
            "plc_pca_targets_parquet": (str(plc_pca_targets_path) if plc_pca_targets_path else None),
            "plc_pca_model_npz": (str(plc_pca_model_path) if plc_pca_model_path else None),
            "plc_pca_model_json": (str(plc_pca_meta_path) if plc_pca_meta_path else None),
        },
        "split": {
            "seed": int(args.split_seed),
            "train_ratio": float(args.train_ratio),
            "test_ratio": float(args.test_ratio),
            "val_ratio": float(args.val_ratio),
            "split_actuators": _parse_csv_list(str(args.split_actuators)),
            "min_positive_count": int(args.split_min_positive_count),
            "actual": {k: float(v) for k, v in samples["split"].value_counts(normalize=True).sort_index().to_dict().items()},
        },
        "actuators": list(ACTUATORS),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"[ok] wrote {samples_path} rows={len(samples)}", flush=True)
    print(f"[ok] wrote {split_manifest_path}", flush=True)
    print(f"[ok] wrote {stats_path}", flush=True)
    print(f"[ok] wrote {report_path}", flush=True)
    if embedding_npz:
        print(f"[ok] wrote {embedding_npz}", flush=True)
    if embedding_joined:
        print(f"[ok] wrote {embedding_joined}", flush=True)
    if plc_pca_targets_path:
        print(f"[ok] wrote {plc_pca_targets_path}", flush=True)
    if plc_pca_model_path:
        print(f"[ok] wrote {plc_pca_model_path}", flush=True)
    if plc_pca_meta_path:
        print(f"[ok] wrote {plc_pca_meta_path}", flush=True)


def _write_embeddings(
    *,
    samples: pd.DataFrame,
    out_dataset_root: Path,
    args: argparse.Namespace,
) -> tuple[Path, Optional[Path]]:
    out_dataset_root.mkdir(parents=True, exist_ok=True)
    emb_npz = out_dataset_root / "embeddings_panns.npz"
    emb_joined = out_dataset_root / "embeddings_joined.parquet" if bool(args.write_embeddings_joined) else None

    if bool(args.skip_existing) and emb_npz.exists():
        z = np.load(str(emb_npz))
        emb = np.asarray(z["embeddings"], dtype=np.float32)
        if emb.shape[0] != len(samples):
            raise SystemExit(
                f"Embedding cache row mismatch: cache_rows={emb.shape[0]} samples={len(samples)} path={emb_npz}"
            )
        print(f"[embed] cache hit -> {emb_npz} shape={tuple(emb.shape)}", flush=True)
    else:
        backend = _PannsBackend(device=str(args.embedding_device))
        emb = _extract_embeddings(
            backend=backend,
            paths=samples["segment_path"].astype(str).tolist(),
            batch_size=int(args.embedding_batch_size),
            target_seconds=float(args.embedding_target_seconds),
            num_workers=int(args.embedding_num_workers),
            log_every=int(args.embedding_log_every),
        )
        np.savez_compressed(str(emb_npz), embeddings=emb)
        print(f"[embed] saved -> {emb_npz} shape={tuple(emb.shape)}", flush=True)

    if emb_joined is not None:
        if not (bool(args.skip_existing) and emb_joined.exists()):
            joined = samples[
                [c for c in ("sample_id", "split", "actuation_combo", "actuation_bits", "audio_source", "segment_path") if c in samples.columns]
            ].copy()
            for j in range(emb.shape[1]):
                joined[f"embedding_{j:04d}"] = emb[:, j].astype(np.float32)
            joined.to_parquet(emb_joined, index=False)
    return emb_npz, emb_joined


def _json_ready_feature_ranges(feature_ranges: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for col, node in feature_ranges.items():
        out_node: Dict[str, Any] = {}
        for key, value in node.items():
            if isinstance(value, np.generic):
                out_node[str(key)] = value.item()
            else:
                out_node[str(key)] = value
        out[str(col)] = out_node
    return out


def _fit_and_write_plc_pca(
    *,
    samples: pd.DataFrame,
    out_dataset_root: Path,
    args: argparse.Namespace,
) -> tuple[pd.DataFrame, Optional[Path], Optional[Path], Optional[Path]]:
    if not bool(args.write_plc_pca):
        return samples, None, None, None
    out_dataset_root.mkdir(parents=True, exist_ok=True)

    explicit_cols = [c.strip() for c in str(args.plc_pca_cols).split(",") if c.strip()] or None
    always_exclude = [
        "sample_id",
        "site",
        "audio_source",
        "camera",
        "day_utc",
        "segment_path",
        "segment_start_ts_utc",
        "segment_end_ts_utc",
        "mel_shard_path",
        "mel_local_path",
        "mel_shard_local_index",
        "event_window_id",
        "split_group_id",
        "split",
        "split_seed",
        "actuation_combo",
        "actuation_bits",
        "actuation_unknown",
        "has_mel",
        "window_seconds",
        "n_rows",
    ] + [f"{a}_state" for a in ACTUATORS] + [f"{a}_duty_target" for a in ACTUATORS]

    cols = select_pca_columns(
        samples,
        explicit_cols=explicit_cols,
        include_regex=list(args.plc_pca_include_regex or []),
        exclude_regex=list(args.plc_pca_exclude_regex or []),
        always_exclude=always_exclude,
    )
    if not cols:
        raise SystemExit("No PLC PCA columns selected for actuation dataset. Set --plc-pca-cols or broaden include regex.")

    fit_split = str(args.plc_pca_fit_split).strip().lower()
    if fit_split == "train" and "split" in samples.columns:
        fit_df = samples.loc[samples["split"].astype(str).str.lower() == "train"].copy()
    else:
        fit_df = samples.copy()
    if fit_df.empty:
        raise SystemExit("No rows available to fit PLC PCA")

    unknown_col = next((c for c in ("state_unknown", "state__unknown") if c in fit_df.columns), None)
    if unknown_col is not None:
        fit_df = fit_df[pd.to_numeric(fit_df[unknown_col], errors="coerce").fillna(0.0) < 0.5].copy()
        if fit_df.empty:
            raise SystemExit(f"All fit rows removed by PLC PCA unknown filter using column: {unknown_col}")

    bundle = fit_pca(
        fit_df,
        cols,
        n_components=int(args.plc_pca_components),
        standardize=True,
        fill_value=float(args.plc_pca_fill_value),
        clip_abs=args.plc_pca_clip_abs,
        controls_weight=float(args.plc_pca_controls_weight),
    )
    proj_df, Z = transform_pca(
        samples.copy(),
        bundle,
        fill_value=float(args.plc_pca_fill_value),
        clip_abs=args.plc_pca_clip_abs,
    )

    out = samples.copy()
    for j in range(int(Z.shape[1])):
        out[f"plc_pca{j+1}"] = Z[:, j].astype(np.float64)

    pca_targets_path = out_dataset_root / "plc_window_pca_targets.parquet"
    pca_model_path = out_dataset_root / "plc_window_pca_model.npz"
    pca_meta_path = out_dataset_root / "plc_window_pca_model.json"

    target_cols = ["sample_id", "split"] + [f"plc_pca{j+1}" for j in range(int(Z.shape[1]))]
    target_cols = [c for c in target_cols if c in out.columns]
    out[target_cols].to_parquet(pca_targets_path, index=False)

    np.savez_compressed(
        str(pca_model_path),
        cols=np.asarray(bundle.cols, dtype=object),
        scaler_mean=np.asarray(getattr(bundle.scaler, "mean_", np.zeros((len(bundle.cols),), dtype=np.float64)), dtype=np.float64),
        scaler_scale=np.asarray(getattr(bundle.scaler, "scale_", np.ones((len(bundle.cols),), dtype=np.float64)), dtype=np.float64),
        components=np.asarray(bundle.pca.components_, dtype=np.float64),
        explained_variance=np.asarray(bundle.pca.explained_variance_, dtype=np.float64),
        explained_variance_ratio=np.asarray(bundle.pca.explained_variance_ratio_, dtype=np.float64),
        singular_values=np.asarray(getattr(bundle.pca, "singular_values_", np.asarray([], dtype=np.float64)), dtype=np.float64),
        control_mask=np.asarray(bundle.control_mask, dtype=bool),
        controls_weight=np.asarray([bundle.controls_weight], dtype=np.float64),
        controls_regex=np.asarray(bundle.controls_regex, dtype=object),
        fit_split=np.asarray([fit_split], dtype=object),
        fill_value=np.asarray([float(args.plc_pca_fill_value)], dtype=np.float64),
        clip_abs=np.asarray(
            [np.nan if args.plc_pca_clip_abs is None else float(args.plc_pca_clip_abs)],
            dtype=np.float64,
        ),
    )

    meta = {
        "cols": list(bundle.cols),
        "n_cols": int(len(bundle.cols)),
        "n_components": int(bundle.pca.n_components_),
        "controls_weight": float(bundle.controls_weight),
        "controls_regex": list(bundle.controls_regex),
        "fit_split": fit_split,
        "fill_value": float(args.plc_pca_fill_value),
        "clip_abs": (None if args.plc_pca_clip_abs is None else float(args.plc_pca_clip_abs)),
        "explained_variance_ratio": [float(x) for x in np.asarray(bundle.pca.explained_variance_ratio_, dtype=np.float64).tolist()],
        "feature_ranges": _json_ready_feature_ranges(bundle.feature_ranges),
        "target_parquet": str(pca_targets_path),
        "model_npz": str(pca_model_path),
    }
    pca_meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[ok] wrote {pca_targets_path}", flush=True)
    print(f"[ok] wrote {pca_model_path}", flush=True)
    print(f"[ok] wrote {pca_meta_path}", flush=True)
    return out, pca_targets_path, pca_model_path, pca_meta_path


def main() -> None:
    args = parse_args()
    site = str(args.site).strip().lower()
    paths = _resolve_paths(args)

    if abs(float(args.train_ratio) + float(args.test_ratio) + float(args.val_ratio) - 1.0) > 1e-6:
        raise SystemExit("--train-ratio + --test-ratio + --val-ratio must equal 1.0")

    include_rpi = bool(args.include_rpi)
    include_wyze = bool(args.include_wyze)
    if not include_rpi and not include_wyze:
        include_rpi = True
        include_wyze = True

    date_filter = set(args.date) if args.date else None
    camera_filter = set(args.wyze_camera) if args.wyze_camera else None
    repo_root = Path(__file__).resolve().parents[2]
    out_root = paths["out_root"]
    out_dataset_root = out_root / "dataset=audio_actuation_dataset" / f"site={site}" / f"window_s={int(args.window_seconds)}"

    MelSegmentsConfig, generate_mel_segments = _import_ml_audio_mel()
    generate_window_features_for_intervals_df = _import_window_features_pipeline()

    source_days = []
    if include_rpi:
        source_days.extend(
            _build_rpi_stage(
                site=site,
                rpi_root=paths["rpi_root"],
                out_root=out_root,
                date_filter=date_filter,
                dry_run=bool(args.dry_run),
            )
        )
    if include_wyze:
        source_days.extend(
            _build_wyze_stage(
                repo_root=repo_root,
                site=site,
                wyze_root=paths["wyze_root"],
                out_root=out_root,
                sample_rate=int(args.sample_rate),
                min_size_bytes=int(args.wyze_min_size_bytes),
                date_filter=date_filter,
                camera_filter=camera_filter,
                skip_existing=bool(args.skip_existing),
                skip_conversion=bool(args.skip_wyze_conversion),
                convert_workers=int(args.wyze_convert_workers),
                dry_run=bool(args.dry_run),
            )
        )

    if not source_days:
        raise SystemExit("No source/day inputs found.")

    seg_rows: List[pd.DataFrame] = []
    for sd in sorted(source_days, key=lambda x: (x.audio_source, x.day)):
        seg_manifest = _segment_source_day(
            repo_root=repo_root,
            sd=sd,
            out_root=out_root,
            site=site,
            window_seconds=float(args.window_seconds),
            stride_seconds=float(args.stride_seconds),
            skip_existing=bool(args.skip_existing),
            dry_run=bool(args.dry_run),
        )
        if args.dry_run:
            continue
        if not seg_manifest.exists():
            print(f"[skip] segment manifest missing: {seg_manifest}", flush=True)
            continue
        seg_df = pd.read_parquet(seg_manifest)
        if seg_df.empty:
            continue
        seg_df["site"] = sd.site
        seg_df["audio_source"] = _canonical_audio_source(sd.site, sd.audio_source, sd.camera)
        seg_df["camera"] = sd.camera
        seg_df["camera_canonical"] = _canonical_wyze_camera(sd.site, sd.camera)
        seg_df["day_utc"] = sd.day
        seg_rows.append(seg_df)

    if args.dry_run:
        print("[done] dry-run complete", flush=True)
        return
    if not seg_rows:
        raise SystemExit("No segments produced.")

    segments_df = pd.concat(seg_rows, ignore_index=True)
    segments_df["segment_start_ts_utc"] = pd.to_datetime(segments_df["segment_start_ts_utc"], utc=True, errors="coerce")
    segments_df["segment_end_ts_utc"] = pd.to_datetime(segments_df["segment_end_ts_utc"], utc=True, errors="coerce")
    segments_df = segments_df[segments_df["segment_start_ts_utc"].notna() & segments_df["segment_end_ts_utc"].notna()].copy()
    segments_df = segments_df.sort_values(["audio_source", "segment_start_ts_utc", "segment_path"]).reset_index(drop=True)
    segments_df["sample_id"] = [
        hashlib.sha1(f"{r.audio_source}|{r.segment_path}|{r.segment_start_ts_utc}|{r.segment_end_ts_utc}".encode("utf-8")).hexdigest()
        for r in segments_df.itertuples(index=False)
    ]

    mel_input_manifest = out_root / "intermediate" / "segments" / f"site={site}" / "segments_all.parquet"
    mel_input_manifest.parent.mkdir(parents=True, exist_ok=True)
    segments_df.to_parquet(mel_input_manifest, index=False)

    mel_out = out_root / "intermediate" / "mels" / f"site={site}" / f"window_s={int(args.window_seconds)}"
    mel_manifest = mel_out / "audio_mel_segments.parquet"
    if not (args.skip_existing and mel_manifest.exists()):
        cfg = MelSegmentsConfig(
            segments_root=out_root,
            segments_manifest=str(mel_input_manifest),
            out_dir=mel_out,
            site=site,
            sample_rate=int(args.sample_rate),
            target_seconds=float(args.window_seconds),
            shard_size=int(args.mel_shard_size),
            partition_by="utc_day",
            skip_existing_shards=bool(args.skip_existing),
            n_fft=int(args.mel_n_fft),
            win_length=int(args.mel_win_length),
            hop_length=int(args.mel_hop_length),
            n_mels=int(args.mel_n_mels),
            fmin=float(args.mel_fmin),
            fmax=float(args.mel_fmax),
            power=float(args.mel_power),
            log_eps=float(args.mel_log_eps),
            mel_normalization=str(args.mel_normalization),
            dtype=str(args.mel_dtype),
        )
        generate_mel_segments(cfg)
    if not mel_manifest.exists():
        raise SystemExit(f"Mel manifest missing: {mel_manifest}")

    mel_df = pd.read_parquet(mel_manifest)
    mel_df["segment_start_ts_utc"] = pd.to_datetime(mel_df["segment_start_ts_utc"], utc=True, errors="coerce")
    mel_df["segment_end_ts_utc"] = pd.to_datetime(mel_df["segment_end_ts_utc"], utc=True, errors="coerce")

    merged = segments_df.merge(
        mel_df[
            [
                "segment_path",
                "segment_start_ts_utc",
                "segment_end_ts_utc",
                "mel_shard_path",
                "mel_shard_relpath",
                "mel_shard_local_index",
                "mel_n_mels",
                "mel_n_frames",
                "mel_dtype",
            ]
        ],
        on=["segment_path", "segment_start_ts_utc", "segment_end_ts_utc"],
        how="left",
    )
    merged["has_mel"] = merged["mel_shard_path"].notna()
    missing_mels = int((~merged["has_mel"]).sum())
    if missing_mels > 0:
        raise SystemExit(f"Missing mel outputs for {missing_mels} segments.")

    plc_roots = [paths["plc_root"]]
    if paths["plc_fallback_root"] not in plc_roots:
        plc_roots.append(paths["plc_fallback_root"])

    out_rows: List[pd.DataFrame] = []
    for day, day_df in merged.groupby("day_utc", sort=True):
        feat_df = _window_features_for_segments(
            generate_window_features_for_intervals_df=generate_window_features_for_intervals_df,
            plc_roots=plc_roots,
            site=site,
            day=str(day),
            seg_df=day_df,
            max_gap_stale_s=float(args.max_gap_stale_s),
        )
        if feat_df is None:
            continue

        feat_df = feat_df.reset_index(drop=True)
        left = day_df.reset_index(drop=True)
        overlap_cols = set(left.columns).intersection(set(feat_df.columns))
        if overlap_cols:
            feat_df = feat_df.rename(columns={c: f"plc_{c}" for c in overlap_cols})
        joined = pd.concat([left, feat_df], axis=1)

        plc_day_df = _read_plc_day(plc_roots, site=site, day=str(day))
        if plc_day_df is None:
            continue
        labeled = _label_segments_with_plc_overlap(plc_df=plc_day_df, seg_df=joined)
        labeled = _build_actuation_labels(labeled)
        out_rows.append(labeled)

    if not out_rows:
        raise SystemExit("No rows after PLC join/labeling.")

    samples = pd.concat(out_rows, ignore_index=True)
    split_actuators = _parse_csv_list(str(args.split_actuators))
    if not split_actuators:
        raise SystemExit("--split-actuators must include at least one actuator")
    invalid_actuators = [a for a in split_actuators if a not in ACTUATORS]
    if invalid_actuators:
        raise SystemExit(f"Unknown split actuators: {', '.join(invalid_actuators)}")
    samples = _build_selected_actuation_key(samples, split_actuators)
    samples = _attach_event_windows_for_combo(
        samples,
        combo_col="actuation_combo",
        max_gap_seconds=float(args.max_event_gap_seconds),
        max_window_seconds=float(args.max_event_window_seconds),
    )
    samples = _split_assign_by_combo(
        samples,
        combo_col="split_actuation_combo",
        split_actuators=split_actuators,
        min_positive_count=int(args.split_min_positive_count),
        seed=int(args.split_seed),
        train_ratio=float(args.train_ratio),
        test_ratio=float(args.test_ratio),
        val_ratio=float(args.val_ratio),
    )

    samples, plc_pca_targets_path, plc_pca_model_path, plc_pca_meta_path = _fit_and_write_plc_pca(
        samples=samples,
        out_dataset_root=out_dataset_root,
        args=args,
    )
    embedding_npz, embedding_joined = _write_embeddings(samples=samples, out_dataset_root=out_dataset_root, args=args)
    _write_outputs(
        samples=samples,
        out_dataset_root=out_dataset_root,
        args=args,
        site=site,
        missing_mels=missing_mels,
        embedding_npz=embedding_npz,
        embedding_joined=embedding_joined,
        plc_pca_targets_path=plc_pca_targets_path,
        plc_pca_model_path=plc_pca_model_path,
        plc_pca_meta_path=plc_pca_meta_path,
    )


if __name__ == "__main__":
    main()
