#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Dict, List, Sequence

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from digital_twin.model import step_twin
from digital_twin.presets import site_presets
from digital_twin.types import DemandConfig, TwinConfig, TwinMode, TwinState


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Train a residual correction model on top of the digital twin. "
            "The model learns y_real(t+h) - y_twin(t+h) from recent sensor/actuator history and twin features."
        )
    )
    p.add_argument(
        "--input-glob",
        action="append",
        default=None,
        help="Input parquet glob(s). Repeatable. Default: data/raw/plc/*/date=*/data.parquet",
    )
    p.add_argument("--site", default="bluerock", help="Site key for presets and path filtering")
    p.add_argument("--start", default=None, help="UTC start (inclusive), ISO-8601")
    p.add_argument("--end", default=None, help="UTC end (exclusive), ISO-8601")
    p.add_argument("--timestamp-col", default="plctime")
    p.add_argument("--cadence", default="10s", help="Resample cadence for modeling")

    p.add_argument("--feed-level-col", default="feedtanklevel")
    p.add_argument("--product-level-col", default="prodtanklevel")
    p.add_argument("--flow-col", default="feedflow", help="Target flow sensor")
    p.add_argument("--demand-col", default="deliveryflow", help="Demand signal used as optional override")
    p.add_argument("--pressure-col", default="deliverypressure")

    p.add_argument(
        "--actuator-col",
        action="append",
        default=None,
        help=(
            "Actuator/PLC state columns to include as features. Repeatable. "
            "Default: wellpumprun,ropumprun,flushrun,deliveryrun,recyclevalveposition,ropressctrlvalveposition"
        ),
    )
    p.add_argument("--history-steps", type=int, default=18, help="Number of lagged timesteps in feature window")
    p.add_argument("--horizon-steps", type=int, default=6, help="Prediction horizon h in timesteps")

    p.add_argument("--use-real-demand", action="store_true", help="Drive twin with real demand col during rollout")
    p.add_argument("--train-frac", type=float, default=0.7, help="Chronological train split")
    p.add_argument("--val-frac", type=float, default=0.15, help="Chronological validation split")
    p.add_argument("--random-seed", type=int, default=42)
    p.add_argument("--max-iter", type=int, default=400)
    p.add_argument("--hidden-layers", default="64,32", help="MLP hidden layer sizes (comma-separated)")
    p.add_argument("--alpha", type=float, default=1e-4, help="MLP L2 regularization strength")
    p.add_argument("--out-dir", default="data/derived/twin_residual")
    p.add_argument("--prefix", default=None)
    return p


def _default_globs(globs: Sequence[str] | None) -> List[str]:
    return list(globs) if globs else ["data/raw/plc/*/date=*/data.parquet"]


def _expand(globs: Sequence[str]) -> List[Path]:
    out: List[Path] = []
    for g in globs:
        out.extend(Path(p) for p in sorted(glob.glob(g, recursive=True)))
    return sorted(set(out))


def _site_from_path(path: Path) -> str:
    parts = path.parts
    if "plc" not in parts:
        return ""
    i = parts.index("plc")
    if i + 1 >= len(parts):
        return ""
    raw = parts[i + 1].strip().lower()
    return raw.split("=", 1)[1] if raw.startswith("site=") else raw


