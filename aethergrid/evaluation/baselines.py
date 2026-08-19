"""The eight required baseline controllers (PART V). Each is a `PolicyFn`
(core/timestep.py) -- a pure function of the current StepContext to a
proposed (unshielded) action. `oracle` lives in evaluation/oracle.py since
it needs a different calling convention (perfect foresight, single-shot).
"""
from __future__ import annotations

import numpy as np

from aethergrid.core.timestep import StepContext
from aethergrid.optimization.chance_constraints import build_horizon_arrays
from aethergrid.optimization.mpc import solve_building_horizon
from aethergrid.optimization.objective import SolveConfig


def no_control_policy(ctx: StepContext) -> dict:
    """Business-as-usual: a plain thermostat for HVAC, no strategic use of
    battery/DHW/EV flexibility at all."""
    r = ctx.resources
    T = ctx.state.indoor_temp_c
    hvac = r.hvac_capacity_kw if T > (r.comfort_t_min + r.comfort_t_max) / 2 else 0.0
    ev_present = bool(ctx.horizon_ev_present[0]) if len(ctx.horizon_ev_present) else False
    return {
        "hvac_kw": hvac, "battery_charge_kw": 0.0, "battery_discharge_kw": 0.0,
        "dhw_heat_kw": float(ctx.horizon_dhw_draw_kw[0]) if len(ctx.horizon_dhw_draw_kw) else 0.0,
        "ev_charge_kw": (r.ev_max_charge_kw * r.ev_count) if ev_present else 0.0,
        "ts_charge_kw": 0.0, "ts_discharge_kw": 0.0,
    }


def rule_based_policy(ctx: StepContext) -> dict:
    """Simple, explainable heuristics: precool/precharge in cheap hours,
    discharge/coast in expensive hours. No forecasting model, no
    optimization -- a deterministic, human-legible baseline."""
    r = ctx.resources
    rates = ctx.horizon_rates
    rate_now = rates[0] if len(rates) else 0.0
    lo, hi = (np.quantile(rates, [0.33, 0.66]) if len(rates) > 2 else (rate_now, rate_now))

    T = ctx.state.indoor_temp_c
    band_mid = (r.comfort_t_min + r.comfort_t_max) / 2
    if rate_now <= lo:
        hvac = r.hvac_capacity_kw * 0.6 if T > r.comfort_t_min + 0.3 else 0.0  # precool
    elif rate_now >= hi:
        hvac = r.hvac_capacity_kw if T > r.comfort_t_max - 0.3 else 0.0  # coast, only if near ceiling
    else:
        hvac = r.hvac_capacity_kw * 0.5 if T > band_mid else 0.0

    soc_frac = ctx.state.battery_soc_kwh / r.battery_capacity_kwh if r.battery_capacity_kwh > 0 else 0.0
    batt_c = r.battery_power_kw if (rate_now <= lo and soc_frac < r.battery_max_soc_frac) else 0.0
    batt_d = r.battery_power_kw if (rate_now >= hi and soc_frac > r.battery_min_soc_frac) else 0.0

    dhw = r.dhw_capacity_kw if (rate_now <= lo and r.has_dhw) else float(ctx.horizon_dhw_draw_kw[0]) if len(ctx.horizon_dhw_draw_kw) else 0.0
    ev_present = bool(ctx.horizon_ev_present[0]) if len(ctx.horizon_ev_present) else False
    ev = (r.ev_max_charge_kw * r.ev_count) if (ev_present and rate_now <= hi) else 0.0

    return {
        "hvac_kw": hvac, "battery_charge_kw": batt_c, "battery_discharge_kw": batt_d,
        "dhw_heat_kw": dhw, "ev_charge_kw": ev, "ts_charge_kw": 0.0, "ts_discharge_kw": 0.0,
    }


def _mpc_policy(ctx: StepContext, mode: str) -> dict:
    base_arr, solar_arr = build_horizon_arrays(
        ctx.forecast_base_load_path, ctx.forecast_solar_path, ctx.horizon_steps, mode, ctx.risk_level,
    )
    cfg = SolveConfig(
        weights=ctx.weights, carbon_kg_per_kwh=ctx.carbon_kg_per_kwh,
        demand_charge_per_kva=ctx.demand_charge_per_kva,
    )
    sol = solve_building_horizon(
        ctx.resources, ctx.state, base_arr, solar_arr, ctx.horizon_temp_out_c,
        ctx.horizon_internal_gain_kw, ctx.horizon_dhw_draw_kw, ctx.horizon_ev_present,
        ctx.ev_energy_target_kwh, ctx.horizon_rates, ctx.dt_hours, cfg,
        import_cap_kw=ctx.import_cap_kw, prev_hvac_kw=ctx.prev_hvac_kw,
        coordination_price_per_kwh=ctx.coordination_price_per_kwh,
    )
    return sol.first_step_action()


def mean_mpc_policy(ctx: StepContext) -> dict:
    return _mpc_policy(ctx, "mean")


def quantile_mpc_policy(ctx: StepContext) -> dict:
    return _mpc_policy(ctx, "quantile")


def hierarchical_hybrid_policy(ctx: StepContext) -> dict:
    """Level-1 quantile-aware MPC + Level-2/3 coordination signal (the
    coordination_price_per_kwh field on StepContext, populated by the
    community/network coordinator in simulation/colony.py /
    graph/graph.py rather than here)."""
    return _mpc_policy(ctx, "quantile")


BASELINE_POLICIES = {
    "no_control": no_control_policy,
    "rule_based": rule_based_policy,
    "mean_mpc": mean_mpc_policy,
    "quantile_mpc": quantile_mpc_policy,
    "hierarchical_hybrid": hierarchical_hybrid_policy,
}
