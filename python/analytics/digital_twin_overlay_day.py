#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from digital_twin.model import step_twin
from digital_twin.presets import site_presets
from digital_twin.types import DemandConfig, TwinConfig, TwinMode, TwinState


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run digital twin for one day and overlay simulated traces with real PLC data."
    )
    p.add_argument("--site", default="bluerock", help="Site key for presets and path discovery")
    p.add_argument("--day", required=True, help="UTC day in YYYY-MM-DD")
    p.add_argument("--plc-file", default=None, help="Optional explicit day parquet path")

    p.add_argument("--timestamp-col", default="plctime")
    p.add_argument("--feed-level-col", default="feedtanklevel")
    p.add_argument("--product-level-col", default="prodtanklevel")
    p.add_argument("--pressure-col", default="deliverypressure")
    p.add_argument("--flow-col", default="feedflow", help="Real flow series to overlay (e.g. feedflow/deliveryflow)")
    p.add_argument("--demand-col", default="deliveryflow", help="PLC column used as real demand when --use-real-demand is enabled")
    p.add_argument(
        "--sim-flow",
        default="feed_draw",
        choices=["feed_draw", "permeate", "demand", "refill", "flush", "delivery_pulse"],
        help="Which simulated flow signal to compare against real --flow-col",
    )
    p.add_argument(
        "--delivery-pump-gpm",
        type=float,
        default=12.3,
        help="Instantaneous delivery-pump flow when pressure pump is ON (used by sim-flow=delivery_pulse).",
    )
    p.add_argument("--no-pressure", action="store_true", help="Hide pressure subplot")
    p.add_argument(
        "--flow-display-agg-hours",
        type=float,
        default=0.0,
        help="If > 0, plot real/sim flow as mean over this many hours (display only).",
    )
    p.add_argument("--use-real-demand", action="store_true", help="Drive the twin with real PLC demand from --demand-col")
    p.add_argument(
        "--real-demand-max-gap-minutes",
        type=float,
        default=20.0,
        help="Max timestamp gap (minutes) for nearest demand lookup before fallback fill.",
    )

    p.add_argument("--feed-cap-gal", type=float, default=4576.0)
    p.add_argument("--product-cap-gal", type=float, default=5000.0)

    p.add_argument("--dt-seconds", type=float, default=2.0)
    p.add_argument("--feed-low-pct", type=float, default=65.0)
    p.add_argument("--feed-high-pct", type=float, default=80.0)
    p.add_argument("--product-low-pct", type=float, default=60.0)
    p.add_argument("--product-high-pct", type=float, default=75.0)

    p.add_argument("--well-refill-gpm", type=float, default=None)
    p.add_argument("--ro-permeate-gpm", type=float, default=None)
    p.add_argument("--ro-feed-draw-gpm", type=float, default=None)
    p.add_argument("--flush1-draw-gpm", type=float, default=None)
    p.add_argument("--flush2-draw-gpm", type=float, default=None)
    p.add_argument("--demand-base-gpm", type=float, default=None)
    p.add_argument("--demand-day-amp-gpm", type=float, default=None)
    p.add_argument("--demand-week-amp-gpm", type=float, default=None)
    p.add_argument("--demand-day-phase-hours", type=float, default=None)
    p.add_argument("--demand-week-phase-days", type=float, default=None)
    p.add_argument("--demand-fit-json", default=None, help="Harmonic fit JSON from fit_harmonic_demand.py")
    p.add_argument("--start-ts-utc", default=None, help="UTC anchor for demand alignment; defaults to first PLC row")

    p.add_argument("--out-dir", default="data/derived/digital_twin")
    p.add_argument("--prefix", default=None)
    return p


def _find_default_plc_file(site: str, day: str) -> Path:
    candidates = [
        Path(f"data/raw/plc/{site}/date={day}/data.parquet"),
        Path(f"data/raw/plc/site={site}/date={day}/data.parquet"),
    ]
    for c in candidates:
        if c.exists():
            return c
    raise SystemExit(f"Could not find day parquet for site={site} day={day}. Tried: {candidates}")


def _mode_from_row(row: pd.Series) -> TwinMode:
    ro = bool(row.get("ropumprun", False))
    flush = bool(row.get("flushrun", False))
    if flush:
        return TwinMode.FLUSH1
    if ro:
        return TwinMode.RO_RUNNING
    return TwinMode.STANDBY


