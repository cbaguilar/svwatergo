# Discrete Digital Twin (Treatment Systems)

This module provides a first-pass discrete digital twin for your RO treatment topology:

- Feed tank hysteresis control (`60-70%`)
- Product tank hysteresis control (`65-80%`)
- RO production episodes
- End-of-run flush mode
- Exogenous periodic demand (daily + weekly)
- Pressure tank band maintenance (`42-62 psi`)

## Current model scope

- Modes: `OFF`, `STANDBY`, `RO_RUNNING`, `FLUSH1`, `FLUSH2`, `EMERGENCY_STOP`
- State: feed/product tank volume + conductivity proxy
- Flows: refill, RO permeate, RO feed draw, flush draw, demand
- Controller: threshold-based supervisory logic with flush timer

## Run a simulation

```bash
python3 python/analytics/digital_twin_sim.py \
  --hours 48 \
  --out-csv /tmp/twin_sim.csv \
  --out-meta /tmp/twin_sim_meta.json
```

## Suggested next calibration steps

1. Map LT% to tank gallons using site-specific capacities.
2. Fit `ro_permeate_gpm`, `ro_feed_draw_gpm`, and `flush_draw_gpm` from PLC/flow episodes.
3. Fit demand harmonics (`base`, `day_amp`, `week_amp`, phases) from inferred consumption.
4. Fit conductivity targets/time constants by mode from flush/produce transitions.
5. Add measured input overrides (pump/valve state, demand proxies) for data-assimilation mode.

## Residual Correction Model (Twin + Learned Error)

Use the twin as the structured baseline, then train a model on residuals:

`x_hat(t+h) = x_twin(t+h) + r(t+h)`

where `r(t+h)` is learned from recent observations + actuator history + twin context.

Train (example):

```bash
python3 python/analytics/fit_twin_residual_model.py \
  --site bluerock \
  --start 2026-02-01T00:00:00Z \
  --end 2026-03-01T00:00:00Z \
  --cadence 10s \
  --history-steps 18 \
  --horizon-steps 6 \
  --use-real-demand \
  --out-dir data/derived/twin_residual
```

Outputs:

- `*.joblib`: trained residual model bundle + feature spec + twin config
- `*_metrics.json`: base-vs-corrected validation/test metrics
- `*_test_preview.csv`: holdout predictions (`true`, `base`, `corrected`)
