"""Colony / microgrid orchestration (PART K Level-2, PART Z resilience).

The colony's buildings share ONE constrained grid connection point
(`world.resources.grid_capacity_kw`, or zero during an outage). Each step,
every building's controller first proposes what it WOULD import if
unconstrained; the Level-2 community coordinator then rations the shared
capacity by the explicit priority hierarchy:

    CRITICAL LOAD > SAFETY > COMFORT > ECONOMIC OPTIMIZATION > OPTIONAL LOAD

implemented as strict descending-criticality allocation of whatever import
capacity is available -- the same mechanism whether the constraint is a
tight microgrid connection or a full outage (capacity=0). This is what
produces graceful degradation instead of an undifferentiated blackout.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from aethergrid.core.building import Building
from aethergrid.core.timestep import (
    PolicyFn, SimulationSeries, advance_physics, build_step_context, shield_action,
)
from aethergrid.core.world import World
from aethergrid.schemas.experiment import ObjectiveWeights


def allocate_capacity(desired_import_kw: dict[str, float], capacity_kw: float | None,
                       criticality: dict[str, float]) -> dict[str, float]:
    """Ration shared import capacity by descending criticality. Buildings
    with non-positive desired import (net exporters) are excluded from
    rationing entirely -- they don't compete for the shared connection."""
    positive = {b: v for b, v in desired_import_kw.items() if v > 0}
    if capacity_kw is None or sum(positive.values()) <= capacity_kw:
        return dict(desired_import_kw)
    remaining = capacity_kw
    allocation = dict(desired_import_kw)
    for bid in sorted(positive, key=lambda b: -criticality[b]):
        give = min(positive[bid], remaining)
        allocation[bid] = give
        remaining -= give
    return allocation


def simulate_colony(
    world: World,
    policies: dict[str, PolicyFn],
    forecast_fns: dict[str, tuple],   # {building_id: (base_load_fn, solar_fn)}
    criticality: dict[str, float],
    weights: ObjectiveWeights,
    carbon_kg_per_kwh: float,
    risk_level: float = 0.05,
    horizon_steps: int = 32,
    outage_mask: np.ndarray | None = None,
    reset_state: bool = True,
) -> dict[str, SimulationSeries]:
    n = world.n_steps
    buildings = world.buildings
    if reset_state:
        for b in buildings.values():
            b.state = b._init_state()

    out = {bid: {k: np.zeros(n) for k in [
        "import_kw", "export_kw", "unserved_kw", "hvac_kw", "battery_charge_kw",
        "battery_discharge_kw", "dhw_heat_kw", "ev_charge_kw", "ts_charge_kw",
        "ts_discharge_kw", "indoor_temp_c", "battery_soc_kwh", "base_load_kw", "solar_kw",
    ]} for bid in buildings}
    comfort_soft = {bid: np.zeros(n, dtype=bool) for bid in buildings}
    comfort_hard = {bid: np.zeros(n, dtype=bool) for bid in buildings}
    interventions = {bid: [] for bid in buildings}
    prev_hvac = {bid: 0.0 for bid in buildings}

    for t in range(n):
        outage = bool(outage_mask[t]) if outage_mask is not None else False
        speculative, safes, ig0s = {}, {}, {}

        for bid, building in buildings.items():
            base_fn, solar_fn = forecast_fns[bid]
            ctx, internal_gain = build_step_context(
                building, world, t, horizon_steps, risk_level, weights, carbon_kg_per_kwh,
                base_fn, solar_fn, import_cap_kw=None, coordination_price_per_kwh=None,
                prev_hvac_kw=prev_hvac[bid], outage=False,
            )
            raw = policies[bid](ctx)
            ev_present_now = bool(building.profile.ev_present[t])
            ig0 = float(internal_gain[0]) if len(internal_gain) else 0.0
            safe = shield_action(raw, building, world, t, ig0, ev_present_now, apply_shield=True)
            spec_res = advance_physics(building, world, t, safe, ig0, import_cap_kw=None, outage=False,
                                        demand_spike_addon_kw=None, solar_failure_mask=None)
            speculative[bid], safes[bid], ig0s[bid] = spec_res, safe, ig0

        desired = {bid: speculative[bid].bal.grid_import_kw for bid in buildings}
        capacity = 0.0 if outage else world.grid_capacity_kw
        allocation = allocate_capacity(desired, capacity, criticality)

        for bid, building in buildings.items():
            if desired[bid] <= 0 or (capacity is not None and desired[bid] <= allocation[bid] + 1e-9):
                final = speculative[bid]
            else:
                final = advance_physics(building, world, t, safes[bid], ig0s[bid],
                                         import_cap_kw=allocation[bid], outage=outage,
                                         demand_spike_addon_kw=None, solar_failure_mask=None)
            building.state = final.next_state
            r = building.resources

            o = out[bid]
            o["import_kw"][t] = final.grid.import_kw
            o["export_kw"][t] = final.grid.export_kw
            o["unserved_kw"][t] = final.grid.unserved_kw
            o["hvac_kw"][t] = safes[bid].hvac_kw
            o["battery_charge_kw"][t] = safes[bid].battery_charge_kw
            o["battery_discharge_kw"][t] = safes[bid].battery_discharge_kw
            o["dhw_heat_kw"][t] = safes[bid].dhw_heat_kw
            o["ev_charge_kw"][t] = safes[bid].ev_charge_kw
            o["ts_charge_kw"][t] = safes[bid].ts_charge_kw
            o["ts_discharge_kw"][t] = safes[bid].ts_discharge_kw
            o["indoor_temp_c"][t] = final.next_state.indoor_temp_c
            o["battery_soc_kwh"][t] = final.next_state.battery_soc_kwh
            o["base_load_kw"][t] = final.base_load_now
            o["solar_kw"][t] = final.solar_now
            comfort_soft[bid][t] = not (r.comfort_t_min <= final.next_state.indoor_temp_c <= r.comfort_t_max)
            comfort_hard[bid][t] = not (r.hard_t_min <= final.next_state.indoor_temp_c <= r.hard_t_max)
            interventions[bid].append(safes[bid].interventions)
            prev_hvac[bid] = safes[bid].hvac_kw

    result = {}
    for bid in buildings:
        o = out[bid]
        result[bid] = SimulationSeries(
            index=world.index, import_kw=o["import_kw"], export_kw=o["export_kw"], unserved_kw=o["unserved_kw"],
            hvac_kw=o["hvac_kw"], battery_charge_kw=o["battery_charge_kw"], battery_discharge_kw=o["battery_discharge_kw"],
            dhw_heat_kw=o["dhw_heat_kw"], ev_charge_kw=o["ev_charge_kw"], ts_charge_kw=o["ts_charge_kw"],
            ts_discharge_kw=o["ts_discharge_kw"], indoor_temp_c=o["indoor_temp_c"], battery_soc_kwh=o["battery_soc_kwh"],
            comfort_soft_violation=comfort_soft[bid], comfort_hard_violation=comfort_hard[bid],
            shield_interventions=interventions[bid], base_load_kw=o["base_load_kw"], solar_kw=o["solar_kw"],
        )
    return result