def _bool_from_row(row: pd.Series, key: str) -> bool:
    v = row.get(key, False)
    try:
        if pd.isna(v):
            return False
    except Exception:
        pass
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v) > 0.0
    s = str(v).strip().lower()
    return s in {"1", "true", "on", "yes", "running", "open"}


def _sim_flow_value(sim_flow: str, r, delivery_pump_gpm: float) -> float:
    if sim_flow == "feed_draw":
        return float(r.q_feed_draw_gpm)
    if sim_flow == "permeate":
        return float(r.q_permeate_gpm)
    if sim_flow == "demand":
        return float(r.q_demand_gpm)
    if sim_flow == "refill":
        return float(r.q_refill_gpm)
    if sim_flow == "flush":
        return float(r.q_flush_gpm)
    if sim_flow == "delivery_pulse":
        return float(delivery_pump_gpm if int(r.pressure_pump_on) > 0 else 0.0)
    return float(r.q_feed_draw_gpm)


def _build_real_demand_override(
    *,
    df: pd.DataFrame,
    demand_col: str,
    sim_times: pd.DatetimeIndex,
    dt_seconds: float,
    max_gap_minutes: float,
) -> pd.Series:
    if demand_col not in df.columns:
        raise SystemExit(f"--use-real-demand requested but demand column not found: {demand_col}")
    src = df[["__ts", demand_col]].copy()
    src[demand_col] = pd.to_numeric(src[demand_col], errors="coerce")
    src = src[src["__ts"].notna() & src[demand_col].notna()].sort_values("__ts")
    if src.empty:
        raise SystemExit(f"--use-real-demand requested but no valid rows in demand column: {demand_col}")

    src_s = src.set_index("__ts")[demand_col].sort_index()
    # Average real demand over each simulation time-step window.
    dt = pd.to_timedelta(float(dt_seconds), unit="s")
    step_mean = src_s.resample(dt, origin=sim_times[0], label="left", closed="left").mean()
    out = step_mean.reindex(sim_times)

    # Fill sparse bins using nearest observed sample within tolerance, then ffill/bfill.
    target = pd.DataFrame({"__ts": sim_times})
    near = pd.merge_asof(
        target,
        src.rename(columns={demand_col: "demand_gpm"}),
        on="__ts",
        direction="nearest",
        tolerance=pd.to_timedelta(float(max(0.0, max_gap_minutes)), unit="m"),
    )["demand_gpm"]
    near.index = sim_times
    out = out.fillna(near).ffill().bfill().fillna(0.0).clip(lower=0.0)
    return out