def _as_binary(s: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(s):
        return s.astype(int)
    x = pd.to_numeric(s, errors="coerce")
    return (x.fillna(0.0) > 0).astype(int)


def _load_and_resample(
    files: Sequence[Path],
    *,
    site: str,
    timestamp_col: str,
    cols: Sequence[str],
    start: str | None,
    end: str | None,
    cadence: str,
) -> pd.DataFrame:
    site_norm = site.strip().lower()
    start_ts = pd.Timestamp(start, tz="UTC") if start else None
    end_ts = pd.Timestamp(end, tz="UTC") if end else None

    rows: List[pd.DataFrame] = []
    for fp in files:
        path_site = _site_from_path(fp)
        if path_site and path_site != site_norm:
            continue
        try:
            d = pd.read_parquet(fp)
        except Exception:
            continue
        if timestamp_col not in d.columns:
            continue
        keep = [timestamp_col] + [c for c in cols if c in d.columns]
        d = d[keep].copy()
        d["__ts"] = pd.to_datetime(d[timestamp_col], utc=True, errors="coerce")
        d = d[d["__ts"].notna()]
        if start_ts is not None:
            d = d[d["__ts"] >= start_ts]
        if end_ts is not None:
            d = d[d["__ts"] < end_ts]
        if d.empty:
            continue
        rows.append(d)

    if not rows:
        raise SystemExit("No rows found after file/site/time filtering")

    df = pd.concat(rows, ignore_index=True).sort_values("__ts").reset_index(drop=True)
    g = df.set_index("__ts")
    agg: Dict[str, str] = {c: "mean" for c in cols if c in df.columns}
    r = g.resample(cadence).agg(agg).dropna(how="all")
    r = r.reset_index().sort_values("__ts").reset_index(drop=True)
    return r


def _mode_one_hot(mode: TwinMode) -> Dict[str, int]:
    names = ["OFF", "STANDBY", "RO_RUNNING", "FLUSH1", "FLUSH2", "EMERGENCY_STOP"]
    return {f"sim_mode_{n.lower()}": int(mode.value == n) for n in names}


def _simulate_twin(
    *,
    df: pd.DataFrame,
    cfg: TwinConfig,
    demand_cfg: DemandConfig,
    feed_level_col: str,
    product_level_col: str,
    pressure_col: str,
    demand_col: str,
    use_real_demand: bool,
) -> pd.DataFrame:
    if df.empty:
        raise SystemExit("Cannot simulate twin on empty dataframe")

    first = df.iloc[0]
    feed0_pct = float(first[feed_level_col]) if pd.notna(first[feed_level_col]) else 65.0
    prod0_pct = float(first[product_level_col]) if pd.notna(first[product_level_col]) else 72.0
    pressure0 = float(first[pressure_col]) if pressure_col in df.columns and pd.notna(first[pressure_col]) else 52.0

    # If PLC starts with well pump running, honor that initial state until feed reaches high setpoint.
    well0_on = False
    if "wellpumprun" in df.columns:
        w0 = pd.to_numeric(pd.Series([first["wellpumprun"]]), errors="coerce").iloc[0]
        well0_on = bool(pd.notna(w0) and float(w0) > 0.0)

    refill0 = bool(feed0_pct <= cfg.feed_low_pct)
    if well0_on and feed0_pct < cfg.feed_high_pct:
        refill0 = True

    state = TwinState(
        t_seconds=0.0,
        mode=TwinMode.STANDBY,
        mode_elapsed_seconds=0.0,
        v_feed_gal=cfg.feed_capacity_gal * np.clip(feed0_pct / 100.0, 0.0, 1.0),
        v_product_gal=cfg.product_capacity_gal * np.clip(prod0_pct / 100.0, 0.0, 1.0),
        cond_proxy=cfg.cond_target_standby,
        pressure_psi=pressure0,
        refill_latch_on=refill0,
        ro_latch_on=prod0_pct <= cfg.product_low_pct,
    )

    rows: List[Dict[str, float | int]] = []
    first_row = {
        "sim_feed_pct": float(feed0_pct),
        "sim_product_pct": float(prod0_pct),
        "sim_pressure": float(pressure0),
        "sim_q_refill_gpm": 0.0,
        "sim_q_permeate_gpm": 0.0,
        "sim_q_feed_draw_gpm": 0.0,
        "sim_q_flush_gpm": 0.0,
        "sim_q_demand_gpm": 0.0,
        "sim_feedflow_gpm": 0.0,
    }
    first_row.update(_mode_one_hot(state.mode))
    rows.append(first_row)

    for i in range(1, len(df)):
        demand_override = None
        if use_real_demand and demand_col in df.columns and pd.notna(df.iloc[i - 1][demand_col]):
            demand_override = max(0.0, float(df.iloc[i - 1][demand_col]))
        r = step_twin(state=state, cfg=cfg, demand_cfg=demand_cfg, demand_override_gpm=demand_override)
        state = r.state
        row = {
            "sim_feed_pct": float(r.feed_pct),
            "sim_product_pct": float(r.product_pct),
            "sim_pressure": float(state.pressure_psi),
            "sim_q_refill_gpm": float(r.q_refill_gpm),
            "sim_q_permeate_gpm": float(r.q_permeate_gpm),
            "sim_q_feed_draw_gpm": float(r.q_feed_draw_gpm),
            "sim_q_flush_gpm": float(r.q_flush_gpm),
            "sim_q_demand_gpm": float(r.q_demand_gpm),
            "sim_feedflow_gpm": float(r.q_feed_draw_gpm + r.q_flush_gpm),
        }
        row.update(_mode_one_hot(state.mode))
        rows.append(row)

    return pd.DataFrame(rows)


def _parse_hidden_layers(s: str) -> tuple[int, ...]:
    vals = [int(x.strip()) for x in str(s).split(",") if x.strip()]
    if not vals:
        return (64, 32)
    return tuple(max(1, v) for v in vals)


def _metrics(y_true: np.ndarray, y_pred: np.ndarray, names: Sequence[str]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for i, name in enumerate(names):
        yt = y_true[:, i]
        yp = y_pred[:, i]
        out[name] = {
            "rmse": float(np.sqrt(mean_squared_error(yt, yp))),
            "mae": float(mean_absolute_error(yt, yp)),
            "r2": float(r2_score(yt, yp)),
        }
    return out


def main() -> None:
    args = build_argparser().parse_args()
    presets = site_presets()
    site = str(args.site).strip().lower()
    if site not in presets:
        raise SystemExit(f"Unknown --site: {site}")

    actuator_cols = (
        list(args.actuator_col)
        if args.actuator_col
        else [
            "wellpumprun",
            "ropumprun",
            "flushrun",
            "deliveryrun",
            "recyclevalveposition",
            "ropressctrlvalveposition",
        ]
    )
    target_real_cols = [str(args.feed_level_col), str(args.product_level_col), str(args.flow_col)]
    target_sim_cols = ["sim_feed_pct", "sim_product_pct", "sim_feedflow_gpm"]
    target_names = ["feed_level_pct", "product_level_pct", f"{args.flow_col}_gpm"]

    files = _expand(_default_globs(args.input_glob))
    if not files:
        raise SystemExit("No files matched --input-glob")

    use_cols = list(dict.fromkeys(target_real_cols + [args.demand_col, args.pressure_col] + actuator_cols))
    df = _load_and_resample(
        files,
        site=site,
        timestamp_col=str(args.timestamp_col),
        cols=use_cols,
        start=args.start,
        end=args.end,
        cadence=str(args.cadence),
    )
    if len(df) < 200:
        raise SystemExit("Not enough rows after resample; need at least 200 for stable training")

    for c in target_real_cols + [args.demand_col, args.pressure_col]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = np.nan
    for c in actuator_cols:
        if c not in df.columns:
            df[c] = 0.0
            continue
        if c.endswith("position"):
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0) / 100.0
        else:
            df[c] = _as_binary(df[c]).astype(float)

    df = df.sort_values("__ts").reset_index(drop=True)
    df[target_real_cols + [args.demand_col, args.pressure_col]] = df[
        target_real_cols + [args.demand_col, args.pressure_col]
    ].ffill().bfill()
    df = df.dropna(subset=target_real_cols).reset_index(drop=True)

    ps = presets[site]
    cfg = TwinConfig(
        dt_seconds=float(pd.to_timedelta(str(args.cadence)).total_seconds()),
        feed_capacity_gal=float(ps.get("feed_capacity_gal", TwinConfig.feed_capacity_gal)),
        product_capacity_gal=float(ps.get("product_capacity_gal", TwinConfig.product_capacity_gal)),
        feed_low_pct=float(ps.get("feed_low_pct", TwinConfig.feed_low_pct)),
        feed_high_pct=float(ps.get("feed_high_pct", TwinConfig.feed_high_pct)),
        product_low_pct=float(ps.get("product_low_pct", TwinConfig.product_low_pct)),
        product_high_pct=float(ps.get("product_high_pct", TwinConfig.product_high_pct)),
        well_refill_gpm=float(ps["well_refill_gpm"]),
        ro_permeate_gpm=float(ps["ro_permeate_gpm"]),
        ro_feed_draw_gpm=float(ps["ro_feed_draw_gpm"]),
        flush1_draw_gpm=float(ps["flush1_draw_gpm"]),
        flush2_draw_gpm=float(ps["flush2_draw_gpm"]),
        pressure_low_psi=float(ps.get("pressure_low_psi", TwinConfig.pressure_low_psi)),
        pressure_high_psi=float(ps.get("pressure_high_psi", TwinConfig.pressure_high_psi)),
    )
    demand_cfg = DemandConfig(
        base_gpm=float(ps["demand_base_gpm"]),
        day_amp_gpm=float(ps["demand_day_amp_gpm"]),
        week_amp_gpm=float(ps["demand_week_amp_gpm"]),
        day_phase_hours=float(ps["demand_day_phase_hours"]),
        week_phase_days=float(ps["demand_week_phase_days"]),
        harmonic_fit_json_path=str(ps.get("demand_harmonic_fit_json_path", "")).strip(),
    )

    sim = _simulate_twin(
        df=df,
        cfg=cfg,
        demand_cfg=demand_cfg,
        feed_level_col=str(args.feed_level_col),
        product_level_col=str(args.product_level_col),
        pressure_col=str(args.pressure_col),
        demand_col=str(args.demand_col),
        use_real_demand=bool(args.use_real_demand),
    )
    work = pd.concat([df[["__ts"] + target_real_cols + actuator_cols], sim], axis=1)

    hist = max(1, int(args.history_steps))
    h = max(1, int(args.horizon_steps))
    twin_context_cols = [
        "sim_feed_pct",
        "sim_product_pct",
        "sim_pressure",
        "sim_q_refill_gpm",
        "sim_q_permeate_gpm",
        "sim_q_feed_draw_gpm",
        "sim_q_flush_gpm",
        "sim_q_demand_gpm",
    ] + [c for c in sim.columns if c.startswith("sim_mode_")]

    feat_rows: List[Dict[str, float]] = []
    y_rows: List[np.ndarray] = []
    base_rows: List[np.ndarray] = []
    ts_rows: List[pd.Timestamp] = []

    n = len(work)
    for i in range(hist - 1, n - h):
        feat: Dict[str, float] = {}
        for lag in range(hist):
            j = i - lag
            for c in target_real_cols:
                feat[f"obs_{c}_lag{lag}"] = float(work.iloc[j][c])
            for c in actuator_cols:
                feat[f"act_{c}_lag{lag}"] = float(work.iloc[j][c])
            for c in twin_context_cols:
                feat[f"twin_{c}_lag{lag}"] = float(work.iloc[j][c])

        k = i + h
        for sim_col in target_sim_cols:
            seg = pd.to_numeric(work.iloc[i + 1 : k + 1][sim_col], errors="coerce")
            feat[f"twin_future_{sim_col}_mean_h{h}"] = float(seg.mean())
            feat[f"twin_future_{sim_col}_min_h{h}"] = float(seg.min())
            feat[f"twin_future_{sim_col}_max_h{h}"] = float(seg.max())
            feat[f"twin_future_{sim_col}_end_h{h}"] = float(work.iloc[k][sim_col])

        y_real = np.array([float(work.iloc[k][c]) for c in target_real_cols], dtype=float)
        y_twin = np.array([float(work.iloc[k][c]) for c in target_sim_cols], dtype=float)
        feat_rows.append(feat)
        y_rows.append(y_real - y_twin)
        base_rows.append(y_twin)
        ts_rows.append(pd.Timestamp(work.iloc[k]["__ts"]))

    if not feat_rows:
        raise SystemExit("No training samples after horizon/history trimming")

    X = pd.DataFrame(feat_rows).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y = np.vstack(y_rows)
    y_base = np.vstack(base_rows)
    ts = pd.Series(ts_rows, name="target_ts")

    n_samples = len(X)
    train_end = int(n_samples * float(args.train_frac))
    val_end = int(n_samples * (float(args.train_frac) + float(args.val_frac)))
    train_end = min(max(train_end, 1), n_samples - 2)
    val_end = min(max(val_end, train_end + 1), n_samples - 1)

    X_train = X.iloc[:train_end]
    X_val = X.iloc[train_end:val_end]
    X_test = X.iloc[val_end:]

    y_train = y[:train_end]
    y_val = y[train_end:val_end]
    y_test = y[val_end:]
    yb_train = y_base[:train_end]
    yb_val = y_base[train_end:val_end]
    yb_test = y_base[val_end:]

    model = Pipeline(
        steps=[
            ("scale", StandardScaler()),
            (
                "mlp",
                MLPRegressor(
                    hidden_layer_sizes=_parse_hidden_layers(args.hidden_layers),
                    activation="relu",
                    solver="adam",
                    alpha=float(args.alpha),
                    learning_rate="adaptive",
                    max_iter=int(args.max_iter),
                    random_state=int(args.random_seed),
                    early_stopping=True,
                    validation_fraction=0.15,
                    n_iter_no_change=12,
                ),
            ),
        ]
    )
    model.fit(X_train, y_train)

    pred_resid_val = model.predict(X_val)
    pred_resid_test = model.predict(X_test)

    pred_val = yb_val + pred_resid_val
    pred_test = yb_test + pred_resid_test
    true_val = yb_val + y_val
    true_test = yb_test + y_test

    metrics = {
        "val_base": _metrics(true_val, yb_val, target_names),
        "val_corrected": _metrics(true_val, pred_val, target_names),
        "test_base": _metrics(true_test, yb_test, target_names),
        "test_corrected": _metrics(true_test, pred_test, target_names),
    }
    global_residual_std = {
        target_names[i]: float(np.std(y_train[:, i])) for i in range(len(target_names))
    }
    metrics["train_residual_std"] = global_residual_std

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = args.prefix or f"{site}_residual_h{h}_w{hist}"
    model_path = out_dir / f"{name}.joblib"
    metrics_path = out_dir / f"{name}_metrics.json"
    preview_path = out_dir / f"{name}_test_preview.csv"

    bundle = {
        "model": model,
        "site": site,
        "cadence": str(args.cadence),
        "history_steps": hist,
        "horizon_steps": h,
        "target_real_cols": target_real_cols,
        "target_sim_cols": target_sim_cols,
        "target_names": target_names,
        "actuator_cols": actuator_cols,
        "feature_cols": list(X.columns),
        "twin_context_cols": twin_context_cols,
        "twin_config": cfg,
        "demand_config": demand_cfg,
        "train_residual_std": global_residual_std,
        "notes": "Predicts residual at t+h; corrected prediction = twin + residual",
    }
    joblib.dump(bundle, model_path)

    summary = {
        "site": site,
        "rows_raw": int(len(df)),
        "samples_model": int(n_samples),
        "train_samples": int(len(X_train)),
        "val_samples": int(len(X_val)),
        "test_samples": int(len(X_test)),
        "cadence": str(args.cadence),
        "history_steps": hist,
        "horizon_steps": h,
        "targets": target_names,
        "use_real_demand": bool(args.use_real_demand),
        "metrics": metrics,
    }
    metrics_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    preview = pd.DataFrame({"target_ts": ts.iloc[val_end:].values})
    for i, name_col in enumerate(target_names):
        preview[f"true_{name_col}"] = true_test[:, i]
        preview[f"base_{name_col}"] = yb_test[:, i]
        preview[f"corrected_{name_col}"] = pred_test[:, i]
        preview[f"pred_residual_{name_col}"] = pred_resid_test[:, i]
    preview.to_csv(preview_path, index=False)

    print(f"[OK] wrote {model_path}")
    print(f"[OK] wrote {metrics_path}")
    print(f"[OK] wrote {preview_path}")


if __name__ == "__main__":
    main()
