from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


ROPUMPRUN_STATE_TO_CODE = {
    "off": 0,
    "on": 1,
    "transition_on": 2,
    "transition_off": 3,
}


def _safe_signal_prefix(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]+", "_", str(name).strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "state"


@dataclass(frozen=True)
class AudioPLCSource:
    camera: str
    mel_manifest: Path
    plc_rows: Path
    site: Optional[str] = None
    plc_col: str = "ropumprun"
    timestamp_col: Optional[str] = None


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported table format: {path}")


def _resolve_path(p: str, base: Path) -> str:
    path = Path(str(p))
    if path.is_absolute():
        return str(path)
    # Keep repo-relative/local paths as-is when they already resolve from cwd.
    if path.exists():
        return str(path.resolve())
    return str((base / path).resolve())


def _normalize_mel_manifest(df: pd.DataFrame, manifest_path: Path, camera: str, site: Optional[str]) -> pd.DataFrame:
    out = df.copy()
    required = {"segment_start_ts_utc", "segment_end_ts_utc", "mel_shard_path", "mel_shard_local_index"}
    missing = required - set(out.columns)
    if missing:
        raise ValueError(f"Mel manifest missing columns {sorted(missing)}: {manifest_path}")

    out["segment_start_ts_utc"] = pd.to_datetime(out["segment_start_ts_utc"], utc=True, errors="coerce")
    out["segment_end_ts_utc"] = pd.to_datetime(out["segment_end_ts_utc"], utc=True, errors="coerce")
    out = out[out["segment_start_ts_utc"].notna() & out["segment_end_ts_utc"].notna()].copy()
    if "mel_saved" in out.columns:
        out = out[out["mel_saved"] != False].copy()  # noqa: E712
    out["mel_shard_path"] = out["mel_shard_path"].map(lambda x: _resolve_path(str(x), manifest_path.parent))
    out["mel_shard_local_index"] = pd.to_numeric(out["mel_shard_local_index"], errors="coerce").astype("Int64")
    out = out[out["mel_shard_local_index"].notna()].copy()
    out["mel_shard_local_index"] = out["mel_shard_local_index"].astype(int)
    out["camera"] = str(camera)
    if site:
        out["site"] = str(site).strip().lower()
    elif "site" in out.columns:
        out["site"] = out["site"].astype(str).str.strip().str.lower()
    else:
        out["site"] = ""
    out = out.reset_index(drop=True)
    out["segment_row_id"] = np.arange(len(out), dtype=np.int64)
    return out


def _choose_timestamp_col(df: pd.DataFrame, preferred: Optional[str]) -> str:
    if preferred and preferred in df.columns:
        return preferred
    for c in ("plc_ts", "plctime", "timestamp", "ts"):
        if c in df.columns:
            return c
    raise ValueError("No PLC timestamp column found. Tried plc_ts/plctime/timestamp/ts.")


def _coerce_plc_bool_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.astype("Int8")
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().any():
        out = np.where(num > 0, 1, 0).astype("float64")
        out[np.isnan(num.to_numpy(dtype="float64", copy=False))] = np.nan
        return pd.Series(out, index=s.index)
    sm = s.astype(str).str.strip().str.lower()
    mapping = {
        "true": 1,
        "false": 0,
        "on": 1,
        "off": 0,
        "run": 1,
        "stop": 0,
        "1": 1,
        "0": 0,
    }
    return sm.map(mapping)


def _normalize_plc_rows(df: pd.DataFrame, *, plc_col: str, timestamp_col: Optional[str]) -> Tuple[pd.DataFrame, str]:
    out = df.copy()
    ts_col = _choose_timestamp_col(out, timestamp_col)
    if plc_col not in out.columns:
        # try case-insensitive match
        match = {str(c).lower(): c for c in out.columns}
        if plc_col.lower() in match:
            plc_col = str(match[plc_col.lower()])
        else:
            raise ValueError(f"PLC rows missing column: {plc_col}")
    out["__plc_ts"] = pd.to_datetime(out[ts_col], utc=True, errors="coerce")
    out["__ropumprun"] = _coerce_plc_bool_series(out[plc_col])
    out = out[out["__plc_ts"].notna()].copy()
    out = out.sort_values("__plc_ts", kind="mergesort").reset_index(drop=True)
    return out, ts_col


