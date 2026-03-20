#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Tuple


SITE_LAYOUTS: Dict[str, Dict[str, object]] = {
    "bluerock": {
        "display_name": "Bluerock",
        "schematic": "frontend/svwaternet/src/components/detailed/schematics/BluerockSchematic.js",
        "systems": [
            ("FeedTankSystem", "Feed Tank System"),
            ("ROSystem", "Reverse Osmosis System"),
            ("WaterDeliverSystem", "Water Delivery System"),
        ],
    },
    "santateresa": {
        "display_name": "Santa Teresa",
        "schematic": "frontend/svwaternet/src/components/detailed/schematics/SantaTeresaSchematic.js",
        "systems": [
            ("FeedTankSystem", "Feed Tank System"),
            ("FlushTankSystem", "Flush Tank System"),
            ("ROSystem", "Reverse Osmosis System"),
            ("ROSystemTopLayer", "Reverse Osmosis System"),
            ("DeliverySystem", "Water Delivery System"),
        ],
    },
    "pryorfarm": {
        "display_name": "Pryor Farms",
        "schematic": "frontend/svwaternet/src/components/detailed/schematics/PryorFarmsSchematic.js",
        "systems": [
            ("FeedTankSystem", "Feed Tank System"),
            ("FlushTankSystem", "Flush Tank System"),
            ("ROSystem", "Reverse Osmosis System"),
            ("ROSystemTopLayer", "Reverse Osmosis System"),
            ("DeliverySystem", "Water Delivery System"),
        ],
    },
}

SPECIAL_LABELS = {
    "flushtanklevel": "Flush Tank Level",
    "concentrateflow": "Concentrate Flow",
    "producttds": "Product TDS",
    "recyclevalveposition": "Recycle Valve Position",
    "ropressctrlvalveposition": "RO Pressure Control Valve Position",
}

SPECIAL_UNITS = {
    "flushtanklevel": "%",
    "concentrateflow": "GPM",
    "producttds": "µS/cm",
    "recyclevalveposition": "%",
    "ropressctrlvalveposition": "%",
}

COMPONENT_SPECS = [
    ("SensorIndicator", "sensor", "sensorKey"),
    ("PumpSymbol", "pump", "pumpKey"),
    ("ValveIndicator", "valve", ""),
    ("VariablePieValveIndicator", "control valve", ""),
    ("ThreeWayValveIndicator", "valve", ""),
    ("ThreeWayVariableValveIndicator", "control valve", ""),
    ("ThreeWayVariablePieValveIndicator", "control valve", ""),
]


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//.*", "", text)
    return text


def _extract_object_block(text: str, const_name: str) -> str:
    m = re.search(rf"const\s+{re.escape(const_name)}\s*=\s*\{{", text)
    if not m:
        raise SystemExit(f"could not find const {const_name}")
    start = m.end() - 1
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise SystemExit(f"unterminated object for {const_name}")


def _parse_abbr_map(text: str) -> Dict[str, str]:
    block = _extract_object_block(text, "ABBR")
    return {key: value for key, value in re.findall(r"([A-Za-z0-9_]+)\s*:\s*'([^']*)'", block)}


def _parse_sensor_meta(text: str) -> Dict[str, Dict[str, str]]:
    block = _extract_object_block(text, "SENSOR_META")
    out: Dict[str, Dict[str, str]] = {}
    for key, body in re.findall(r"([A-Za-z0-9_]+)\s*:\s*\{(.*?)\}", block, flags=re.S):
        node: Dict[str, str] = {}
        for field in ("label", "unit", "type"):
            m = re.search(rf"{field}\s*:\s*'([^']*)'", body)
            if m:
                node[field] = m.group(1)
        out[key] = node
    return out


def _parse_site_overrides(text: str, site_key: str) -> Dict[str, Dict[str, str]]:
    block = _extract_object_block(text, "SITE_SENSOR_OVERRIDES")
    site_match = re.search(rf"{re.escape(site_key)}\s*:\s*\{{(.*?)\n\s*\}}", block, flags=re.S)
    if not site_match:
        return {}
    site_block = site_match.group(1)
    out: Dict[str, Dict[str, str]] = {}
    for key, body in re.findall(r"([A-Za-z0-9_]+)\s*:\s*\{(.*?)\}", site_block, flags=re.S):
        node: Dict[str, str] = {}
        for field in ("dataKey", "label", "abbreviation"):
            m = re.search(rf"{field}\s*:\s*'([^']*)'", body)
            if m:
                node[field] = m.group(1)
        out[key] = node
    return out


