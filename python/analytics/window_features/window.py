from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .io import day_to_range_utc
from .specs import ColumnGroups


def _time_weighted_mean_step_hold(ts_sec: np.ndarray, x: np.ndarray, w1: float) -> float:
    if len(ts_sec) == 0:
        return np.nan
    t = ts_sec.astype("float64")
    t_next = np.empty_like(t)
    t_next[:-1] = t[1:]
    t_next[-1] = w1
    dt_seg = np.maximum(0.0, t_next - t)
    total = float(dt_seg.sum())
    if total <= 0:
        return float(x[-1]) if len(x) else np.nan
    return float((dt_seg * x).sum() / total)


def _duty_and_transitions_step_hold(
    ts_sec: np.ndarray, state: np.ndarray, w1: float
) -> Tuple[float, int]:
    """
    Treat "on" as state != 0. Time-weighted duty over the window, plus number of on/off flips.
    """
    if len(ts_sec) == 0:
        return (np.nan, 0)

    s = np.where(np.isnan(state), 0.0, state)
    s_on = (s != 0.0).astype(np.float64)
    transitions = int(np.sum(s_on[1:] != s_on[:-1])) if len(s_on) >= 2 else 0

    t = ts_sec.astype("float64")
    t_next = np.empty_like(t)
    t_next[:-1] = t[1:]
    t_next[-1] = w1
    dt_seg = np.maximum(0.0, t_next - t)
    total = float(dt_seg.sum())
    if total <= 0:
        return (float(s_on[-1]), transitions)

    duty = float((dt_seg * s_on).sum() / total)
    return (duty, transitions)


def _tw_mode_step_hold(ts_sec: np.ndarray, x: np.ndarray, w1: float) -> Tuple[float, int]:
    """
    Time-weighted mode (dominant value under step-hold) + transitions count (value changes).
    Returns (mode_value, transitions).
    """
    if len(ts_sec) == 0:
        return (np.nan, 0)

    transitions = int(np.sum(x[1:] != x[:-1])) if len(x) >= 2 else 0

    t = ts_sec.astype("float64")
    t_next = np.empty_like(t)
    t_next[:-1] = t[1:]
    t_next[-1] = w1
    dt_seg = np.maximum(0.0, t_next - t)

    acc: Dict[float, float] = {}
    for v, dtv in zip(x, dt_seg):
        if not np.isfinite(v):
            continue
        vv = float(v)
        acc[vv] = acc.get(vv, 0.0) + float(max(0.0, dtv))

    if not acc:
        finite = x[np.isfinite(x)]
        return (float(finite[-1]) if len(finite) else np.nan, transitions)

    mode_val = max(acc.items(), key=lambda kv: kv[1])[0]
    return (float(mode_val), transitions)


def _transition_times_step_hold(
    ts_sec: np.ndarray,
    x: np.ndarray,
    *,
    boolean_mode: bool = False,
) -> np.ndarray:
    """
    Return timestamps where the signal transitions to a new value.
    Transition time is the timestamp of the new value sample.
    """
    if len(ts_sec) < 2:
        return np.empty((0,), dtype="float64")

    if boolean_mode:
        xv = np.where(np.isfinite(x), x, 0.0)
        s = (xv != 0.0).astype(np.int8)
    else:
        good = np.isfinite(x)
        if not np.any(good):
            return np.empty((0,), dtype="float64")
        s = x.copy()
        if not np.all(good):
            # Carry forward finite values over NaNs so missing samples don't look like transitions.
            idx = np.where(good, np.arange(len(s)), 0)
            np.maximum.accumulate(idx, out=idx)
            s = s[idx]

    trans_idx = np.nonzero(s[1:] != s[:-1])[0] + 1
    if len(trans_idx) == 0:
        return np.empty((0,), dtype="float64")
    return ts_sec[trans_idx].astype("float64", copy=False)