def _label_segment_states(
    seg_df: pd.DataFrame,
    plc_df: pd.DataFrame,
) -> pd.DataFrame:
    # Reset index to avoid pandas alignment issues when assigning label arrays
    # back into sliced DataFrames.
    out = seg_df.copy().reset_index(drop=True)
    if plc_df.empty:
        out["ropumprun_label"] = pd.NA
        out["ropumprun_label_code"] = pd.NA
        out["ropumprun_last_value"] = pd.NA
        out["ropumprun_plc_rows_in_window"] = 0
        out["ropumprun_transition_count"] = 0
        out["ropumprun_label_source"] = "no_plc"
        return out

    plc_ts = plc_df["__plc_ts"].astype("int64").to_numpy()
    plc_val = pd.to_numeric(plc_df["__ropumprun"], errors="coerce").to_numpy(dtype="float64")

    labels: List[Optional[str]] = []
    label_codes: List[Optional[int]] = []
    last_vals: List[Optional[int]] = []
    n_in_window: List[int] = []
    n_transitions: List[int] = []
    sources: List[str] = []

    for row in out.itertuples(index=False):
        s_ns = int(row.segment_start_ts_utc.value)
        e_ns = int(row.segment_end_ts_utc.value)
        i0 = int(np.searchsorted(plc_ts, s_ns, side="left"))
        i1 = int(np.searchsorted(plc_ts, e_ns, side="right"))
        n = max(0, i1 - i0)
        n_in_window.append(int(n))

        # Detect edges whose new state timestamp lands inside the segment.
        edge_labels: List[str] = []
        for j in range(max(1, i0), min(len(plc_ts), i1 + 1)):
            prev_v = plc_val[j - 1]
            curr_v = plc_val[j]
            if not np.isfinite(prev_v) or not np.isfinite(curr_v):
                continue
            if int(prev_v) == int(curr_v):
                continue
            t_ns = int(plc_ts[j])
            if s_ns <= t_ns <= e_ns:
                if int(prev_v) == 0 and int(curr_v) == 1:
                    edge_labels.append("transition_on")
                elif int(prev_v) == 1 and int(curr_v) == 0:
                    edge_labels.append("transition_off")

        label: Optional[str] = None
        last_value: Optional[int] = None
        source = "none"
        if edge_labels:
            label = edge_labels[-1]
            source = "edge_in_window"
            if i1 - 1 >= i0 and i1 - 1 < len(plc_val) and np.isfinite(plc_val[i1 - 1]):
                last_value = int(plc_val[i1 - 1])
            elif i0 - 1 >= 0 and np.isfinite(plc_val[i0 - 1]):
                last_value = int(plc_val[i0 - 1])
        else:
            value: Optional[int] = None
            if n > 0:
                window_vals = plc_val[i0:i1]
                finite = window_vals[np.isfinite(window_vals)]
                if finite.size > 0:
                    value = int(finite[-1])
                    source = "last_in_window"
            if value is None and i0 - 1 >= 0 and np.isfinite(plc_val[i0 - 1]):
                value = int(plc_val[i0 - 1])
                source = "nearest_prior"
            if value is None and i0 < len(plc_val) and np.isfinite(plc_val[i0]):
                value = int(plc_val[i0])
                source = "nearest_future"
            if value is not None:
                label = "on" if value == 1 else "off"
                last_value = int(value)

        last_vals.append(last_value)

        n_transitions.append(int(len(edge_labels)))
        labels.append(label)
        label_codes.append(ROPUMPRUN_STATE_TO_CODE.get(label) if label is not None else None)
        sources.append(source)

    out["ropumprun_label"] = pd.Series(labels, dtype="object")
    out["ropumprun_label_code"] = pd.Series(label_codes, dtype="Int64")
    out["ropumprun_last_value"] = pd.Series(last_vals, dtype="Int64")
    out["ropumprun_is_on"] = (out["ropumprun_label"] == "on").astype("int8")
    out.loc[out["ropumprun_label"].isna(), "ropumprun_is_on"] = pd.NA
    out["ropumprun_is_on"] = out["ropumprun_is_on"].astype("Int64")
    out["ropumprun_plc_rows_in_window"] = np.asarray(n_in_window, dtype=np.int64)
    out["ropumprun_transition_count"] = np.asarray(n_transitions, dtype=np.int64)
    out["ropumprun_label_source"] = pd.Series(sources, dtype="object")
    return out


