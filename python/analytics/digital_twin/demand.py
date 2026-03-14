from __future__ import annotations

import math
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from .types import DemandConfig


_PROFILE_CACHE: Dict[str, np.ndarray] = {}
_HARMONIC_CACHE: Dict[str, Dict] = {}


def _load_profile(path: str) -> Optional[np.ndarray]:
    p = str(path or "").strip()
    if not p:
        return None
    if p in _PROFILE_CACHE:
        return _PROFILE_CACHE[p]

    fp = Path(p)
    if not fp.exists():
        return None

    df = pd.read_csv(fp)
    # Accept either index-labeled or plain matrix CSV.
    if "dow" in df.columns:
        df = df.set_index("dow")
    # Ensure rows/cols align to 7x24.
    out = np.full((7, 24), np.nan, dtype=float)
    for d in range(7):
        if d in df.index:
            row = df.loc[d]
        elif str(d) in df.index:
            row = df.loc[str(d)]
        else:
            continue
        for h in range(24):
            key = str(h)
            if key in row.index:
                out[d, h] = float(pd.to_numeric(row[key], errors="coerce"))
            elif h in row.index:
                out[d, h] = float(pd.to_numeric(row[h], errors="coerce"))
    _PROFILE_CACHE[p] = out
    return out


def _profile_demand_gpm(t_seconds: float, cfg: DemandConfig) -> Optional[float]:
    table = _load_profile(cfg.profile_csv_path)
    if table is None:
        return None

    try:
        if str(cfg.start_ts_utc or "").strip():
            t0 = pd.Timestamp(cfg.start_ts_utc)
            if t0.tzinfo is None:
                t0 = t0.tz_localize("UTC")
            else:
                t0 = t0.tz_convert("UTC")
        else:
            # Monday anchor by default if no explicit start given.
            t0 = pd.Timestamp("2026-01-05T00:00:00Z")
        t_abs = t0 + pd.to_timedelta(float(t_seconds), unit="s")
        t_local = t_abs.tz_convert(str(cfg.profile_timezone or "America/Los_Angeles"))
        dow = int(t_local.dayofweek)
        hour = int(t_local.hour)
        q = table[dow, hour]
        if np.isfinite(q):
            return max(0.0, float(q))
    except Exception:
        return None
    return None