def _seconds_since_last_transition(
    transition_ts_sec: np.ndarray,
    t_sec: float,
) -> float:
    if transition_ts_sec.size == 0 or not np.isfinite(t_sec):
        return np.nan
    j = int(np.searchsorted(transition_ts_sec, t_sec, side="right") - 1)
    if j < 0:
        return np.nan
    dt = float(t_sec - float(transition_ts_sec[j]))
    return dt if dt >= 0 else np.nan


def _window_start_for_ts(
    ts: pd.Series, *, day_start: pd.Timestamp, window: pd.Timedelta
) -> pd.Series:
    """
    Map each timestamp to the start of its fixed-length window anchored at day_start.

    This avoids pandas .dt.floor() limitations for arbitrary seconds and ensures
    windows line up exactly with day_start.
    """
    ts_ns = ts.astype("int64", copy=False)
    day_ns = int(day_start.value)
    win_ns = int(window.value)
    k = (ts_ns - day_ns) // win_ns
    w0_ns = day_ns + k * win_ns
    return pd.to_datetime(w0_ns, utc=True)


def compute_window_features_for_day(
    df: pd.DataFrame,
    *,
    site: str,
    day: str,
    ts_col: str,
    groups: ColumnGroups,
    window_seconds: int = 60,
    stride_seconds: Optional[int] = None,
    max_gap_for_stale_s: float = 300.0,
) -> pd.DataFrame:
    """
    Compute fixed-length window feature vectors for one UTC day.

    - Windows are anchored at day_start (00:00:00Z).
    - Each window covers [w0, w1) of length window_seconds.
    - Windows advance by stride_seconds (default: window_seconds).
    - Within each window, we treat signals as step-hold between samples.
    """
    if window_seconds <= 0:
        raise ValueError("--window-seconds must be > 0")

    stride_seconds = window_seconds if stride_seconds is None else int(stride_seconds)
    if stride_seconds <= 0:
        raise ValueError("--stride-seconds must be > 0")

    window = pd.Timedelta(seconds=int(window_seconds))
    stride = pd.Timedelta(seconds=int(stride_seconds))

    df = df.copy()
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    df = df[df[ts_col].notna()].sort_values(ts_col)

    day_start, day_end = day_to_range_utc(day)
    df = df[(df[ts_col] >= day_start) & (df[ts_col] < day_end)].copy()

    day_span = day_end - day_start
    if day_span < window:
        window_index = pd.DatetimeIndex([day_start], tz="UTC")
    else:
        last_start = day_end - window
        window_index = pd.date_range(
            day_start, last_start, freq=stride, inclusive="both", tz="UTC"
        )

    # Precompute arrays once (avoid per-window pandas conversions)
    ts = pd.to_datetime(df[ts_col], utc=True)
    ts_ns = ts.astype("int64", copy=False).to_numpy()
    ts_sec_all = ts_ns.astype("float64") / 1e9

    col_arrays: Dict[str, np.ndarray] = {}
    for c in groups.continuous + groups.boolean + groups.discrete:
        col_arrays[c] = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype="float64", copy=False)

    transition_targets: Dict[str, Tuple[str, bool]] = {
        "state__sec_since_transition": ("state", False),
        "ropumprun__sec_since_transition": ("ropumprun", True),
        "deliveryrun__sec_since_transition": ("deliveryrun", True),
    }
    transition_times: Dict[str, np.ndarray] = {}
    for out_col, (src_col, is_bool) in transition_targets.items():
        if src_col in col_arrays:
            transition_times[out_col] = _transition_times_step_hold(
                ts_sec_all,
                col_arrays[src_col],
                boolean_mode=is_bool,
            )
        else:
            transition_times[out_col] = np.empty((0,), dtype="float64")

    # Precompute window boundaries in ns and row index ranges via searchsorted
    window_start_ns = window_index.astype("int64", copy=False).to_numpy()
    window_end_ns = (window_index + window).astype("int64", copy=False).to_numpy()
    idx_start = np.searchsorted(ts_ns, window_start_ns, side="left")
    idx_end = np.searchsorted(ts_ns, window_end_ns, side="left")

    out_rows: List[Dict[str, object]] = []
    last_event_ns: Optional[int] = None
    consecutive_empty = 0

    for i, w0 in enumerate(window_index):
        w1 = w0 + window
        i0 = int(idx_start[i])
        i1 = int(idx_end[i])

        row: Dict[str, object] = {
            "site": site,
            "day": day,
            "window_seconds": int(window_seconds),
            "stride_seconds": int(stride_seconds),
            "window_start_ts": w0,
            "window_end_ts": w1,
        }
        w1_sec = w1.value / 1e9
        for out_col, tr in transition_times.items():
            row[out_col] = _seconds_since_last_transition(tr, float(w1_sec))

        if i0 == i1:
            consecutive_empty += 1
            row["n_rows"] = 0
            row["consecutive_empty_windows"] = consecutive_empty

            w1_ns = int(w1.value)
            gap = np.inf if last_event_ns is None else float((w1_ns - last_event_ns) / 1e9)
            row["time_since_last_event_sec"] = gap
            row["state_unknown"] = int(gap > max_gap_for_stale_s)

            for c in groups.continuous:
                row[f"{c}__last"] = np.nan
                row[f"{c}__mean_tw"] = np.nan

            for b in groups.boolean:
                row[f"{b}__last"] = np.nan
                row[f"{b}__duty"] = np.nan
                row[f"{b}__transitions"] = 0

            for d in groups.discrete:
                row[f"{d}__last"] = np.nan
                row[f"{d}__mode_tw"] = np.nan
                row[f"{d}__transitions"] = 0

            out_rows.append(row)
            continue

        consecutive_empty = 0
        row["n_rows"] = int(i1 - i0)
        row["consecutive_empty_windows"] = 0

        last_event_ns = int(ts_ns[i1 - 1])
        w1_ns = int(w1.value)
        row["time_since_last_event_sec"] = float((w1_ns - last_event_ns) / 1e9)
        row["state_unknown"] = int(row["time_since_last_event_sec"] > max_gap_for_stale_s)

        ts_sec = ts_sec_all[i0:i1]
        w1_sec = w1.value / 1e9

        for c in groups.continuous:
            x = col_arrays[c][i0:i1]
            row[f"{c}__last"] = float(x[-1]) if (len(x) and np.isfinite(x[-1])) else np.nan

            good = np.isfinite(x)
            row[f"{c}__mean_tw"] = (
                _time_weighted_mean_step_hold(ts_sec[good], x[good], w1_sec) if np.any(good) else np.nan
            )

        for b in groups.boolean:
            s = col_arrays[b][i0:i1]
            row[f"{b}__last"] = float(s[-1]) if (len(s) and np.isfinite(s[-1])) else np.nan

            good = np.isfinite(s)
            if np.any(good):
                duty, trans = _duty_and_transitions_step_hold(ts_sec[good], s[good], w1_sec)
                row[f"{b}__duty"] = duty
                row[f"{b}__transitions"] = trans
            else:
                row[f"{b}__duty"] = np.nan
                row[f"{b}__transitions"] = 0

        for d in groups.discrete:
            s = col_arrays[d][i0:i1]
            row[f"{d}__last"] = float(s[-1]) if (len(s) and np.isfinite(s[-1])) else np.nan

            good = np.isfinite(s)
            if np.any(good):
                mode, trans = _tw_mode_step_hold(ts_sec[good], s[good], w1_sec)
                row[f"{d}__mode_tw"] = mode
                row[f"{d}__transitions"] = trans
            else:
                row[f"{d}__mode_tw"] = np.nan
                row[f"{d}__transitions"] = 0

        out_rows.append(row)

    return pd.DataFrame(out_rows)