def run() -> None:
    args = build_argparser().parse_args()
    site = str(args.site).strip().lower()

    plc_path = Path(args.plc_file) if args.plc_file else _find_default_plc_file(site, args.day)
    df = pd.read_parquet(plc_path)

    required = [args.timestamp_col, args.feed_level_col, args.product_level_col, args.flow_col]
    if not args.no_pressure:
        required.append(args.pressure_col)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing required PLC columns: {missing}")

    df = df.copy()
    df["__ts"] = pd.to_datetime(df[args.timestamp_col], utc=True, errors="coerce")
    for c in [args.feed_level_col, args.product_level_col, args.flow_col]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if args.demand_col in df.columns:
        df[args.demand_col] = pd.to_numeric(df[args.demand_col], errors="coerce")
    if args.pressure_col in df.columns:
        df[args.pressure_col] = pd.to_numeric(df[args.pressure_col], errors="coerce")

    for b in ["ropumprun", "flushrun", "wellpumprun"]:
        if b in df.columns:
            v = df[b]
            if pd.api.types.is_bool_dtype(v):
                df[b] = v
            else:
                df[b] = pd.to_numeric(v, errors="coerce").fillna(0).astype(int) > 0
        else:
            df[b] = False

    df = df[df["__ts"].notna()].sort_values("__ts").reset_index(drop=True)
    df = df[df["__ts"].dt.strftime("%Y-%m-%d") == args.day].reset_index(drop=True)
    if df.empty:
        raise SystemExit("No rows for requested day")

    first = df.iloc[0]
    t0 = df["__ts"].iloc[0]

    presets = site_presets()
    if site not in presets:
        raise SystemExit(f"Unknown site preset: {site}")
    ps = presets[site]

    def v(name: str, override: Optional[float]) -> float:
        if override is not None:
            return float(override)
        return float(ps[name])

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
    )
    demand_cfg = DemandConfig(
        base_gpm=v("demand_base_gpm", args.demand_base_gpm),
        day_amp_gpm=v("demand_day_amp_gpm", args.demand_day_amp_gpm),
        week_amp_gpm=v("demand_week_amp_gpm", args.demand_week_amp_gpm),
        harmonic_fit_json_path=(
            str(args.demand_fit_json).strip()
            if args.demand_fit_json is not None
            else str(ps.get("demand_harmonic_fit_json_path", "")).strip()
        ),
        start_ts_utc=(str(args.start_ts_utc).strip() if args.start_ts_utc is not None else str(t0.isoformat())),
        day_phase_hours=(
            float(args.demand_day_phase_hours)
            if args.demand_day_phase_hours is not None
            else float(ps.get("demand_day_phase_hours", 15.0))
        ),
        week_phase_days=(
            float(args.demand_week_phase_days)
            if args.demand_week_phase_days is not None
            else float(ps.get("demand_week_phase_days", 2.0))
        ),
    )

    init_mode = _mode_from_row(first)
    pressure0 = float(first[args.pressure_col]) if args.pressure_col in df.columns and pd.notna(first[args.pressure_col]) else 52.0
    # Infer initial latch state from real actuator state first, then thresholds as fallback.
    real_well_on = _bool_from_row(first, "wellpumprun")
    real_ro_on = _bool_from_row(first, "ropumprun")
    refill_latch_on0 = real_well_on or (float(first[args.feed_level_col]) <= cfg.feed_low_pct)
    ro_latch_on0 = real_ro_on or (float(first[args.product_level_col]) <= cfg.product_low_pct)

    state = TwinState(
        t_seconds=0.0,
        mode=init_mode,
        mode_elapsed_seconds=0.0,
        v_feed_gal=cfg.feed_capacity_gal * (float(first[args.feed_level_col]) / 100.0),
        v_product_gal=cfg.product_capacity_gal * (float(first[args.product_level_col]) / 100.0),
        cond_proxy=cfg.cond_target_ro_running if init_mode == TwinMode.RO_RUNNING else cfg.cond_target_standby,
        pressure_psi=pressure0,
        refill_latch_on=refill_latch_on0,
        ro_latch_on=ro_latch_on0,
    )

    t1 = df["__ts"].iloc[-1]
    horizon_s = max(0.0, (t1 - t0).total_seconds())
    n_steps = int(horizon_s / cfg.dt_seconds)
    sim_times = pd.date_range(
        start=t0,
        periods=n_steps + 1,
        freq=pd.to_timedelta(cfg.dt_seconds, unit="s"),
        tz="UTC",
    )
    real_demand_override = None
    if args.use_real_demand:
        real_demand_override = _build_real_demand_override(
            df=df,
            demand_col=str(args.demand_col),
            sim_times=sim_times,
            dt_seconds=cfg.dt_seconds,
            max_gap_minutes=float(args.real_demand_max_gap_minutes),
        )

    sim_rows = [
        {
            "__ts": t0,
            "sim_feed_pct": 100.0 * state.v_feed_gal / cfg.feed_capacity_gal,
            "sim_product_pct": 100.0 * state.v_product_gal / cfg.product_capacity_gal,
            "sim_pressure": state.pressure_psi,
            "sim_flow": 0.0,
            "sim_mode": state.mode.value,
        }
    ]
    for i in range(n_steps):
        demand_override = None
        if real_demand_override is not None:
            demand_override = float(real_demand_override.iloc[min(i, len(real_demand_override) - 1)])
        r = step_twin(state=state, cfg=cfg, demand_cfg=demand_cfg, demand_override_gpm=demand_override)
        state = r.state
        sim_rows.append(
            {
                "__ts": t0 + pd.to_timedelta(state.t_seconds, unit="s"),
                "sim_feed_pct": r.feed_pct,
                "sim_product_pct": r.product_pct,
                "sim_pressure": state.pressure_psi,
                "sim_flow": _sim_flow_value(args.sim_flow, r, float(args.delivery_pump_gpm)),
                "sim_mode": state.mode.value,
            }
        )

    sim_df = pd.DataFrame(sim_rows).sort_values("__ts").reset_index(drop=True)

    real_cols = ["__ts", args.feed_level_col, args.product_level_col, args.flow_col]
    if args.pressure_col in df.columns:
        real_cols.append(args.pressure_col)
    real_df = df[real_cols].copy().rename(
        columns={
            args.feed_level_col: "real_feed_pct",
            args.product_level_col: "real_product_pct",
            args.pressure_col: "real_pressure",
            args.flow_col: "real_flow",
        }
    )

    merged = pd.merge_asof(real_df.sort_values("__ts"), sim_df.sort_values("__ts"), on="__ts", direction="nearest")

    flow_plot_df = merged
    if float(args.flow_display_agg_hours) > 0.0:
        rule = f"{float(args.flow_display_agg_hours):g}h"
        flow_plot_df = (
            merged.set_index("__ts")[["real_flow", "sim_flow"]]
            .resample(rule)
            .mean()
            .dropna(how="all")
            .reset_index()
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix or f"{site}_{args.day}_overlay"
    out_csv = out_dir / f"{prefix}.csv"
    out_png = out_dir / f"{prefix}.png"
    merged.to_csv(out_csv, index=False)

    import matplotlib.pyplot as plt

    nrows = 2 if args.no_pressure else 3
    fig, axs = plt.subplots(nrows, 1, figsize=(11, 7 if args.no_pressure else 8), sharex=True, dpi=130)
    if nrows == 2:
        ax_tank, ax_flow = axs
    else:
        ax_tank, ax_pressure, ax_flow = axs

    ax_tank.plot(merged["__ts"], merged["real_feed_pct"], label="Real Feed %", lw=1.6)
    ax_tank.plot(merged["__ts"], merged["sim_feed_pct"], label="Sim Feed %", lw=1.3)
    ax_tank.plot(merged["__ts"], merged["real_product_pct"], label="Real Product %", lw=1.6)
    ax_tank.plot(merged["__ts"], merged["sim_product_pct"], label="Sim Product %", lw=1.3)
    ax_tank.set_ylabel("Tank %")
    ax_tank.grid(alpha=0.25)
    ax_tank.legend(loc="best", ncol=2, fontsize=8)

    if not args.no_pressure and "real_pressure" in merged.columns:
        ax_pressure.plot(merged["__ts"], merged["real_pressure"], label="Real Pressure", lw=1.6)
        ax_pressure.plot(merged["__ts"], merged["sim_pressure"], label="Sim Pressure", lw=1.3)
        ax_pressure.set_ylabel("Pressure")
        ax_pressure.grid(alpha=0.25)
        ax_pressure.legend(loc="best")

    flow_label_suffix = (
        f" ({float(args.flow_display_agg_hours):g}h mean)"
        if float(args.flow_display_agg_hours) > 0.0
        else ""
    )
    ax_flow.plot(
        flow_plot_df["__ts"],
        flow_plot_df["real_flow"],
        label=f"Real {args.flow_col}{flow_label_suffix}",
        lw=1.6,
    )
    ax_flow.plot(
        flow_plot_df["__ts"],
        flow_plot_df["sim_flow"],
        label=f"Sim {args.sim_flow}{flow_label_suffix}",
        lw=1.3,
    )
    ax_flow.set_ylabel("Flow (gpm)")
    ax_flow.set_xlabel("Time (UTC)")
    ax_flow.grid(alpha=0.25)
    ax_flow.legend(loc="best")

    fig.suptitle(f"{site} digital twin overlay for {args.day}")
    fig.tight_layout()
    fig.savefig(out_png)

    print(
        "[start_compare]"
        f" real_feed_pct={float(first[args.feed_level_col]):.3f}"
        f" sim_feed_pct={sim_rows[0]['sim_feed_pct']:.3f}"
        f" real_product_pct={float(first[args.product_level_col]):.3f}"
        f" sim_product_pct={sim_rows[0]['sim_product_pct']:.3f}"
        f" real_pressure={pressure0:.3f}"
        f" sim_pressure={sim_rows[0]['sim_pressure']:.3f}"
        f" real_mode={_mode_from_row(first).value}"
        f" sim_mode={sim_rows[0]['sim_mode']}"
        f" real_wellpumprun={int(real_well_on)}"
        f" init_refill_latch_on={int(refill_latch_on0)}"
        f" real_ropumprun={int(real_ro_on)}"
        f" init_ro_latch_on={int(ro_latch_on0)}"
        f" use_real_demand={int(bool(args.use_real_demand))}"
        f" demand_col={args.demand_col}"
    )
    print(f"[OK] plc_file={plc_path}")
    print(f"[OK] wrote {out_csv}")
    print(f"[OK] wrote {out_png}")


if __name__ == "__main__":
    run()
