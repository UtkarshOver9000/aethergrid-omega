"""Deterministic adaptive controller -- the PART AV-sanctioned fallback
when PPO is unavailable or fails to train in-session ("PPO -> deterministic
adaptive controller"). Unlike rule_based_policy (fixed thresholds), this
one adapts its aggressiveness to the CURRENT forecast uncertainty
(q90-q50 spread at the 1-step horizon), so it still exercises the
"uncertainty-aware" story without needing a trained model at all."""
from __future__ import annotations

import numpy as np

from aethergrid.core.timestep import StepContext


def adaptive_fallback_policy(ctx: StepContext) -> dict:
    r = ctx.resources
    rates = ctx.horizon_rates
    rate_now = rates[0] if len(rates) else 0.0
    lo, hi = (np.quantile(rates, [0.33, 0.66]) if len(rates) > 2 else (rate_now, rate_now))

    h1 = ctx.forecast_base_load_path.get(1, {})
    uncertainty = 0.0
    if h1 and 0.9 in h1 and 0.5 in h1 and h1[0.5] > 1e-6:
        uncertainty = np.clip((h1[0.9] - h1[0.5]) / h1[0.5], 0, 1)
    aggressiveness = float(np.clip(0.4 + uncertainty, 0.4, 1.0))  # more uncertain -> hedge harder

    T = ctx.state.indoor_temp_c
    band_mid = (r.comfort_t_min + r.comfort_t_max) / 2
    if rate_now <= lo:
        hvac = r.hvac_capacity_kw * aggressiveness if T > r.comfort_t_min + 0.3 else 0.0
    elif rate_now >= hi:
        hvac = r.hvac_capacity_kw if T > r.comfort_t_max - 0.5 else 0.0
    else:
        hvac = r.hvac_capacity_kw * 0.5 if T > band_mid else 0.0

    soc_frac = ctx.state.battery_soc_kwh / r.battery_capacity_kwh if r.battery_capacity_kwh > 0 else 0.0
    batt_c = r.battery_power_kw * aggressiveness if (rate_now <= lo and soc_frac < r.battery_max_soc_frac) else 0.0
    batt_d = r.battery_power_kw if (rate_now >= hi and soc_frac > r.battery_min_soc_frac) else 0.0

    dhw = r.dhw_capacity_kw * aggressiveness if (rate_now <= lo and r.has_dhw) else \
        (float(ctx.horizon_dhw_draw_kw[0]) if len(ctx.horizon_dhw_draw_kw) else 0.0)
    ev_present = bool(ctx.horizon_ev_present[0]) if len(ctx.horizon_ev_present) else False
    ev = (r.ev_max_charge_kw * r.ev_count) if (ev_present and rate_now <= hi) else 0.0

    return {
        "hvac_kw": hvac, "battery_charge_kw": batt_c, "battery_discharge_kw": batt_d,
        "dhw_heat_kw": dhw, "ev_charge_kw": ev, "ts_charge_kw": 0.0, "ts_discharge_kw": 0.0,
    }
