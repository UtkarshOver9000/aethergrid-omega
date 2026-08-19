"""Rolling-horizon LP controller for a single building's flexible loads
(PART I/J -- Level-1 local controller). Fully linear: the RC thermal model,
storage dynamics and electrical balance are all linear in the decision
variables, so this stays an LP (PuLP + CBC), no MILP/binaries needed, which
keeps rolling re-optimization fast enough to run every step of a multi-day,
multi-building simulation.

HVAC is modeled as cooling-only (see optimization/objective.py:HVAC_COP) --
a documented simplification, not a hidden one.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pulp

from aethergrid.core.building import BuildingState
from aethergrid.core.resources import BuildingResources
from aethergrid.optimization.objective import HVAC_COP, SolveConfig


@dataclass
class MPCSolution:
    status: str
    hvac_kw: np.ndarray
    battery_charge_kw: np.ndarray
    battery_discharge_kw: np.ndarray
    dhw_heat_kw: np.ndarray
    ev_charge_kw: np.ndarray
    ts_charge_kw: np.ndarray
    ts_discharge_kw: np.ndarray
    grid_import_kw: np.ndarray
    grid_export_kw: np.ndarray
    indoor_temp_c: np.ndarray
    battery_soc_kwh: np.ndarray
    objective_value: float
    peak_kw: float
    comfort_violation_kwh: float

    def first_step_action(self) -> dict:
        return {
            "hvac_kw": float(self.hvac_kw[0]),
            "battery_charge_kw": float(self.battery_charge_kw[0]),
            "battery_discharge_kw": float(self.battery_discharge_kw[0]),
            "dhw_heat_kw": float(self.dhw_heat_kw[0]),
            "ev_charge_kw": float(self.ev_charge_kw[0]),
            "ts_charge_kw": float(self.ts_charge_kw[0]),
            "ts_discharge_kw": float(self.ts_discharge_kw[0]),
        }


def solve_building_horizon(
    resources: BuildingResources,
    state: BuildingState,
    base_load_kw: np.ndarray,
    solar_kw: np.ndarray,
    temp_out_c: np.ndarray,
    internal_gain_kw: np.ndarray,
    dhw_draw_kw: np.ndarray,
    ev_present: np.ndarray,
    ev_energy_target_kwh: float,
    rate_per_kwh: np.ndarray,
    dt_hours: float,
    config: SolveConfig,
    import_cap_kw: float | None = None,
    prev_hvac_kw: float = 0.0,
    coordination_price_per_kwh: np.ndarray | None = None,
) -> MPCSolution:
    H = len(base_load_kw)
    r = resources
    w = config.weights
    prob = pulp.LpProblem("building_mpc", pulp.LpMinimize)

    hvac = [pulp.LpVariable(f"hvac_{t}", 0, r.hvac_capacity_kw) for t in range(H)]
    batt_c = [pulp.LpVariable(f"batt_c_{t}", 0, r.battery_power_kw) for t in range(H)]
    batt_d = [pulp.LpVariable(f"batt_d_{t}", 0, r.battery_power_kw) for t in range(H)]
    dhw = [pulp.LpVariable(f"dhw_{t}", 0, r.dhw_capacity_kw) for t in range(H)]
    ev_c = [pulp.LpVariable(f"ev_{t}", 0, max(r.ev_max_charge_kw * r.ev_count, 0.0)) for t in range(H)]
    ts_c = [pulp.LpVariable(f"ts_c_{t}", 0, r.thermal_storage_power_kw) for t in range(H)]
    ts_d = [pulp.LpVariable(f"ts_d_{t}", 0, r.thermal_storage_power_kw) for t in range(H)]
    imp = [pulp.LpVariable(f"imp_{t}", 0, import_cap_kw) for t in range(H)]
    exp = [pulp.LpVariable(f"exp_{t}", 0) for t in range(H)]

    T = [pulp.LpVariable(f"T_{t}", r.hard_t_min, r.hard_t_max) for t in range(H + 1)]
    soc = [pulp.LpVariable(f"soc_{t}", r.battery_min_soc_frac * r.battery_capacity_kwh,
                            r.battery_max_soc_frac * r.battery_capacity_kwh) for t in range(H + 1)]
    ts_soc = [pulp.LpVariable(f"ts_soc_{t}", 0, r.thermal_storage_capacity_kwh) for t in range(H + 1)]
    dhw_soc = [pulp.LpVariable(f"dhw_soc_{t}", 0, r.dhw_storage_kwh) for t in range(H + 1)]
    ev_soc_cap = max(r.ev_capacity_kwh * r.ev_count, 1e-6)
    ev_soc = [pulp.LpVariable(f"ev_soc_{t}", 0, ev_soc_cap) for t in range(H + 1)]

    slack_hi = [pulp.LpVariable(f"slack_hi_{t}", 0) for t in range(H)]
    slack_lo = [pulp.LpVariable(f"slack_lo_{t}", 0) for t in range(H)]
    switch_aux = [pulp.LpVariable(f"switch_{t}", 0) for t in range(H)]
    peak = pulp.LpVariable("peak", 0)
    reserve_deficit = pulp.LpVariable("reserve_deficit", 0)

    prob += T[0] == state.indoor_temp_c
    prob += soc[0] == state.battery_soc_kwh
    prob += ts_soc[0] == state.thermal_storage_soc_kwh
    prob += dhw_soc[0] == state.dhw_soc_kwh
    prob += ev_soc[0] == state.ev_soc_kwh

    eff = r.battery_round_trip_eff ** 0.5
    for t in range(H):
        prob += T[t + 1] == T[t] + (dt_hours / max(r.thermal_C, 1e-6)) * (
            (temp_out_c[t] - T[t]) / max(r.thermal_R, 1e-6) + internal_gain_kw[t] - HVAC_COP * hvac[t]
        )
        prob += T[t] <= r.comfort_t_max + slack_hi[t]
        prob += T[t] >= r.comfort_t_min - slack_lo[t]

        prob += soc[t + 1] == soc[t] + batt_c[t] * eff * dt_hours - (batt_d[t] / eff) * dt_hours
        prob += ts_soc[t + 1] == ts_soc[t] * (1 - r.thermal_storage_loss_frac_per_step) + (ts_c[t] - ts_d[t]) * dt_hours
        prob += dhw_soc[t + 1] == dhw_soc[t] + (dhw[t] - dhw_draw_kw[t]) * dt_hours
        if ev_present[t]:
            prob += ev_soc[t + 1] == ev_soc[t] + ev_c[t] * dt_hours
        else:
            prob += ev_soc[t + 1] == ev_soc[t]
            prob += ev_c[t] == 0

        prob += (imp[t] - exp[t] == base_load_kw[t] + hvac[t] + dhw[t] + ev_c[t]
                 + batt_c[t] - batt_d[t] + ts_c[t] - ts_d[t] - solar_kw[t])
        prob += peak >= imp[t]

        prev = hvac[t - 1] if t > 0 else prev_hvac_kw
        prob += switch_aux[t] >= hvac[t] - prev
        prob += switch_aux[t] >= prev - hvac[t]

    if r.has_ev and ev_energy_target_kwh > 0:
        last_present = [t for t in range(H) if ev_present[t]]
        if last_present:
            departure_idx = last_present[-1] + 1
            prob += ev_soc[departure_idx] >= min(ev_energy_target_kwh, ev_soc_cap)

    prob += reserve_deficit >= config.reserve_target_frac * r.battery_capacity_kwh - soc[H]

    # Per-horizon demand-charge-risk proxy: currency/kW rate derived from the
    # tariff's actual demand charge, so this term is grounded in real tariff
    # economics rather than an arbitrary scale (the true billed peak is still
    # computed once, after the fact, by BillEngine -- this is only a risk signal).
    demand_rate = config.demand_charge_per_kva / max(config.assumed_power_factor, 1e-6)

    energy_cost = pulp.lpSum(imp[t] * rate_per_kwh[t] * dt_hours for t in range(H))
    carbon_cost = pulp.lpSum(imp[t] * dt_hours * config.carbon_kg_per_kwh for t in range(H))
    comfort_penalty = pulp.lpSum(slack_hi[t] + slack_lo[t] for t in range(H))
    switching_penalty = pulp.lpSum(switch_aux)
    degradation_cost = pulp.lpSum(batt_c[t] + batt_d[t] for t in range(H)) * dt_hours

    coordination_cost = 0
    if coordination_price_per_kwh is not None:
        # Level-2 community coordination signal: an externally supplied
        # per-step price added on top of the tariff, letting a community
        # coordinator discourage this building from importing heavily at
        # the same time as its neighbors (PART K / PART AY dynamic edges)
        # without needing a single joint multi-building LP.
        coordination_cost = pulp.lpSum(imp[t] * coordination_price_per_kwh[t] * dt_hours for t in range(H))

    prob += (
        w.energy_cost * energy_cost
        + w.demand_charge_risk * peak * demand_rate
        + w.carbon_cost * carbon_cost
        + w.comfort_penalty * comfort_penalty
        + w.switching_penalty * switching_penalty
        + w.degradation_cost * degradation_cost
        + w.resilience_penalty * reserve_deficit
        + w.connection_cost * coordination_cost
    )

    solver = pulp.PULP_CBC_CMD(msg=False)
    prob.solve(solver)
    status = pulp.LpStatus[prob.status]

    def val(v):
        x = v.value()
        return 0.0 if x is None else x

    return MPCSolution(
        status=status,
        hvac_kw=np.array([val(x) for x in hvac]),
        battery_charge_kw=np.array([val(x) for x in batt_c]),
        battery_discharge_kw=np.array([val(x) for x in batt_d]),
        dhw_heat_kw=np.array([val(x) for x in dhw]),
        ev_charge_kw=np.array([val(x) for x in ev_c]),
        ts_charge_kw=np.array([val(x) for x in ts_c]),
        ts_discharge_kw=np.array([val(x) for x in ts_d]),
        grid_import_kw=np.array([val(x) for x in imp]),
        grid_export_kw=np.array([val(x) for x in exp]),
        indoor_temp_c=np.array([val(x) for x in T]),
        battery_soc_kwh=np.array([val(x) for x in soc]),
        objective_value=pulp.value(prob.objective) or 0.0,
        peak_kw=val(peak),
        comfort_violation_kwh=sum(val(x) for x in slack_hi) + sum(val(x) for x in slack_lo),
    )