@dataclass
class ResilienceSummary:
    hours_survived: float
    critical_load_service_frac: float
    comfort_degradation_steps: int
    energy_shortage_kwh: float
    min_battery_reserve_frac: dict
    economic_cost_inr: float

    def as_dict(self) -> dict:
        return {
            "hours_survived": round(self.hours_survived, 2),
            "critical_load_service_frac": round(self.critical_load_service_frac, 4),
            "comfort_degradation_steps": self.comfort_degradation_steps,
            "energy_shortage_kwh": round(self.energy_shortage_kwh, 2),
            "min_battery_reserve_frac": {k: round(v, 3) for k, v in self.min_battery_reserve_frac.items()},
            "economic_cost_inr": round(self.economic_cost_inr, 2),
        }


def summarize_resilience(series_by_building: dict[str, SimulationSeries], world: World,
                          criticality: dict[str, float], outage_mask: np.ndarray, bills_total_inr: float) -> ResilienceSummary:
    dt = world.dt_hours
    outage_steps = np.where(outage_mask)[0]
    hours_survived = 0.0
    if len(outage_steps):
        # "survived" = highest-criticality building kept below its unserved-load threshold
        crit_bid = max(criticality, key=criticality.get)
        served = series_by_building[crit_bid].unserved_kw[outage_steps] < 1e-6
        consecutive = 0
        for ok in served:
            if ok:
                consecutive += 1
            else:
                break
        hours_survived = consecutive * dt

    total_served = sum(float(np.sum(s.import_kw) * dt) for s in series_by_building.values())
    total_unserved = sum(float(np.sum(s.unserved_kw) * dt) for s in series_by_building.values())
    critical_service = total_served / (total_served + total_unserved) if (total_served + total_unserved) > 0 else 1.0

    comfort_degradation = sum(int(s.comfort_soft_violation.sum()) for s in series_by_building.values())
    min_reserve = {
        bid: float(np.min(s.battery_soc_kwh) / max(world.buildings[bid].resources.battery_capacity_kwh, 1e-6))
        for bid, s in series_by_building.items() if world.buildings[bid].resources.battery_capacity_kwh > 0
    }

    return ResilienceSummary(hours_survived, critical_service, comfort_degradation, total_unserved,
                              min_reserve, bills_total_inr)