def _extract_function_body(text: str, fn_name: str) -> str:
    pat = re.compile(rf"function\s+{re.escape(fn_name)}\s*\([^)]*\)\s*\{{", re.S)
    m = pat.search(text)
    if not m:
        raise SystemExit(f"could not find function {fn_name}")
    start = m.end()
    next_match = re.search(r"\nfunction\s+[A-Za-z0-9_]+\s*\(", text[start:])
    end = start + next_match.start() if next_match else len(text)
    return text[start:end]


def _parse_schematic_function_rows(text: str, fn_name: str) -> List[Dict[str, str]]:
    body = _extract_function_body(_strip_comments(text), fn_name)
    rows: List[Dict[str, str]] = []
    seen = set()
    for component_name, component_kind, key_prop in COMPONENT_SPECS:
        for m in re.finditer(rf"<{component_name}\b(.*?)\/>", body, flags=re.S):
            block = m.group(1)
            key = ""
            if key_prop:
                km = re.search(rf'{re.escape(key_prop)}="([^"]+)"', block)
                if km:
                    key = km.group(1)
            if not key:
                km = re.search(r'md\.get\("([^"]+)",\s*"on_click"\)', block)
                if km:
                    key = km.group(1)
            if not key:
                km = re.search(r'md\.get\("([^"]+)",\s*"current_value"\)', block)
                if km:
                    key = km.group(1)
            if not key:
                continue
            dedupe_key = (component_name, key)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            inner_match = re.search(r'innerText="([^"]+)"', block)
            rows.append(
                {
                    "sensor_key": key,
                    "tag_override": inner_match.group(1) if inner_match else "",
                    "kind": component_kind,
                }
            )
    return rows


def _title_case_key(key: str) -> str:
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), key.replace("_", " "))


def _default_dashboard_tag(key: str) -> str:
    return (key[:3] if key else "").upper()


def _infer_label(key: str) -> str:
    if key in SPECIAL_LABELS:
        return SPECIAL_LABELS[key]
    return _title_case_key(key)


def _infer_unit(key: str) -> str:
    if key in SPECIAL_UNITS:
        return SPECIAL_UNITS[key]
    if key.endswith("level"):
        return "%"
    if key.endswith("flow"):
        return "GPM"
    if key.endswith("pressure"):
        return "PSI"
    if key.endswith("tds"):
        return "µS/cm"
    if key.endswith("temp"):
        return "°C"
    if key.endswith("position"):
        return "%"
    return ""


def _infer_report_type(key: str, component_kind: str, configured_type: str) -> str:
    if configured_type:
        return configured_type
    if component_kind != "sensor":
        return component_kind
    return "sensor"


def _latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    out = str(text)
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    out = out.replace("µ", r"\ensuremath{\mu}")
    out = out.replace("μ", r"\ensuremath{\mu}")
    out = out.replace("°", r"\ensuremath{^\circ}")
    return out


