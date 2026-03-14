#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from digital_twin import DemandConfig, TwinConfig, config_dict, initial_state_from_pct, simulate
from digital_twin.presets import site_presets


def _write_csv(rows: list[dict[str, float | str]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        out_csv.write_text("", encoding="utf-8")
        return
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    presets = site_presets()
    ap = argparse.ArgumentParser(description="Run discrete digital twin simulation for treatment systems")
    ap.add_argument(
        "--site",
        default="bluerock",
        choices=sorted(presets.keys()),
        help="Site preset for calibrated flow/demand defaults",
    )
    ap.add_argument("--hours", type=float, default=24.0, help="Simulation horizon in hours")
    ap.add_argument("--dt-seconds", type=float, default=2.0)

    ap.add_argument("--feed-cap-gal", type=float, default=1000.0)
    ap.add_argument("--product-cap-gal", type=float, default=5000.0)

    ap.add_argument("--feed-low-pct", type=float, default=65.0)
    ap.add_argument("--feed-high-pct", type=float, default=70.0)
    ap.add_argument("--product-low-pct", type=float, default=65.0)
    ap.add_argument("--product-high-pct", type=float, default=80.0)

    ap.add_argument("--well-refill-gpm", type=float, default=None, help="Override site preset value")
    ap.add_argument("--ro-permeate-gpm", type=float, default=None, help="Override site preset value")
    ap.add_argument("--ro-feed-draw-gpm", type=float, default=None, help="Override site preset value")
    ap.add_argument("--flush1-draw-gpm", type=float, default=None, help="Override site preset value")
    ap.add_argument("--flush2-draw-gpm", type=float, default=None, help="Override site preset value")
    ap.add_argument("--flush1-seconds", type=float, default=30.0)
    ap.add_argument("--flush2-seconds", type=float, default=15.0)
    ap.add_argument("--pressure-low-psi", type=float, default=42.0)
    ap.add_argument("--pressure-high-psi", type=float, default=62.0)
    ap.add_argument("--pressure-rise-psi-per-min", type=float, default=18.0)
    ap.add_argument("--pressure-decay-psi-per-min", type=float, default=0.2)
    ap.add_argument("--pressure-demand-drop-psi-per-gal", type=float, default=0.9)

    ap.add_argument("--init-feed-pct", type=float, default=65.0)
    ap.add_argument("--init-product-pct", type=float, default=72.0)
    ap.add_argument("--init-pressure-psi", type=float, default=52.0)

    ap.add_argument("--demand-base-gpm", type=float, default=None, help="Override site preset value")
    ap.add_argument("--demand-day-amp-gpm", type=float, default=None, help="Override site preset value")
    ap.add_argument("--demand-week-amp-gpm", type=float, default=None, help="Override site preset value")
    ap.add_argument(
        "--demand-fit-json",
        default=None,
        help="Harmonic fit JSON from fit_harmonic_demand.py (uses same fitted basis/windowing).",
    )
    ap.add_argument(
        "--demand-profile-csv",
        default=None,
        help="Optional hour x day-of-week demand profile CSV (rows dow=0..6, cols 0..23).",
    )
    ap.add_argument(
        "--demand-profile-timezone",
        default=None,
        help="Timezone for demand profile lookup (default from site preset).",
    )
    ap.add_argument(
        "--start-ts-utc",
        default="",
        help="Optional UTC anchor timestamp for profile alignment (e.g., 2026-02-25T00:00:00Z).",
    )
    ap.add_argument("--demand-day-phase-hours", type=float, default=None, help="Override site preset value")
    ap.add_argument("--demand-week-phase-days", type=float, default=None, help="Override site preset value")

    ap.add_argument("--out-csv", required=True, help="Output simulation CSV")
    ap.add_argument("--out-meta", required=True, help="Output metadata JSON")
    args = ap.parse_args()

    preset = presets[str(args.site).strip().lower()]

    def v(name: str, override: float | None) -> float:
        if override is not None:
            return float(override)
        return float(preset[name])

    cfg = TwinConfig(
        dt_seconds=float(args.dt_seconds),
        feed_capacity_gal=float(args.feed_cap_gal),
        product_capacity_gal=float(args.product_cap_gal),
        feed_low_pct=float(args.feed_low_pct),
        feed_high_pct=float(args.feed_high_pct),
        product_low_pct=float(args.product_low_pct),
        product_high_pct=float(args.product_high_pct),
        well_refill_gpm=v("well_refill_gpm", args.well_refill_gpm),
        ro_permeate_gpm=v("ro_permeate_gpm", args.ro_permeate_gpm),
        ro_feed_draw_gpm=v("ro_feed_draw_gpm", args.ro_feed_draw_gpm),
        flush1_draw_gpm=v("flush1_draw_gpm", args.flush1_draw_gpm),
        flush2_draw_gpm=v("flush2_draw_gpm", args.flush2_draw_gpm),
        flush1_duration_seconds=float(args.flush1_seconds),
        flush2_duration_seconds=float(args.flush2_seconds),
        pressure_low_psi=float(args.pressure_low_psi),
        pressure_high_psi=float(args.pressure_high_psi),
        pressure_rise_psi_per_min=float(args.pressure_rise_psi_per_min),
        pressure_decay_psi_per_min=float(args.pressure_decay_psi_per_min),
        pressure_demand_drop_psi_per_gal=float(args.pressure_demand_drop_psi_per_gal),
    )
    demand_cfg = DemandConfig(
        base_gpm=v("demand_base_gpm", args.demand_base_gpm),
        day_amp_gpm=v("demand_day_amp_gpm", args.demand_day_amp_gpm),
        week_amp_gpm=v("demand_week_amp_gpm", args.demand_week_amp_gpm),
        harmonic_fit_json_path=(
            str(args.demand_fit_json).strip()
            if args.demand_fit_json is not None
            else str(preset.get("demand_harmonic_fit_json_path", "")).strip()
        ),
        profile_csv_path=(
            str(args.demand_profile_csv).strip()
            if args.demand_profile_csv is not None
            else str(preset.get("demand_profile_csv_path", "")).strip()
        ),
        profile_timezone=(
            str(args.demand_profile_timezone).strip()
            if args.demand_profile_timezone is not None
            else str(preset.get("demand_profile_timezone", "America/Los_Angeles")).strip()
        ),
        start_ts_utc=str(args.start_ts_utc).strip(),
        day_phase_hours=(
            float(args.demand_day_phase_hours)
            if args.demand_day_phase_hours is not None
            else float(preset.get("demand_day_phase_hours", 15.0))
        ),
        week_phase_days=(
            float(args.demand_week_phase_days)
            if args.demand_week_phase_days is not None
            else float(preset.get("demand_week_phase_days", 2.0))
        ),
    )

    state0 = initial_state_from_pct(
        cfg=cfg,
        feed_pct=float(args.init_feed_pct),
        product_pct=float(args.init_product_pct),
        pressure_psi=float(args.init_pressure_psi),
    )

    rows = simulate(
        hours=float(args.hours),
        state0=state0,
        cfg=cfg,
        demand_cfg=demand_cfg,
    )

    out_csv = Path(args.out_csv)
    out_meta = Path(args.out_meta)
    _write_csv(rows, out_csv)

    modes = {
        "OFF": 0,
        "STANDBY": 0,
        "RO_RUNNING": 0,
        "FLUSH1": 0,
        "FLUSH2": 0,
        "EMERGENCY_STOP": 0,
    }
    for r in rows:
        m = str(r.get("mode", "STANDBY"))
        modes[m] = int(modes.get(m, 0)) + 1

    meta = {
        "summary": {
            "rows": len(rows),
            "hours": float(args.hours),
            "dt_seconds": float(args.dt_seconds),
            "site_preset": str(args.site).strip().lower(),
            "mode_counts": modes,
        },
        "config": config_dict(cfg, demand_cfg),
        "initial_state": {
            "feed_pct": float(args.init_feed_pct),
            "product_pct": float(args.init_product_pct),
            "pressure_psi": float(args.init_pressure_psi),
        },
    }
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"[write] csv={out_csv} rows={len(rows)}")
    print(f"[write] meta={out_meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
