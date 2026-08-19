"""Fixed-size observation vector for the RL policy (PART L). Includes
forecast quantiles, tariff, flexibility state, comfort headroom and
community/peak-risk indicators -- everything the MPC also sees, just
flattened into a vector instead of fed to a solver."""
from __future__ import annotations

import numpy as np

from aethergrid.core.timestep import StepContext

OBS_DIM = 18


def _q(path: dict, h: int, q: float, default: float = 0.0) -> float:
    if not path:
        return default
    key = h if h in path else max(path.keys())
    return path[key].get(q, default)


def build_observation(ctx: StepContext, norm_load_kw: float = 300.0, norm_temp_c: float = 45.0) -> np.ndarray:
    r = ctx.resources
    s = ctx.state
    band = max(r.comfort_t_max - r.comfort_t_min, 0.1)
    headroom_up = np.clip((r.comfort_t_max - s.indoor_temp_c) / band, 0, 2)
    headroom_down = np.clip((s.indoor_temp_c - r.comfort_t_min) / band, 0, 2)

    batt_soc = s.battery_soc_kwh / max(r.battery_capacity_kwh, 1e-6)
    ts_soc = s.thermal_storage_soc_kwh / max(r.thermal_storage_capacity_kwh, 1e-6)
    dhw_soc = s.dhw_soc_kwh / max(r.dhw_storage_kwh, 1e-6)
    ev_present = float(ctx.horizon_ev_present[0]) if len(ctx.horizon_ev_present) else 0.0

    hour = ctx.timestamp.hour + ctx.timestamp.minute / 60.0
    load_q50 = _q(ctx.forecast_base_load_path, 1, 0.5) / norm_load_kw
    load_q90 = _q(ctx.forecast_base_load_path, 1, 0.9) / norm_load_kw
    solar_q50 = _q(ctx.forecast_solar_path, 1, 0.5) / norm_load_kw
    uncertainty_spread = (load_q90 - load_q50)

    rate_now = ctx.horizon_rates[0] if len(ctx.horizon_rates) else 0.0
    rate_norm = rate_now / 15.0
    rate_max_horizon = float(np.max(ctx.horizon_rates)) / 15.0 if len(ctx.horizon_rates) else rate_norm

    outdoor_temp_norm = (ctx.horizon_temp_out_c[0] if len(ctx.horizon_temp_out_c) else 25.0) / norm_temp_c
    coord_price = 0.0
    if ctx.coordination_price_per_kwh is not None and len(ctx.coordination_price_per_kwh):
        coord_price = float(ctx.coordination_price_per_kwh[0]) / 15.0

    obs = np.array([
        (s.indoor_temp_c - r.comfort_t_min) / band, headroom_up, headroom_down,
        batt_soc, ts_soc, dhw_soc, ev_present,
        np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24),
        rate_norm, rate_max_horizon, load_q50, load_q90, uncertainty_spread,
        solar_q50, outdoor_temp_norm, coord_price, ctx.prev_hvac_kw / max(r.hvac_capacity_kw, 1e-6),
    ], dtype=np.float32)
    return np.nan_to_num(obs, nan=0.0, posinf=1.0, neginf=-1.0)