def _load_harmonic_fit(path: str) -> Optional[Dict]:
    p = str(path or "").strip()
    if not p:
        return None
    if p in _HARMONIC_CACHE:
        return _HARMONIC_CACHE[p]
    fp = Path(p)
    if not fp.exists():
        return None
    try:
        d = json.loads(fp.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            return None
        _HARMONIC_CACHE[p] = d
        return d
    except Exception:
        return None


def _local_time_for_demand(t_seconds: float, cfg: DemandConfig, tz_name: str) -> Optional[pd.Timestamp]:
    try:
        if str(cfg.start_ts_utc or "").strip():
            t0 = pd.Timestamp(cfg.start_ts_utc)
            if t0.tzinfo is None:
                t0 = t0.tz_localize("UTC")
            else:
                t0 = t0.tz_convert("UTC")
        else:
            t0 = pd.Timestamp("2026-01-05T00:00:00Z")
        t_abs = t0 + pd.to_timedelta(float(t_seconds), unit="s")
        return t_abs.tz_convert(tz_name)
    except Exception:
        return None


def _eval_named_coeff(coeff: Dict[str, float], key: str) -> float:
    try:
        return float(coeff.get(key, 0.0))
    except Exception:
        return 0.0


def _eval_harmonic_coeffs(
    *,
    t_local: pd.Timestamp,
    coeff: Dict[str, float],
    daily_order: int,
    weekly_order: int,
    trend_order: int,
    fit_t0_local: Optional[pd.Timestamp],
) -> float:
    hour = float(t_local.hour) + (float(t_local.minute) / 60.0)
    dow = float(t_local.dayofweek) + (hour / 24.0)
    yhat = _eval_named_coeff(coeff, "bias")

    for k in range(1, int(max(0, daily_order)) + 1):
        ang = 2.0 * math.pi * float(k) * hour / 24.0
        yhat += _eval_named_coeff(coeff, f"day_sin_{k}") * math.sin(ang)
        yhat += _eval_named_coeff(coeff, f"day_cos_{k}") * math.cos(ang)

    for m in range(1, int(max(0, weekly_order)) + 1):
        ang = 2.0 * math.pi * float(m) * dow / 7.0
        yhat += _eval_named_coeff(coeff, f"week_sin_{m}") * math.sin(ang)
        yhat += _eval_named_coeff(coeff, f"week_cos_{m}") * math.cos(ang)

    if int(max(0, trend_order)) > 0:
        t_ref = fit_t0_local if fit_t0_local is not None else t_local
        t_days = (t_local - t_ref).total_seconds() / 86400.0
        for q in range(1, int(max(0, trend_order)) + 1):
            yhat += _eval_named_coeff(coeff, f"trend_pow_{q}") * float(t_days**q)

    return max(0.0, float(yhat))


def _harmonic_fit_demand_gpm(t_seconds: float, cfg: DemandConfig) -> Optional[float]:
    fit = _load_harmonic_fit(cfg.harmonic_fit_json_path)
    if fit is None:
        return None

    try:
        tz_name = str(fit.get("timezone") or cfg.profile_timezone or "America/Los_Angeles")
        t_local = _local_time_for_demand(t_seconds, cfg, tz_name)
        if t_local is None:
            return None

        daily_order = int(fit.get("daily_order", 0))
        weekly_order = int(fit.get("weekly_order", 0))
        trend_order = int(fit.get("trend_order", 0))
        fit_window_days = int(fit.get("fit_window_days", 0))

        fit_t0_local = None
        fit_t0_raw = str(fit.get("fit_t0_local", "") or "").strip()
        if fit_t0_raw:
            t0 = pd.Timestamp(fit_t0_raw)
            fit_t0_local = t0.tz_localize(tz_name) if t0.tzinfo is None else t0.tz_convert(tz_name)

        if fit_window_days > 0 and isinstance(fit.get("coefficients_by_window"), dict):
            t_ref = fit_t0_local if fit_t0_local is not None else t_local
            idx = int((t_local - t_ref).total_seconds() // (fit_window_days * 86400.0))
            coeff_by_window = fit["coefficients_by_window"]
            coeff = coeff_by_window.get(str(idx))
            if coeff is None:
                coeff = fit.get("coefficients_global_fallback")
            if isinstance(coeff, dict):
                return _eval_harmonic_coeffs(
                    t_local=t_local,
                    coeff=coeff,
                    daily_order=daily_order,
                    weekly_order=weekly_order,
                    trend_order=trend_order,
                    fit_t0_local=fit_t0_local,
                )

        coeff = fit.get("coefficients")
        if isinstance(coeff, dict):
            return _eval_harmonic_coeffs(
                t_local=t_local,
                coeff=coeff,
                daily_order=daily_order,
                weekly_order=weekly_order,
                trend_order=trend_order,
                fit_t0_local=fit_t0_local,
            )
    except Exception:
        return None
    return None


def periodic_demand_gpm(t_seconds: float, cfg: DemandConfig) -> float:
    q_fit = _harmonic_fit_demand_gpm(t_seconds, cfg)
    if q_fit is not None:
        return q_fit

    q_profile = _profile_demand_gpm(t_seconds, cfg)
    if q_profile is not None:
        return q_profile

    """Simple daily + weekly harmonic demand model."""
    day_phase_rad = 2.0 * math.pi * (cfg.day_phase_hours / 24.0)
    week_phase_rad = 2.0 * math.pi * (cfg.week_phase_days / 7.0)

    day_term = cfg.day_amp_gpm * math.sin((2.0 * math.pi * t_seconds / 86400.0) - day_phase_rad)
    week_term = cfg.week_amp_gpm * math.sin((2.0 * math.pi * t_seconds / (7.0 * 86400.0)) - week_phase_rad)

    q = cfg.base_gpm + day_term + week_term
    return max(0.0, q)
