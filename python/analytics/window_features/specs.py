from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ColumnGroups:
    continuous: List[str]
    boolean: List[str]
    discrete: List[str]


@dataclass(frozen=True)
class FlowGate:
    """
    Gate certain derived feature columns based on a flow signal.

    If flow_col + flow_suffix (e.g. "feedflow__mean_tw") is < min_value (or non-finite),
    then for each target in targets, set target+suffixes to NaN.

    Also gates out windows where state_unknown == 1.
    """

    name: str
    flow_col: str
    min_value: float
    targets: List[str]
    flow_suffix: str = "__mean_tw"


@dataclass(frozen=True)
class SitePipelineSpec:
    site: str
    ts_col: str
    continuous: List[str]
    boolean: List[str]
    discrete: List[str]
    ignore: List[str]
    rename: Optional[Dict[str, str]] = None
    flow_gates: Optional[List[FlowGate]] = None


# --- PRYORFARM_SPEC: move totalizers/powermeter/totalhrs/daily* into continuous; remove from ignore
PRYORFARM_SPEC = SitePipelineSpec(
    site="pryorfarm",
    ts_col="plctime",
    continuous=[
        "permeateflow",
        "deliveryflow",
        "inletflow",
        "concentrateflow",
        "recycleflow",
        "feedtanklevel",
        "prodtanklevel",
        "flushtanklevel",
        "prodtankdepth",
        "feedtankdepth",
        "flushtankdepth",
        "inletpressure",
        "concentratepressure",
        "permeatepressure",
        "ropressure",
        "deliverypressure",
        "feedpressure",
        "recyclevalveposition",
        "ropressctrlvalveposition",
        "ropumpspeed",
        "permtds",
        "feedtds",
        "producttds",
        "permnitrate",
        "permtemp",
        "flushduret",
        "totalroflow",
        "totalinletflow",
        "totalconcflow",
        "totaldelflow",
        "dailypermflow",
        "dailyinletflow",
        "totalhrs",
        "powermeter",
    ],
    boolean=[
        "dumpproduct",
        "wellpumprun",
        "wellpumpauto",
        "feedpumprun",
        "ropumprun",
        "deliveryrun",
        "deliveryauto",
        "inletrun",
        "flushrun",
        "concbypassrun",
        "proddiversionrun",
        "flushdiversionrun",
        "runflush",
        "flushtankfull",
        "prodtankdisable",
        "alarm",
        "lockout",
        "rostandby",
    ],
    discrete=[
        "alarmword",
        "warnword0",
        "warnword1",
        "state",
    ],
    ignore=[
        "location",
        "recordtime",
    ],
    rename=None,
    flow_gates=[
        FlowGate(
            name="permeate_valid",
            flow_col="permeateflow",
            flow_suffix="__mean_tw",
            min_value=1.0,
            targets=["permtds", "permnitrate", "permtemp"],
        ),
        FlowGate(
            name="feed_valid",
            flow_col="inletflow",
            flow_suffix="__mean_tw",
            min_value=4.0,
            targets=["feedtds"],
        ),
    ],
)


# --- BLUEROCK_SPEC: same idea (keep totalizers/daily/hrs/power)
BLUEROCK_SPEC = SitePipelineSpec(
    site="bluerock",
    ts_col="plctime",
    continuous=[
        "permeateflow",
        "deliveryflow",
        "feedflow",
        "concentrateflow",
        "recycleflow",
        "feedtanklevel",
        "prodtanklevel",
        "residualtanklevel",
        "prodtankdepth",
        "feedtankdepth",
        "residualtankdepth",
        "inletpressure",
        "concentratepressure",
        "permeatepressure",
        "ropressure",
        "deliverypressure",
        "feedpressure",
        "recyclevalveposition",
        "ropressctrlvalveposition",
        "ropumpspeed",
        "permtds",
        "feedtds",
        "producttds",
        "permnitrate",
        "permtemp",
        "flushduret",
        "totalroflow",
        "totalfeedflow",
        "totalrecycleflow",
        "totaldelflow",
        "dailypermflow",
        "totalhrs",
        "powermeter",
    ],
    boolean=[
        "dumpproduct",
        "wellpumprun",
        "wellpumpauto",
        "feedpumprun",
        "ropumprun",
        "deliveryrun",
        "deliveryauto",
        "inletrun",
        "concbypassrun",
        "proddiversionrun",
        "runflush",
        "flushrun",
        "chlorinepumprun",
        "residtankvalverun",
        "prodtankdisable",
        "alarm",
        "rostandby",
        "lockout",
    ],
    discrete=[
        "alarmword",
        "warnword0",
        "warnword1",
        "state",
    ],
    ignore=[
        "location",
        "schema_version",
        "extras",
        "recordtime",
    ],
    rename=None,
    flow_gates=[
        FlowGate(
            name="permeate_valid",
            flow_col="permeateflow",
            flow_suffix="__mean_tw",
            min_value=1.0,
            targets=["permtds", "permnitrate", "permtemp"],
        ),
        FlowGate(
            name="feed_valid",
            flow_col="feedflow",
            flow_suffix="__mean_tw",
            min_value=4.0,
            targets=["feedtds"],
        ),
    ],
)


