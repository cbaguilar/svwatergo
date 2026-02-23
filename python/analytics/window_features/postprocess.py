from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from .specs import ColumnGroups, FlowGate


def apply_flow_gates_to_features(
    feat: pd.DataFrame,
    *,
    gates: Sequence[FlowGate],
    feature_suffixes: Sequence[str],
    unknown_col: str = "state_unknown",
) -> pd.DataFrame:
    """
    Set selected feature columns to NaN when flow is too low OR window is unknown/outage.

    - Uses flow_col + gate.flow_suffix (e.g. "feedflow__mean_tw") as the gating signal.
    - If the flow feature column doesn't exist, gates everything for safety.
    """
    feat = feat.copy()
    unknown = pd.to_numeric(feat.get(unknown_col, 0), errors="coerce").fillna(0).astype(int)

    for gate in gates:
        flow_feat_col = f"{gate.flow_col}{gate.flow_suffix}"
        if flow_feat_col not in feat.columns:
            mask_bad = pd.Series(True, index=feat.index)
        else:
            flowv = pd.to_numeric(feat[flow_feat_col], errors="coerce").astype("float64")
            mask_bad = (~np.isfinite(flowv)) | (flowv < float(gate.min_value))

        mask_bad = mask_bad | (unknown == 1)

        for t in gate.targets:
            for suf in feature_suffixes:
                col = f"{t}{suf}"
                if col in feat.columns:
                    feat.loc[mask_bad, col] = np.nan

    return feat


def add_continuous_window_derivatives(
    feat: pd.DataFrame,
    groups: ColumnGroups,
    *,
    base_suffix: str = "__mean_tw",
    out_suffix: str = "__d1",
    fill_value: float = 0.0,
    unknown_col: str = "state_unknown",
    sort_col: str = "window_start_ts",
) -> pd.DataFrame:
    """
    Post-pass: compute window-to-window deltas for continuous signals,
    but DO NOT compute across unknown/outage windows.
    Rules:
      - If current or previous window is unknown -> derivative = 0
      - If base value missing -> derivative = 0
    """
    feat = feat.copy()

    if sort_col in feat.columns:
        feat = feat.sort_values(sort_col).reset_index(drop=True)

    unknown = pd.to_numeric(feat.get(unknown_col, 0), errors="coerce").fillna(0).astype(int)

    for c in groups.continuous:
        base_col = f"{c}{base_suffix}"
        out_col = f"{c}{out_suffix}"

        if base_col not in feat.columns:
            feat[out_col] = fill_value
            continue

        x = pd.to_numeric(feat[base_col], errors="coerce").astype("float64")
        dx = x.diff()

        mask_bad = (unknown == 1) | (unknown.shift(1, fill_value=1) == 1)
        dx = dx.mask(mask_bad, other=np.nan)
        dx = dx.where(np.isfinite(dx), np.nan)

        feat[out_col] = dx.fillna(fill_value).astype("float64")

    return feat