def _build_site_rows(site_key: str, dashboard_text: str, schematic_text: str) -> List[Tuple[str, List[Dict[str, str]]]]:
    layout = SITE_LAYOUTS[site_key]
    abbr_map = _parse_abbr_map(dashboard_text)
    sensor_meta = _parse_sensor_meta(dashboard_text)
    site_overrides = _parse_site_overrides(dashboard_text, site_key)

    grouped: Dict[str, List[Dict[str, str]]] = {}
    for fn_name, system_title in layout["systems"]:  # type: ignore[index]
        grouped.setdefault(system_title, [])
        for node in _parse_schematic_function_rows(schematic_text, fn_name):
            key = node["sensor_key"]
            if any(existing["sensor_key"] == key for existing in grouped[system_title]):
                continue
            override = site_overrides.get(key, {})
            plc_tag = override.get("dataKey") or key
            label = override.get("label") or sensor_meta.get(key, {}).get("label") or _infer_label(key)
            unit = sensor_meta.get(key, {}).get("unit") or _infer_unit(key)
            sensor_type = _infer_report_type(
                key,
                node.get("kind", "sensor"),
                sensor_meta.get(key, {}).get("type", ""),
            )
            fallback_tag = override.get("abbreviation") or abbr_map.get(key) or _default_dashboard_tag(key)
            tag = node["tag_override"] or fallback_tag
            notes: List[str] = []
            if node["tag_override"]:
                notes.append(f"schematic tag override; dashboard fallback is {fallback_tag}")
            elif key not in abbr_map and "abbreviation" not in override:
                notes.append("dashboard abbreviation falls back to first 3 uppercase letters")
            if plc_tag != key:
                notes.append(f"UI key {key} resolves to PLC/data key {plc_tag}")
            grouped[system_title].append(
                {
                    "label": label,
                    "tag": tag,
                    "sensor_key": key,
                    "plc_tag": plc_tag,
                    "unit": unit,
                    "type": sensor_type,
                    "note": "; ".join(notes),
                }
            )
    return [(title, rows) for title, rows in grouped.items() if rows]


def _render_site_table(title: str, rows: List[Dict[str, str]]) -> str:
    header = [
        rf"\subsection*{{{_latex_escape(title)}}}",
        r"{\footnotesize",
        r"\setlength{\LTleft}{0pt}",
        r"\setlength{\LTright}{0pt}",
        r"\begin{longtable}{p{3.4cm}p{1.5cm}p{2.8cm}p{1.6cm}p{1.3cm}p{4.6cm}}",
        r"\toprule",
        r"Item & Tag & PLC Tag & Unit & Type & Notes \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        r"Item & Tag & PLC Tag & Unit & Type & Notes \\",
        r"\midrule",
        r"\endhead",
        r"\bottomrule",
        r"\endfoot",
    ]
    body = []
    for row in rows:
        body.append(
            " & ".join(
                [
                    _latex_escape(row["label"]),
                    _latex_escape(row["tag"]),
                    r"\texttt{" + _latex_escape(row["plc_tag"]) + "}",
                    _latex_escape(row["unit"]),
                    _latex_escape(row["type"]),
                    "",
                ]
            )
            + r" \\"
        )
    return "\n".join(header + body + [r"\end{longtable}", r"}", ""])


def main() -> int:
    p = argparse.ArgumentParser(description="Generate LaTeX sensor tables for detailed-dashboard schematics.")
    p.add_argument(
        "--dashboard",
        default="frontend/svwaternet/src/views/detailed-dashboard/DetailedDashboard.js",
    )
    p.add_argument(
        "--out",
        default="docs/detailed_dashboard_sensor_tables.tex",
    )
    args = p.parse_args()

    dashboard_text = Path(args.dashboard).read_text(encoding="utf-8")
    parts = [
        "% Auto-generated from detailed dashboard schematic source files",
        "% Requires: \\usepackage{booktabs,longtable}",
        r"\section*{Detailed Dashboard Sensor Inventory}",
        r"\noindent The tables below enumerate the sensors rendered in the detailed dashboard schematics for Bluerock, Santa Teresa, and Pryor Farms.",
        "",
    ]

    for site_key, layout in SITE_LAYOUTS.items():
        schematic_text = Path(layout["schematic"]).read_text(encoding="utf-8")  # type: ignore[index]
        parts.append(rf"\section*{{{_latex_escape(str(layout['display_name']))}}}")
        parts.append(
            rf"\noindent Source schematic: \texttt{{{_latex_escape(str(layout['schematic']))}}}"
        )
        parts.append("")
        merged_rows: List[Dict[str, str]] = []
        seen = set()
        for _, rows in _build_site_rows(site_key, dashboard_text, schematic_text):
            for row in rows:
                key = row["plc_tag"]
                if key in seen:
                    continue
                seen.add(key)
                merged_rows.append(row)
        parts.append(_render_site_table(f"{layout['display_name']} Instrumentation Table", merged_rows))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    print(f"[ok] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