# --- SANTATERESA_SPEC: move totalizers/powermeter/totalhrs/daily* into continuous; remove from ignore
SANTATERESA_SPEC = SitePipelineSpec(
    site="santateresa",
    ts_col="plctime",
    continuous=[
        "permeateflow",
        "deliveryflow",
        "inletflow",
        "concentrateflow",
        "recycleflow",
        "feedtanklevel",
        "prodtanklevel",
        "flushtanklevel",
        "prodtankdepth",
        "feedtankdepth",
        "flushtankdepth",
        "inletpressure",
        "concentratepressure",
        "permeatepressure",
        "ropressure",
        "deliverypressure",
        "feedpressure",
        "recyclevalveposition",
        "ropressctrlvalveposition",
        "ropumpspeed",
        "permtds",
        "feedtds",
        "producttds",
        "permnitrate",
        "permtemp",
        "flushduret",
        "totalroflow",
        "totalinletflow",
        "totalconcflow",
        "totaldelflow",
        "dailypermflow",
        "dailyinletflow",
        "totalhrs",
        "powermeter",
    ],
    boolean=[
        "dumpproduct",
        "wellpumprun",
        "wellpumpauto",
        "feedpumprun",
        "ropumprun",
        "deliveryrun",
        "deliveryauto",
        "inletrun",
        "flushrun",
        "concbypassrun",
        "proddiversionrun",
        "flushdiversionrun",
        "runflush",
        "flushtankfull",
        "prodtankdisable",
        "alarm",
        "lockout",
        "rostandby",
    ],
    discrete=[
        "alarmword",
        "warnword0",
        "warnword1",
        "state",
    ],
    ignore=[
        "location",
        "recordtime",
    ],
    rename=None,
    flow_gates=[
        FlowGate(
            name="permeate_valid",
            flow_col="permeateflow",
            flow_suffix="__mean_tw",
            min_value=1.0,
            targets=["permtds", "permnitrate", "permtemp"],
        ),
        FlowGate(
            name="feed_valid",
            flow_col="inletflow",
            flow_suffix="__mean_tw",
            min_value=4.0,
            targets=["feedtds"],
        ),
    ],
)


PIPELINES: Dict[str, SitePipelineSpec] = {
    "bluerock": BLUEROCK_SPEC,
    "pryorfarm": PRYORFARM_SPEC,
    "santateresa": SANTATERESA_SPEC,
}


def apply_site_spec(
    df: pd.DataFrame, spec: SitePipelineSpec
) -> Tuple[pd.DataFrame, ColumnGroups, Dict[str, object]]:
    df = df.copy()

    if spec.rename:
        df = df.rename(columns=spec.rename)

    if spec.ts_col not in df.columns:
        raise ValueError(f"{spec.site}: missing timestamp column '{spec.ts_col}'")

    expected = spec.continuous + spec.boolean + spec.discrete

    missing_cont = [c for c in spec.continuous if c not in df.columns]
    missing_bool = [c for c in spec.boolean if c not in df.columns]
    missing_disc = [c for c in spec.discrete if c not in df.columns]

    for c in expected:
        if c not in df.columns:
            df[c] = np.nan

    drop = [c for c in spec.ignore if c in df.columns]
    if drop:
        df = df.drop(columns=drop)

    df[expected] = df[expected].apply(pd.to_numeric, errors="coerce")

    groups = ColumnGroups(
        continuous=sorted(spec.continuous),
        boolean=sorted(spec.boolean),
        discrete=sorted(spec.discrete),
    )

    other = sorted([c for c in df.columns if c not in ([spec.ts_col] + expected)])
    report: Dict[str, object] = {
        "site": spec.site,
        "ts_col": spec.ts_col,
        "n_cols_continuous": len(spec.continuous),
        "n_cols_boolean": len(spec.boolean),
        "n_cols_discrete": len(spec.discrete),
        "missing_expected_continuous": missing_cont,
        "missing_expected_boolean": missing_bool,
        "missing_expected_discrete": missing_disc,
        "other_columns_present_after_ignore": other,
    }
    return df, groups, report
