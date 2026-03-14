from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TwinMode(str, Enum):
    OFF = "OFF"
    STANDBY = "STANDBY"
    RO_RUNNING = "RO_RUNNING"
    FLUSH1 = "FLUSH1"
    FLUSH2 = "FLUSH2"
    EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclass(frozen=True)
class TwinConfig:
    # Simulation resolution
    dt_seconds: float = 2.0

    # Tank capacities (gallons)
    feed_capacity_gal: float = 1000.0
    product_capacity_gal: float = 1000.0

    # Control thresholds in percent
    feed_low_pct: float = 60.0
    feed_high_pct: float = 70.0
    product_low_pct: float = 65.0
    product_high_pct: float = 80.0

    # Flows (gpm)
    well_refill_gpm: float = 6.0
    ro_permeate_gpm: float = 0.28
    ro_feed_draw_gpm: float = 0.75
    flush1_draw_gpm: float = 0.35
    flush2_draw_gpm: float = 0.20

    # Flush
    flush1_duration_seconds: float = 30.0
    flush2_duration_seconds: float = 15.0

    # Pressure tank supervisory band (psi)
    pressure_low_psi: float = 42.0
    pressure_high_psi: float = 62.0
    pressure_rise_psi_per_min: float = 18.0
    pressure_decay_psi_per_min: float = 0.2
    pressure_demand_drop_psi_per_gal: float = 0.9

    # Conductivity proxy (uS/cm-ish units)
    cond_target_off: float = 260.0
    cond_target_standby: float = 250.0
    cond_target_ro_running: float = 90.0
    cond_target_flush1: float = 380.0
    cond_target_flush2: float = 320.0
    cond_target_emergency_stop: float = 420.0
    cond_tau_off_seconds: float = 240.0
    cond_tau_standby_seconds: float = 240.0
    cond_tau_ro_running_seconds: float = 120.0
    cond_tau_flush1_seconds: float = 45.0
    cond_tau_flush2_seconds: float = 60.0
    cond_tau_emergency_stop_seconds: float = 30.0


@dataclass(frozen=True)
class DemandConfig:
    # Baseline and periodic demand model in gpm
    base_gpm: float = 0.06
    day_amp_gpm: float = 0.04
    week_amp_gpm: float = 0.02
    day_phase_hours: float = 15.0
    week_phase_days: float = 2.0
    # Optional learned profile lookup (dow x hour CSV: rows dow=0..6, cols 0..23).
    profile_csv_path: str = ""
    # Optional harmonic fit JSON emitted by fit_harmonic_demand.py.
    harmonic_fit_json_path: str = ""
    profile_timezone: str = "America/Los_Angeles"
    # Optional anchor for absolute local-time alignment.
    start_ts_utc: str = ""


@dataclass
class TwinState:
    t_seconds: float
    mode: TwinMode
    mode_elapsed_seconds: float

    # Tank inventory in gallons
    v_feed_gal: float
    v_product_gal: float

    # Conductivity proxy state
    cond_proxy: float
    pressure_psi: float
    refill_latch_on: bool = False
    ro_latch_on: bool = False


@dataclass(frozen=True)
class TwinStepResult:
    state: TwinState
    q_demand_gpm: float
    q_refill_gpm: float
    q_permeate_gpm: float
    q_feed_draw_gpm: float
    q_flush_gpm: float
    pressure_pump_on: int
    pressure_psi: float
    feed_pct: float
    product_pct: float
