from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

DEFAULT_MONOTONIC_EXCLUDE_REGEX = [
    r"^total",                 # totalizers/counters
    r"^daily",                 # daily totals
    r"^powermeter__(?!d1$)",   # exclude powermeter__* except powermeter__d1
    r"__last$",                # last-sample features (often noisier)
]

DEFAULT_INCLUDE_REGEX = [
    r"__mean_tw$",
    r"__d1$",
    r"__duty$",
    r"__mode_tw$",
    r"__transitions$",
    r"^state_unknown$",
]

DEFAULT_CONTROL_REGEX = [
    r"__duty$",
    r"__transitions$",
    r"^(state__|warnword|alarmword)",
]


def read_lines_file(path: Optional[str]) -> List[str]:
    if not path:
        return []
    p = Path(path)
    lines = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def compile_regexes(patterns: Sequence[str]) -> List[re.Pattern]:
    return [re.compile(p) for p in patterns]


def match_any(name: str, regs: Sequence[re.Pattern]) -> bool:
    return any(r.search(name) for r in regs)


def select_pca_columns(
    df: pd.DataFrame,
    *,
    explicit_cols: Optional[List[str]] = None,
    include_regex: Optional[List[str]] = None,
    exclude_regex: Optional[List[str]] = None,
    include_cols_file: Optional[str] = None,
    exclude_cols_file: Optional[str] = None,
    always_exclude: Optional[List[str]] = None,
) -> List[str]:
    cols = list(df.columns)

    incl_file = read_lines_file(include_cols_file)
    excl_file = read_lines_file(exclude_cols_file)

    include_regex = include_regex or []
    exclude_regex = exclude_regex or []

    if explicit_cols and len(explicit_cols) > 0:
        chosen = [c for c in explicit_cols if c in cols]
    else:
        incl = (include_regex[:] if include_regex else DEFAULT_INCLUDE_REGEX[:]) + incl_file
        incl_regs = compile_regexes(incl)
        chosen = [c for c in cols if match_any(c, incl_regs)]

    excl = DEFAULT_MONOTONIC_EXCLUDE_REGEX[:] + exclude_regex + excl_file
    excl_regs = compile_regexes(excl)
    chosen = [c for c in chosen if not match_any(c, excl_regs)]

    if always_exclude:
        bad = set(always_exclude)
        chosen = [c for c in chosen if c not in bad]

    seen = set()
    out: List[str] = []
    for c in chosen:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        xf = float(x)
        if not np.isfinite(xf):
            return None
        return xf
    except Exception:
        return None


def compute_feature_ranges(
    df: pd.DataFrame,
    cols: List[str],
    *,
    q_lo: float = 0.01,
    q_hi: float = 0.99,
) -> Dict[str, Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}
    if len(cols) == 0:
        return stats

    for c in cols:
        if c not in df.columns:
            stats[c] = {
                "present": False,
                "n_total": int(len(df)),
                "n_finite": 0,
                "n_nonfinite": int(len(df)),
            }
            continue

        s = pd.to_numeric(df[c], errors="coerce")
        arr = s.to_numpy(dtype="float64", copy=False)

        finite = np.isfinite(arr)
        n_total = int(arr.size)
        n_finite = int(np.sum(finite))
        n_nonfinite = int(n_total - n_finite)

        if n_finite == 0:
            stats[c] = {
                "present": True,
                "n_total": n_total,
                "n_finite": 0,
                "n_nonfinite": n_nonfinite,
            }
            continue

        a = arr[finite]
        qlo = float(np.quantile(a, q_lo))
        qhi = float(np.quantile(a, q_hi))
        mn = float(np.min(a))
        mx = float(np.max(a))
        mean = float(np.mean(a))
        std = float(np.std(a))
        med = float(np.median(a))

        stats[c] = {
            "present": True,
            "n_total": n_total,
            "n_finite": n_finite,
            "n_nonfinite": n_nonfinite,
            "min": mn,
            "max": mx,
            f"p{int(q_lo*100):02d}": qlo,
            "median": med,
            f"p{int(q_hi*100):02d}": qhi,
            "mean": mean,
            "std": std,
        }

    return stats