def compute_window_features_for_intervals(
    df: pd.DataFrame,
    *,
    site: str,
    day: str,
    ts_col: str,
    groups: ColumnGroups,
    interval_start: pd.Series,
    interval_end: pd.Series,
    max_gap_for_stale_s: float = 300.0,
) -> pd.DataFrame:
    """
    Compute feature rows for explicit intervals [start, end) rather than an exhaustive
    fixed grid. This is useful for attaching PLC features to audio segments directly.
    """
    df = df.copy()
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    df = df[df[ts_col].notna()].sort_values(ts_col)

    day_start, day_end = day_to_range_utc(day)
    df = df[(df[ts_col] >= day_start) & (df[ts_col] < day_end)].copy()

    starts = pd.to_datetime(interval_start, utc=True, errors="coerce")
    ends = pd.to_datetime(interval_end, utc=True, errors="coerce")

    ts = pd.to_datetime(df[ts_col], utc=True)
    ts_ns = ts.astype("int64", copy=False).to_numpy()
    ts_sec_all = ts_ns.astype("float64") / 1e9

    col_arrays: Dict[str, np.ndarray] = {}
    for c in groups.continuous + groups.boolean + groups.discrete:
        col_arrays[c] = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype="float64", copy=False)

    transition_targets: Dict[str, Tuple[str, bool]] = {
        "state__sec_since_transition": ("state", False),
        "ropumprun__sec_since_transition": ("ropumprun", True),
        "deliveryrun__sec_since_transition": ("deliveryrun", True),
    }
    transition_times: Dict[str, np.ndarray] = {}
    for out_col, (src_col, is_bool) in transition_targets.items():
        if src_col in col_arrays:
            transition_times[out_col] = _transition_times_step_hold(
                ts_sec_all,
                col_arrays[src_col],
                boolean_mode=is_bool,
            )
        else:
            transition_times[out_col] = np.empty((0,), dtype="float64")

    out_rows: List[Dict[str, object]] = []
    for w0, w1 in zip(starts, ends):
        valid = pd.notna(w0) and pd.notna(w1) and (w1 > w0)
        row: Dict[str, object] = {
            "site": site,
            "day": day,
            "window_seconds": float((w1 - w0).total_seconds()) if valid else np.nan,
            "stride_seconds": np.nan,
            "window_start_ts": w0,
            "window_end_ts": w1,
            "window_match_found": int(bool(valid)),
        }
        w1_sec = float(w1.value / 1e9) if valid else np.nan
        for out_col, tr in transition_times.items():
            row[out_col] = _seconds_since_last_transition(tr, w1_sec)
        if not valid:
            row["n_rows"] = 0
            row["consecutive_empty_windows"] = 0
            row["time_since_last_event_sec"] = np.inf
            row["state_unknown"] = 1
            for c in groups.continuous:
                row[f"{c}__last"] = np.nan
                row[f"{c}__mean_tw"] = np.nan
            for b in groups.boolean:
                row[f"{b}__last"] = np.nan
                row[f"{b}__duty"] = np.nan
                row[f"{b}__transitions"] = 0
            for d in groups.discrete:
                row[f"{d}__last"] = np.nan
                row[f"{d}__mode_tw"] = np.nan
                row[f"{d}__transitions"] = 0
            out_rows.append(row)
            continue

        w0_ns = int(w0.value)
        w1_ns = int(w1.value)
        i0 = int(np.searchsorted(ts_ns, w0_ns, side="left"))
        i1 = int(np.searchsorted(ts_ns, w1_ns, side="left"))

        row["n_rows"] = int(max(0, i1 - i0))
        row["consecutive_empty_windows"] = 0

        if i1 > 0:
            last_event_ns = int(ts_ns[i1 - 1])
            row["time_since_last_event_sec"] = float((w1_ns - last_event_ns) / 1e9)
        else:
            row["time_since_last_event_sec"] = np.inf
        row["state_unknown"] = int(float(row["time_since_last_event_sec"]) > max_gap_for_stale_s)

        if i0 == i1:
            for c in groups.continuous:
                row[f"{c}__last"] = np.nan
                row[f"{c}__mean_tw"] = np.nan
            for b in groups.boolean:
                row[f"{b}__last"] = np.nan
                row[f"{b}__duty"] = np.nan
                row[f"{b}__transitions"] = 0
            for d in groups.discrete:
                row[f"{d}__last"] = np.nan
                row[f"{d}__mode_tw"] = np.nan
                row[f"{d}__transitions"] = 0
            out_rows.append(row)
            continue

        ts_sec = ts_sec_all[i0:i1]
        w1_sec = w1.value / 1e9

        for c in groups.continuous:
            x = col_arrays[c][i0:i1]
            row[f"{c}__last"] = float(x[-1]) if (len(x) and np.isfinite(x[-1])) else np.nan
            good = np.isfinite(x)
            row[f"{c}__mean_tw"] = (
                _time_weighted_mean_step_hold(ts_sec[good], x[good], w1_sec) if np.any(good) else np.nan
            )

        for b in groups.boolean:
            s = col_arrays[b][i0:i1]
            row[f"{b}__last"] = float(s[-1]) if (len(s) and np.isfinite(s[-1])) else np.nan
            good = np.isfinite(s)
            if np.any(good):
                duty, trans = _duty_and_transitions_step_hold(ts_sec[good], s[good], w1_sec)
                row[f"{b}__duty"] = duty
                row[f"{b}__transitions"] = trans
            else:
                row[f"{b}__duty"] = np.nan
                row[f"{b}__transitions"] = 0

        for d in groups.discrete:
            s = col_arrays[d][i0:i1]
            row[f"{d}__last"] = float(s[-1]) if (len(s) and np.isfinite(s[-1])) else np.nan
            good = np.isfinite(s)
            if np.any(good):
                mode, trans = _tw_mode_step_hold(ts_sec[good], s[good], w1_sec)
                row[f"{d}__mode_tw"] = mode
                row[f"{d}__transitions"] = trans
            else:
                row[f"{d}__mode_tw"] = np.nan
                row[f"{d}__transitions"] = 0

        out_rows.append(row)

    return pd.DataFrame(out_rows)


