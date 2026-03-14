from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Iterable, List, Optional

from .controller import next_mode, pct
from .demand import periodic_demand_gpm
from .types import DemandConfig, TwinConfig, TwinMode, TwinState, TwinStepResult


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def initial_state_from_pct(
    *,
    cfg: TwinConfig,
    feed_pct: float = 65.0,
    product_pct: float = 72.0,
    cond_proxy: Optional[float] = None,
    pressure_psi: Optional[float] = None,
) -> TwinState:
    if cond_proxy is None:
        cond_proxy = cfg.cond_target_standby
    if pressure_psi is None:
        pressure_psi = 0.5 * (cfg.pressure_low_psi + cfg.pressure_high_psi)
    return TwinState(
        t_seconds=0.0,
        mode=TwinMode.STANDBY,
        mode_elapsed_seconds=0.0,
        v_feed_gal=cfg.feed_capacity_gal * clamp(feed_pct / 100.0, 0.0, 1.0),
        v_product_gal=cfg.product_capacity_gal * clamp(product_pct / 100.0, 0.0, 1.0),
        cond_proxy=float(cond_proxy),
        pressure_psi=float(pressure_psi),
        refill_latch_on=bool(feed_pct <= cfg.feed_low_pct),
        ro_latch_on=bool(product_pct <= cfg.product_low_pct),
    )


def _conductivity_target_and_tau(mode: TwinMode, cfg: TwinConfig) -> tuple[float, float]:
    if mode == TwinMode.RO_RUNNING:
        return (cfg.cond_target_ro_running, max(1e-6, cfg.cond_tau_ro_running_seconds))
    if mode == TwinMode.FLUSH1:
        return (cfg.cond_target_flush1, max(1e-6, cfg.cond_tau_flush1_seconds))
    if mode == TwinMode.FLUSH2:
        return (cfg.cond_target_flush2, max(1e-6, cfg.cond_tau_flush2_seconds))
    if mode == TwinMode.OFF:
        return (cfg.cond_target_off, max(1e-6, cfg.cond_tau_off_seconds))
    if mode == TwinMode.EMERGENCY_STOP:
        return (cfg.cond_target_emergency_stop, max(1e-6, cfg.cond_tau_emergency_stop_seconds))
    return (cfg.cond_target_standby, max(1e-6, cfg.cond_tau_standby_seconds))


