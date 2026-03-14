from __future__ import annotations

from .types import TwinConfig, TwinMode, TwinState


def pct(volume_gal: float, capacity_gal: float) -> float:
    if capacity_gal <= 0:
        return 0.0
    return 100.0 * (volume_gal / capacity_gal)


def next_mode(
    state: TwinState,
    cfg: TwinConfig,
    *,
    refill_latch_on: bool,
    ro_latch_on: bool,
    off_command: bool = False,
    emergency_stop: bool = False,
    reset_emergency_stop: bool = False,
) -> TwinMode:
    feed_pct = pct(state.v_feed_gal, cfg.feed_capacity_gal)

    if emergency_stop:
      return TwinMode.EMERGENCY_STOP

    if state.mode == TwinMode.EMERGENCY_STOP:
      if reset_emergency_stop:
          return TwinMode.OFF if off_command else TwinMode.STANDBY
      return TwinMode.EMERGENCY_STOP

    if off_command:
        return TwinMode.OFF

    if state.mode == TwinMode.OFF:
        return TwinMode.STANDBY

    if state.mode == TwinMode.STANDBY:
        if ro_latch_on and (feed_pct > cfg.feed_low_pct):
            return TwinMode.RO_RUNNING
        return TwinMode.STANDBY

    if state.mode == TwinMode.RO_RUNNING:
        should_stop = (not ro_latch_on)
        return TwinMode.FLUSH1 if should_stop else TwinMode.RO_RUNNING

    if state.mode == TwinMode.FLUSH1:
        if state.mode_elapsed_seconds >= cfg.flush1_duration_seconds:
            return TwinMode.FLUSH2
        return TwinMode.FLUSH1

    if state.mode == TwinMode.FLUSH2:
        if state.mode_elapsed_seconds >= cfg.flush2_duration_seconds:
            return TwinMode.STANDBY
        return TwinMode.FLUSH2

    return TwinMode.STANDBY
