from __future__ import annotations

import re
from typing import Optional

_BASE_UNITS = {
    "permeateflow": "GPM",
    "feedflow": "GPM",
    "feedflow_soft": "GPM",
    "deliveryflow": "GPM",
    "recycleflow": "GPM",
    "inletflow": "GPM",
    "concentrateflow": "GPM",
    "feedtanklevel": "%",
    "prodtanklevel": "%",
    "producttanklevel": "%",
    "residualtanklevel": "%",
    "flushtanklevel": "%",
    "permtds": "µS/cm",
    "feedtds": "µS/cm",
    "permnitrate": "mg/L as NO3-N",
    "permtemp": "°C",
    "inletpressure": "PSI",
    "feedpressure": "PSI",
    "ropressure": "PSI",
    "concentratepressure": "PSI",
    "permeatepressure": "PSI",
    "deliverypressure": "PSI",
    "totalroflow": "gal",
    "totalfeedflow": "gal",
    "totalinletflow": "gal",
    "totalrecycleflow": "gal",
    "totalconcflow": "gal",
    "totaldelflow": "gal",
    "dailypermflow": "gal",
    "dailyinletflow": "gal",
}

_UNITLESS_PREFIXES = (
    "state__",
    "alarm__",
    "alarmword__",
    "warnword__",
    "score_",
    "y_true_",
    "y_pred_",
)

_UNITLESS_EXACT = {
    "state",
    "pred_confidence",
    "sample_end_index",
    "timestamp",
    "horizon",
}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")


def infer_sensor_unit(label: str) -> Optional[str]:
    text = _normalize(label)
    if not text:
        return None
    if text in _UNITLESS_EXACT:
        return None
    if any(text.startswith(prefix) for prefix in _UNITLESS_PREFIXES):
        return None
    if text in _BASE_UNITS:
        return _BASE_UNITS[text]

    parts = [p for p in re.split(r"[^a-z0-9]+", str(label).lower()) if p]
    for part in parts:
        if part in _BASE_UNITS:
            return _BASE_UNITS[part]

    for key in sorted(_BASE_UNITS.keys(), key=len, reverse=True):
        if key in text:
            return _BASE_UNITS[key]

    if "flow" in text:
        if text.startswith("total") or text.startswith("daily"):
            return "gal"
        return "GPM"
    if "pressure" in text:
        return "PSI"
    if "tanklevel" in text or text.endswith("level") or "_level_" in text:
        return "%"
    if "tds" in text or "conduct" in text:
        return "µS/cm"
    if "nitrate" in text:
        return "mg/L as NO3-N"
    if "temp" in text or "temperature" in text:
        return "°C"
    return None


def label_with_unit(label: str) -> str:
    unit = infer_sensor_unit(label)
    if not unit:
        return str(label)
    text = str(label)
    if f"({unit})" in text or text.endswith(f" {unit}"):
        return text
    return f"{text} ({unit})"
