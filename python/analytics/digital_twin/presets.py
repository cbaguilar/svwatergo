from __future__ import annotations

from typing import Any, Dict


def site_presets() -> Dict[str, Dict[str, Any]]:
    # Calibrated defaults by site. Values are flow/demand parameters only;
    # capacities/thresholds remain CLI-configurable.
    return {
        "bluerock": {
            # Calibrated from observed feed refill ramp and RO operating flows.
            "well_refill_gpm": 23.6,
            "ro_permeate_gpm": 3.0,
            "ro_feed_draw_gpm": 5.2,
            "flush1_draw_gpm": 0.35,
            "flush2_draw_gpm": 0.20,
            # Calibrated tank capacities + hysteresis setpoints from Feb 2026 PLC transitions.
            "feed_capacity_gal": 4600.0,
            "product_capacity_gal": 5000.0,
            "feed_low_pct": 65.019726,
            "feed_high_pct": 79.984659,
            "product_low_pct": 60.01047,
            "product_high_pct": 74.200455,
            # Pressure pump hysteresis from deliveryrun transition quantiles (median ON/OFF).
            "pressure_low_psi": 49.019097,
            "pressure_high_psi": 56.647136,
            # Learned sinusoidal demand parameters from Feb 2026 deliveryflow (2h aggregation).
            "demand_base_gpm": 1.936869893869222,
            "demand_day_amp_gpm": 0.26590657462413575,
            "demand_week_amp_gpm": 0.14513820220639023,
            "demand_day_phase_hours": 7.880042050783156,
            "demand_week_phase_days": 6.233090155410138,
            # Keep profile lookup disabled by default for simple sinusoidal demand.
            "demand_profile_csv_path": "",
            # Optional exact harmonic model from fitter output.
            "demand_harmonic_fit_json_path": "",
            "demand_profile_timezone": "America/Los_Angeles",
        },
        # Derived from observed mean flow by binary pump/valve combinations.
        "pryorfarm": {
            "well_refill_gpm": 4.013671875,
            "ro_permeate_gpm": 3.2413480067650036,
            "ro_feed_draw_gpm": 8.985630729898807,
            "flush1_draw_gpm": 3.889981447124305,
            "flush2_draw_gpm": 3.889981447124305,
            # Current model uses harmonic demand, so keep conservative defaults.
            "demand_base_gpm": 1.321035043623036,
            "demand_day_amp_gpm": 0.0,
            "demand_week_amp_gpm": 0.0,
            "demand_day_phase_hours": 15.0,
            "demand_week_phase_days": 2.0,
            "demand_profile_csv_path": "",
            "demand_harmonic_fit_json_path": "",
            "demand_profile_timezone": "America/Los_Angeles",
        },
        "santateresa": {
            "well_refill_gpm": 6.0,
            "ro_permeate_gpm": 0.28,
            "ro_feed_draw_gpm": 0.75,
            "flush1_draw_gpm": 0.35,
            "flush2_draw_gpm": 0.20,
            "demand_base_gpm": 0.06,
            "demand_day_amp_gpm": 0.04,
            "demand_week_amp_gpm": 0.02,
            "demand_day_phase_hours": 15.0,
            "demand_week_phase_days": 2.0,
            "demand_profile_csv_path": "",
            "demand_harmonic_fit_json_path": "",
            "demand_profile_timezone": "America/Los_Angeles",
        },
    }