def build_labeled_audio_plc_dataset(
    sources: Sequence[AudioPLCSource],
    out_parquet: Path,
    *,
    out_meta: Optional[Path] = None,
) -> Tuple[Path, Path]:
    rows: List[pd.DataFrame] = []
    source_meta: List[Dict[str, Any]] = []

    for src in sources:
        mel_df = _read_table(src.mel_manifest)
        mel_df = _normalize_mel_manifest(mel_df, src.mel_manifest, camera=src.camera, site=src.site)

        plc_df = _read_table(src.plc_rows)
        plc_df, ts_col = _normalize_plc_rows(plc_df, plc_col=src.plc_col, timestamp_col=src.timestamp_col)

        labeled = _label_segment_states(mel_df, plc_df)
        signal_prefix = _safe_signal_prefix(src.plc_col)

        # Generic aliases for downstream training code and future non-ropumprun tasks.
        alias_map = {
            "state_label": "ropumprun_label",
            "state_label_code": "ropumprun_label_code",
            "state_last_value": "ropumprun_last_value",
            "state_is_on": "ropumprun_is_on",
            "state_plc_rows_in_window": "ropumprun_plc_rows_in_window",
            "state_transition_count": "ropumprun_transition_count",
            "state_label_source": "ropumprun_label_source",
        }
        for out_col, src_col in alias_map.items():
            labeled[out_col] = labeled[src_col]

        # Signal-specific aliases (e.g., deliveryrun_label) so the target column names
        # match the PLC signal actually used to create labels.
        signal_alias_map = {
            f"{signal_prefix}_label": "ropumprun_label",
            f"{signal_prefix}_label_code": "ropumprun_label_code",
            f"{signal_prefix}_last_value": "ropumprun_last_value",
            f"{signal_prefix}_is_on": "ropumprun_is_on",
            f"{signal_prefix}_plc_rows_in_window": "ropumprun_plc_rows_in_window",
            f"{signal_prefix}_transition_count": "ropumprun_transition_count",
            f"{signal_prefix}_label_source": "ropumprun_label_source",
        }
        for out_col, src_col in signal_alias_map.items():
            labeled[out_col] = labeled[src_col]

        labeled["state_signal_col"] = str(src.plc_col)
        labeled["state_signal_prefix"] = signal_prefix
        labeled["plc_timestamp_col_used"] = ts_col
        labeled["plc_label_col_used"] = src.plc_col
        labeled["source_mel_manifest"] = str(src.mel_manifest)
        labeled["source_plc_rows"] = str(src.plc_rows)
        rows.append(labeled)

        source_meta.append(
            {
                "camera": src.camera,
                "site": src.site,
                "mel_manifest": str(src.mel_manifest),
                "plc_rows": str(src.plc_rows),
                "plc_col": src.plc_col,
                "signal_prefix": signal_prefix,
                "target_cols": {
                    "generic_label": "state_label",
                    "generic_binary": "state_is_on",
                    "signal_label": f"{signal_prefix}_label",
                    "signal_binary": f"{signal_prefix}_is_on",
                },
                "plc_timestamp_col_used": ts_col,
                "n_segments": int(len(labeled)),
                "n_labeled": int(labeled["ropumprun_label"].notna().sum()),
                "state_counts": {
                    str(k): int(v)
                    for k, v in labeled["ropumprun_label"].fillna("NA").value_counts(dropna=False).to_dict().items()
                },
            }
        )

    if not rows:
        raise ValueError("No sources provided.")
    out_df = pd.concat(rows, axis=0, ignore_index=True, sort=False)
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(out_parquet, index=False)

    if out_meta is None:
        out_meta = out_parquet.with_name(out_parquet.stem + "_metadata.json")

    meta = {
        "dataset": "audio_mel_plc_labels",
        "label_col": "state_label",
        "label_code_col": "state_label_code",
        "binary_target_col": "state_is_on",
        "compat_legacy_label_col": "ropumprun_label",
        "compat_legacy_binary_target_col": "ropumprun_is_on",
        "state_code_map": ROPUMPRUN_STATE_TO_CODE,
        "n_rows": int(len(out_df)),
        "n_labeled": int(out_df["ropumprun_label"].notna().sum()),
        "state_counts": {
            str(k): int(v)
            for k, v in out_df["ropumprun_label"].fillna("NA").value_counts(dropna=False).to_dict().items()
        },
        "cameras": sorted({str(x) for x in out_df.get("camera", pd.Series(dtype=str)).dropna().astype(str).tolist()}),
        "sources": source_meta,
    }
    out_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_parquet, out_meta
