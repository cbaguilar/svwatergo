from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .selection import DEFAULT_CONTROL_REGEX, compile_regexes, match_any, compute_feature_ranges, safe_float

try:
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler
except Exception as e:
    raise SystemExit("Missing sklearn. Install: pip install scikit-learn") from e


@dataclass
class PCAModelBundle:
    cols: List[str]
    scaler: StandardScaler
    pca: PCA
    control_mask: np.ndarray
    controls_weight: float
    controls_regex: List[str]
    feature_ranges: Dict[str, Dict[str, Any]]


def sanitize_matrix(
    X: np.ndarray,
    *,
    fill_value: float = 0.0,
    clip_abs: Optional[float] = None,
) -> np.ndarray:
    X = X.astype("float64", copy=False)
    X[~np.isfinite(X)] = np.nan
    if clip_abs is not None and clip_abs > 0:
        X = np.clip(X, -clip_abs, clip_abs)
    if np.isnan(X).any():
        X = np.where(np.isnan(X), fill_value, X)
    return X


def extract_matrix(
    df: pd.DataFrame,
    cols: List[str],
    *,
    fill_value: float = 0.0,
    clip_abs: Optional[float] = None,
) -> np.ndarray:
    tmp = df[cols].apply(pd.to_numeric, errors="coerce")
    X = tmp.to_numpy(dtype="float64", copy=False)
    return sanitize_matrix(X, fill_value=fill_value, clip_abs=clip_abs)


def build_control_mask(cols: List[str], control_regex: List[str]) -> np.ndarray:
    regs = compile_regexes(control_regex)
    mask = np.array([match_any(c, regs) for c in cols], dtype=bool)
    return mask


def apply_controls_weight(
    Xs: np.ndarray, control_mask: np.ndarray, controls_weight: float
) -> np.ndarray:
    if controls_weight == 1.0:
        return Xs
    Xw = Xs.copy()
    Xw[:, control_mask] *= float(controls_weight)
    return Xw


def fit_pca(
    df: pd.DataFrame,
    cols: List[str],
    *,
    n_components: int = 8,
    whiten: bool = False,
    standardize: bool = True,
    fill_value: float = 0.0,
    clip_abs: Optional[float] = None,
    controls_weight: float = 1.0,
    control_regex: Optional[List[str]] = None,
) -> PCAModelBundle:
    feature_ranges = compute_feature_ranges(df, cols, q_lo=0.01, q_hi=0.99)

    X = extract_matrix(df, cols, fill_value=fill_value, clip_abs=clip_abs)

    if standardize:
        scaler = StandardScaler(with_mean=True, with_std=True)
        Xs = scaler.fit_transform(X)
    else:
        scaler = StandardScaler(with_mean=False, with_std=False)
        scaler.fit(np.zeros((1, X.shape[1]), dtype="float64"))
        Xs = X

    creg = control_regex[:] if control_regex else DEFAULT_CONTROL_REGEX[:]
    control_mask = build_control_mask(cols, creg)

    Xw = apply_controls_weight(Xs, control_mask, controls_weight)

    pca = PCA(n_components=n_components, whiten=whiten, random_state=0)
    pca.fit(Xw)

    return PCAModelBundle(
        cols=cols,
        scaler=scaler,
        pca=pca,
        control_mask=control_mask,
        controls_weight=float(controls_weight),
        controls_regex=creg,
        feature_ranges=feature_ranges,
    )


def transform_pca(
    df: pd.DataFrame,
    bundle: PCAModelBundle,
    *,
    fill_value: float = 0.0,
    clip_abs: Optional[float] = None,
) -> Tuple[pd.DataFrame, np.ndarray]:
    cols = bundle.cols
    missing = [c for c in cols if c not in df.columns]
    if missing:
        for c in missing:
            df[c] = np.nan

    X = extract_matrix(df, cols, fill_value=fill_value, clip_abs=clip_abs)
    Xs = bundle.scaler.transform(X)

    Xw = apply_controls_weight(Xs, bundle.control_mask, bundle.controls_weight)

    Z = bundle.pca.transform(Xw)

    out = df.copy()
    for i in range(Z.shape[1]):
        out[f"pca{i+1}"] = Z[:, i].astype("float64")
    return out, Z