def analyze_interarrival(df: pd.DataFrame, ts_col: str):
    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce").dropna()
    ts = ts.sort_values()

    dt_s = ts.diff().dt.total_seconds().dropna()

    if len(dt_s) == 0:
        stats = {
            "n_rows": int(len(ts)),
            "mean_gap_s": np.nan,
            "median_gap_s": np.nan,
            "p90_gap_s": np.nan,
            "p95_gap_s": np.nan,
            "p99_gap_s": np.nan,
            "max_gap_s": np.nan,
        }
        print("=== Inter-arrival time statistics (seconds) ===")
        for k, v in stats.items():
            if isinstance(v, (int, np.integer)):
                print(f"{k:>15}: {int(v):8d}")
            else:
                vv = float(v) if v is not None else np.nan
                txt = "nan" if not np.isfinite(vv) else f"{vv:8.3f}"
                print(f"{k:>15}: {txt}")
        return dt_s, stats

    stats = {
        "n_rows": int(len(ts)),
        "mean_gap_s": float(dt_s.mean()),
        "median_gap_s": float(dt_s.median()),
        "p90_gap_s": float(np.percentile(dt_s, 90)),
        "p95_gap_s": float(np.percentile(dt_s, 95)),
        "p99_gap_s": float(np.percentile(dt_s, 99)),
        "max_gap_s": float(dt_s.max()),
    }

    print("=== Inter-arrival time statistics (seconds) ===")
    for k, v in stats.items():
        print(f"{k:>15}: {v:8.3f}")

    return dt_s, stats