def step_twin(
    *,
    state: TwinState,
    cfg: TwinConfig,
    demand_cfg: DemandConfig,
    demand_override_gpm: Optional[float] = None,
    off_command: bool = False,
    emergency_stop: bool = False,
    reset_emergency_stop: bool = False,
) -> TwinStepResult:
    dt = cfg.dt_seconds
    feed_pct = pct(state.v_feed_gal, cfg.feed_capacity_gal)
    product_pct = pct(state.v_product_gal, cfg.product_capacity_gal)

    refill_latch_on = bool(state.refill_latch_on)
    if feed_pct <= cfg.feed_low_pct:
        refill_latch_on = True
    elif feed_pct >= cfg.feed_high_pct:
        refill_latch_on = False

    ro_latch_on = bool(state.ro_latch_on)
    if product_pct <= cfg.product_low_pct:
        ro_latch_on = True
    elif product_pct >= cfg.product_high_pct:
        ro_latch_on = False

    mode = next_mode(
        state,
        cfg,
        refill_latch_on=refill_latch_on,
        ro_latch_on=ro_latch_on,
        off_command=off_command,
        emergency_stop=emergency_stop,
        reset_emergency_stop=reset_emergency_stop,
    )
    mode_elapsed = state.mode_elapsed_seconds + dt if mode == state.mode else 0.0

    q_refill = cfg.well_refill_gpm if refill_latch_on else 0.0

    q_permeate = cfg.ro_permeate_gpm if mode == TwinMode.RO_RUNNING else 0.0
    q_feed_draw = cfg.ro_feed_draw_gpm if mode == TwinMode.RO_RUNNING else 0.0
    q_flush = 0.0
    if mode == TwinMode.FLUSH1:
        q_flush = cfg.flush1_draw_gpm
    elif mode == TwinMode.FLUSH2:
        q_flush = cfg.flush2_draw_gpm

    q_demand = periodic_demand_gpm(state.t_seconds, demand_cfg)
    if demand_override_gpm is not None:
        q_demand = max(0.0, float(demand_override_gpm))
    if mode in (TwinMode.OFF, TwinMode.EMERGENCY_STOP):
        q_demand = 0.0

    dv_feed = (q_refill - q_feed_draw - q_flush) * (dt / 60.0)
    dv_product = (q_permeate - q_demand) * (dt / 60.0)

    v_feed_next = clamp(state.v_feed_gal + dv_feed, 0.0, cfg.feed_capacity_gal)
    v_product_next = clamp(state.v_product_gal + dv_product, 0.0, cfg.product_capacity_gal)

    c_target, tau = _conductivity_target_and_tau(mode, cfg)
    alpha = clamp(dt / tau, 0.0, 1.0)
    cond_next = state.cond_proxy + alpha * (c_target - state.cond_proxy)

    pressure_pump_on = 1 if state.pressure_psi < cfg.pressure_low_psi else 0
    if state.pressure_psi >= cfg.pressure_high_psi:
        pressure_pump_on = 0
    if mode in (TwinMode.OFF, TwinMode.EMERGENCY_STOP):
        pressure_pump_on = 0
    dp_rise = cfg.pressure_rise_psi_per_min * (dt / 60.0) if pressure_pump_on else 0.0
    demand_gal_step = q_demand * (dt / 60.0)
    dp_drop = (cfg.pressure_decay_psi_per_min * (dt / 60.0)) + (cfg.pressure_demand_drop_psi_per_gal * demand_gal_step)
    pressure_next = clamp(state.pressure_psi + dp_rise - dp_drop, 0.0, 150.0)

    next_state = TwinState(
        t_seconds=state.t_seconds + dt,
        mode=mode,
        mode_elapsed_seconds=mode_elapsed,
        v_feed_gal=v_feed_next,
        v_product_gal=v_product_next,
        cond_proxy=cond_next,
        pressure_psi=pressure_next,
        refill_latch_on=refill_latch_on,
        ro_latch_on=ro_latch_on,
    )

    return TwinStepResult(
        state=next_state,
        q_demand_gpm=q_demand,
        q_refill_gpm=q_refill,
        q_permeate_gpm=q_permeate,
        q_feed_draw_gpm=q_feed_draw,
        q_flush_gpm=q_flush,
        pressure_pump_on=pressure_pump_on,
        pressure_psi=pressure_next,
        feed_pct=pct(v_feed_next, cfg.feed_capacity_gal),
        product_pct=pct(v_product_next, cfg.product_capacity_gal),
    )


def simulate(
    *,
    hours: float,
    state0: TwinState,
    cfg: TwinConfig,
    demand_cfg: DemandConfig,
) -> List[Dict[str, float | str]]:
    if hours <= 0:
        return []

    rows: List[Dict[str, float | str]] = []
    steps = int(round((hours * 3600.0) / cfg.dt_seconds))
    s = state0
    for _ in range(steps):
        r = step_twin(state=s, cfg=cfg, demand_cfg=demand_cfg)
        s = r.state
        rows.append(
            {
                "t_seconds": s.t_seconds,
                "mode": s.mode.value,
                "mode_elapsed_seconds": s.mode_elapsed_seconds,
                "v_feed_gal": s.v_feed_gal,
                "v_product_gal": s.v_product_gal,
                "feed_pct": r.feed_pct,
                "product_pct": r.product_pct,
                "q_demand_gpm": r.q_demand_gpm,
                "q_refill_gpm": r.q_refill_gpm,
                "q_permeate_gpm": r.q_permeate_gpm,
                "q_feed_draw_gpm": r.q_feed_draw_gpm,
                "q_flush_gpm": r.q_flush_gpm,
                "pressure_pump_on": r.pressure_pump_on,
                "pressure_psi": r.pressure_psi,
                "cond_proxy": s.cond_proxy,
            }
        )
    return rows


def config_dict(cfg: TwinConfig, demand_cfg: DemandConfig) -> Dict[str, object]:
    out: Dict[str, object] = {}
    out.update({f"twin_{k}": float(v) for k, v in asdict(cfg).items()})
    for k, v in asdict(demand_cfg).items():
        key = f"demand_{k}"
        if isinstance(v, (int, float)):
            out[key] = float(v)
        else:
            # Keep non-numeric config values as strings for metadata visibility.
            out[key] = str(v)  # type: ignore[assignment]
    return out