def format_float(x: float, width: int = 10, prec: int = 5) -> str:
    return f"{x:{width}.{prec}f}"


def format_range(r: Optional[Dict[str, Any]]) -> str:
    if not r or not r.get("present", True):
        return "[range=?]"
    p01 = safe_float(r.get("p01"))
    p99 = safe_float(r.get("p99"))
    mn = safe_float(r.get("min"))
    mx = safe_float(r.get("max"))

    parts: List[str] = []
    if p01 is not None and p99 is not None:
        parts.append(f"p01={p01:.4g}")
        parts.append(f"p99={p99:.4g}")
    if mn is not None and mx is not None:
        parts.append(f"min={mn:.4g}")
        parts.append(f"max={mx:.4g}")
    if not parts:
        return "[range=?]"
    return "[" + ", ".join(parts) + "]"


def print_pca_loadings(
    bundle: PCAModelBundle,
    *,
    top_k: int = 25,
    abs_sort: bool = True,
    print_full: bool = False,
) -> None:
    cols = bundle.cols
    comps = bundle.pca.components_
    evr = bundle.pca.explained_variance_ratio_

    n_comp = comps.shape[0]
    n_feat = comps.shape[1]

    print("\n=== PCA loadings (components_) ===")
    print(f"n_components={n_comp}  n_features={n_feat}")
    print(f"controls_weight={bundle.controls_weight}")
    print(f"controls_regex={bundle.controls_regex}")
    print(f"n_control_features={int(bundle.control_mask.sum())} / {n_feat}")
    print("feature_ranges: shown as [p01,p99,min,max] from fit rows (raw, pre-clip/pre-fill)")

    for i in range(n_comp):
        print(f"\n--- PC{i+1}  explained_var={evr[i]*100:.2f}% ---")
        w = comps[i, :].astype("float64")

        idx = np.argsort(np.abs(w))[::-1] if abs_sort else np.argsort(w)[::-1]
        if not print_full:
            idx = idx[: min(top_k, len(idx))]

        for j in idx:
            name = cols[j]
            val = float(w[j])
            tag = " [control]" if bundle.control_mask[j] else ""
            r = bundle.feature_ranges.get(name)
            rr = format_range(r)
            print(f"{format_float(val)}  {name}{tag}  {rr}")


def parse_int_maybe(x) -> int:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return 0
    if isinstance(x, (np.integer, int)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return int(x) if np.isfinite(x) else 0
    if isinstance(x, str):
        s = x.strip().lower()
        if s == "" or s == "nan" or s == "none":
            return 0
        try:
            return int(s, 0)
        except Exception:
            try:
                return int(float(s))
            except Exception:
                return 0
    try:
        return int(x)
    except Exception:
        return 0


ALARMWORD_BITS = {
    0: "EStop Pressed",
    1: "RO Pump Feedback Error",
    2: "Pressure Fault",
    3: "Feed Pump Off",
    4: "Inlet Valve Closed",
    5: "Inlet Pressure Sensor Error",
    6: "RO Tank Sensor Error",
    7: "Feed Tank Sensor Error",
    8: "Chlorine Tank Empty",
    9: "Anti-Scalant Pump Error",
}


def decode_alarmword_bits(word: int, bit_map=ALARMWORD_BITS) -> list[str]:
    if word is None:
        return []
    w = int(word)
    active = []
    for bit, name in sorted(bit_map.items()):
        if (w >> bit) & 1:
            active.append(name)
    return active


def alarmword_active_mask(words: np.ndarray, max_bit: int) -> np.ndarray:
    w = words.astype(np.int64, copy=False)
    bits = np.arange(max_bit + 1, dtype=np.int64)
    return ((w[:, None] >> bits[None, :]) & 1).astype(bool)
