"""The single reusable simulation loop. Every controller (baseline, RL,
hierarchical hybrid) and every experiment (counterfactual, ablation,
robustness, oracle-gap) ultimately calls `simulate_building_series` (or,
for multi-building colony coordination, the lower-level `build_step_context`
/ `advance_physics` pair directly -- see simulation/colony.py) so that
differences in reported metrics are attributable to the *policy*, not to
divergent plumbing between code paths.

Per step: policy proposes an action -> safety shield projects it onto the
feasible set -> digital twin physics advances state -> flows are logged.
BillEngine is applied once, after the full series is collected (billing is
a function of the whole realized series, not a per-step accumulation, so
demand-charge peaks are computed correctly).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import pandas as pd

from aethergrid.core.building import Building, BuildingState
from aethergrid.core.resources import BuildingResources
from aethergrid.core.world import World
from aethergrid.optimization.objective import HVAC_COP
from aethergrid.optimization.safety_shield import ShieldedAction, project_action
from aethergrid.schemas.experiment import ObjectiveWeights
from aethergrid.simulation.electrical import ElectricalBalance, electrical_balance
from aethergrid.simulation.grid import GridResult, apply_grid_constraints
from aethergrid.simulation.storage import battery_step, dhw_step, ev_step, thermal_storage_step
from aethergrid.simulation.thermal import thermal_step


@dataclass
class StepContext:
    t: int
    timestamp: pd.Timestamp
    state: BuildingState
    resources: BuildingResources
    dt_hours: float
    horizon_steps: int
    forecast_base_load_path: dict            # {h: {q: val}}
    forecast_solar_path: dict                # {h: {q: val}}
    horizon_temp_out_c: np.ndarray
    horizon_internal_gain_kw: np.ndarray
    horizon_dhw_draw_kw: np.ndarray
    horizon_ev_present: np.ndarray
    horizon_rates: np.ndarray
    ev_energy_target_kwh: float
    risk_level: float
    weights: ObjectiveWeights
    carbon_kg_per_kwh: float
    demand_charge_per_kva: float
    import_cap_kw: Optional[float]
    coordination_price_per_kwh: Optional[np.ndarray]
    prev_hvac_kw: float
    outage: bool


PolicyFn = Callable[[StepContext], dict]


@dataclass
class SimulationSeries:
    index: pd.DatetimeIndex
    import_kw: np.ndarray
    export_kw: np.ndarray
    unserved_kw: np.ndarray
    hvac_kw: np.ndarray
    battery_charge_kw: np.ndarray
    battery_discharge_kw: np.ndarray
    dhw_heat_kw: np.ndarray
    ev_charge_kw: np.ndarray
    ts_charge_kw: np.ndarray
    ts_discharge_kw: np.ndarray
    indoor_temp_c: np.ndarray
    battery_soc_kwh: np.ndarray
    comfort_soft_violation: np.ndarray  # bool: outside [comfort_t_min, comfort_t_max]
    comfort_hard_violation: np.ndarray  # bool: outside [hard_t_min, hard_t_max]
    shield_interventions: list          # list[list[str]] per step
    base_load_kw: np.ndarray
    solar_kw: np.ndarray

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame({
            "import_kw": self.import_kw, "export_kw": self.export_kw, "unserved_kw": self.unserved_kw,
            "hvac_kw": self.hvac_kw, "battery_charge_kw": self.battery_charge_kw,
            "battery_discharge_kw": self.battery_discharge_kw, "dhw_heat_kw": self.dhw_heat_kw,
            "ev_charge_kw": self.ev_charge_kw, "ts_charge_kw": self.ts_charge_kw,
            "ts_discharge_kw": self.ts_discharge_kw, "indoor_temp_c": self.indoor_temp_c,
            "battery_soc_kwh": self.battery_soc_kwh, "comfort_soft_violation": self.comfort_soft_violation,
            "comfort_hard_violation": self.comfort_hard_violation, "base_load_kw": self.base_load_kw,
            "solar_kw": self.solar_kw,
        }, index=self.index)


def horizon_slices(building: Building, world: World, t: int, horizon_steps: int):
    """Common per-step horizon arrays (weather/occupancy/rates/etc.) needed
    to build a StepContext. Shared by the single-building loop and the
    colony's multi-building loop so both see identical inputs."""
    n = world.n_steps
    idx = world.index
    H = min(horizon_steps, n - t)
    hours = idx.hour[t:t + H].values + idx.minute[t:t + H].values / 60.0
    horizon_rates = np.array([world.tariff.rate_at(h) for h in hours])
    horizon_temp = world.weather["temp_c"].values[t:t + H]
    occ = building.profile.occupancy_frac[t:t + H]
    internal_gain = 8.0 * building.archetype.floor_area_m2 * occ / 1000.0 * 0.5 + \
        world.weather["ghi_wm2"].values[t:t + H] * building.archetype.floor_area_m2 * 0.02 / 1000.0
    dhw_draw = building.profile.dhw_draw_kw[t:t + H]
    ev_present_h = building.profile.ev_present[t:t + H]
    return H, horizon_rates, horizon_temp, internal_gain, dhw_draw, ev_present_h


def build_step_context(
    building: Building, world: World, t: int, horizon_steps: int, risk_level: float,
    weights: ObjectiveWeights, carbon_kg_per_kwh: float,
    forecast_base_load_fn: Callable[[int, int], dict], forecast_solar_fn: Callable[[int, int], dict],
    import_cap_kw: Optional[float], coordination_price_per_kwh: Optional[np.ndarray],
    prev_hvac_kw: float, outage: bool,
) -> tuple[StepContext, np.ndarray]:
    """Returns (StepContext, internal_gain_array) -- the latter is also
    needed by advance_physics so it's handed back rather than recomputed."""
    r = building.resources
    H, horizon_rates, horizon_temp, internal_gain, dhw_draw, ev_present_h = horizon_slices(building, world, t, horizon_steps)
    base_load_path = forecast_base_load_fn(t, H)
    solar_path = forecast_solar_fn(t, H)
    ctx = StepContext(
        t=t, timestamp=world.index[t], state=building.state, resources=r, dt_hours=world.dt_hours,
        horizon_steps=H, forecast_base_load_path=base_load_path, forecast_solar_path=solar_path,
        horizon_temp_out_c=horizon_temp, horizon_internal_gain_kw=internal_gain,
        horizon_dhw_draw_kw=dhw_draw, horizon_ev_present=ev_present_h, horizon_rates=horizon_rates,
        ev_energy_target_kwh=(r.ev_capacity_kwh * r.ev_count * 0.85), risk_level=risk_level,
        weights=weights, carbon_kg_per_kwh=carbon_kg_per_kwh,
        demand_charge_per_kva=world.tariff.demand_charge_per_kva, import_cap_kw=import_cap_kw,
        coordination_price_per_kwh=(coordination_price_per_kwh[t:t + H] if coordination_price_per_kwh is not None else None),
        prev_hvac_kw=prev_hvac_kw, outage=outage,
    )
    return ctx, internal_gain


def shield_action(raw_action: dict, building: Building, world: World, t: int, internal_gain0: float,
                   ev_present_now: bool, apply_shield: bool) -> ShieldedAction:
    r = building.resources
    if apply_shield:
        return project_action(
            raw_action, r, building.state, world.weather["temp_c"].values[t], internal_gain0,
            world.dt_hours, ev_present_now, float(building.profile.dhw_draw_kw[t]),
        )
    return ShieldedAction(**{k: raw_action.get(k, 0.0) for k in [
        "hvac_kw", "battery_charge_kw", "battery_discharge_kw", "dhw_heat_kw",
        "ev_charge_kw", "ts_charge_kw", "ts_discharge_kw",
    ]}, interventions=["SHIELD BYPASSED (ablation study only)"])


@dataclass
class PhysicsStepResult:
    next_state: BuildingState
    grid: GridResult
    bal: ElectricalBalance
    safe: ShieldedAction
    base_load_now: float
    solar_now: float


def advance_physics(
    building: Building, world: World, t: int, safe: ShieldedAction, internal_gain0: float,
    import_cap_kw: Optional[float], outage: bool,
    demand_spike_addon_kw: Optional[np.ndarray], solar_failure_mask: Optional[np.ndarray],
) -> PhysicsStepResult:
    """Advance one building's physical state by one step given an already
    -shielded action. Pure function of (building.state, safe action,
    exogenous inputs) -- does not touch building.state itself, so callers
    (single-building loop, colony joint loop) control exactly when/whether
    to commit the returned next_state."""
    r = building.resources
    dt = world.dt_hours
    ev_present_now = bool(building.profile.ev_present[t])

    base_load_now = building.profile.base_load_kw[t]
    if demand_spike_addon_kw is not None:
        base_load_now = base_load_now + demand_spike_addon_kw[t]
    solar_now = building.profile.solar_potential_kw[t]
    if solar_failure_mask is not None and solar_failure_mask[t]:
        solar_now = 0.0

    T_next = thermal_step(
        building.state.indoor_temp_c, world.weather["temp_c"].values[t], r.thermal_R, r.thermal_C,
        internal_gain0, HVAC_COP * safe.hvac_kw, dt,
    )
    batt_res = battery_step(building.state.battery_soc_kwh, r.battery_capacity_kwh, r.battery_power_kw,
                             safe.battery_charge_kw, safe.battery_discharge_kw, dt,
                             r.battery_round_trip_eff, r.battery_min_soc_frac, r.battery_max_soc_frac)
    ts_res = thermal_storage_step(building.state.thermal_storage_soc_kwh, r.thermal_storage_capacity_kwh,
                                   r.thermal_storage_power_kw, safe.ts_charge_kw, safe.ts_discharge_kw, dt,
                                   r.thermal_storage_loss_frac_per_step)
    dhw_res = dhw_step(building.state.dhw_soc_kwh, r.dhw_storage_kwh, r.dhw_capacity_kw,
                        safe.dhw_heat_kw, float(building.profile.dhw_draw_kw[t]), dt)
    ev_deficit = building.profile.ev_arrival_deficit_kwh[t]
    ev_soc_before = max(0.0, building.state.ev_soc_kwh - ev_deficit)
    ev_res = ev_step(ev_soc_before, r.ev_capacity_kwh * r.ev_count, r.ev_max_charge_kw * r.ev_count,
                      safe.ev_charge_kw, dt, ev_present_now)

    bal = electrical_balance(base_load_now, safe.hvac_kw, dhw_res.actual_charge_kw, ev_res.actual_charge_kw,
                              batt_res.actual_charge_kw, batt_res.actual_discharge_kw, solar_now)
    grid = apply_grid_constraints(bal.grid_import_kw, bal.grid_export_kw, import_cap_kw, outage)

    next_state = BuildingState(
        indoor_temp_c=T_next, battery_soc_kwh=batt_res.soc_kwh, thermal_storage_soc_kwh=ts_res.soc_kwh,
        dhw_soc_kwh=dhw_res.soc_kwh, ev_soc_kwh=ev_res.soc_kwh,
        cum_import_kwh=building.state.cum_import_kwh + grid.import_kw * dt,
        cum_export_kwh=building.state.cum_export_kwh + grid.export_kw * dt,
        cum_unserved_kwh=building.state.cum_unserved_kwh + grid.unserved_kw * dt,
    )
    return PhysicsStepResult(next_state, grid, bal, safe, base_load_now, solar_now)


def simulate_building_series(
    building: Building,
    world: World,
    policy_fn: PolicyFn,
    horizon_steps: int,
    risk_level: float,
    weights: ObjectiveWeights,
    carbon_kg_per_kwh: float,
    forecast_base_load_fn: Callable[[int, int], dict],
    forecast_solar_fn: Callable[[int, int], dict],
    import_cap_kw: Optional[float] = None,
    outage_mask: Optional[np.ndarray] = None,
    demand_spike_addon_kw: Optional[np.ndarray] = None,
    solar_failure_mask: Optional[np.ndarray] = None,
    building_failure_mask: Optional[np.ndarray] = None,
    coordination_price_per_kwh: Optional[np.ndarray] = None,
    reset_state: bool = True,
    apply_shield: bool = True,
) -> SimulationSeries:
    """forecast_base_load_fn(t, horizon) -> {h: {q: val}}; same for solar.
    Kept as callables (not precomputed arrays) so callers can swap in
    perfect foresight (oracle), a sensor-dropout fallback, or a biased
    forecast (forecast-bias stress test) without touching this loop.

    `apply_shield=False` exists ONLY for the ablation study
    (evaluation/ablation.py) to quantify what the safety shield actually
    prevents (RULE 3 is otherwise absolute: every other caller in this
    codebase leaves it True, and the shield's hard-bound clipping still
    applies at the physics layer via storage.py's own clamping regardless)."""
    if reset_state:
        building.state = building._init_state()

    n = world.n_steps
    r = building.resources

    out = {k: np.zeros(n) for k in [
        "import_kw", "export_kw", "unserved_kw", "hvac_kw", "battery_charge_kw",
        "battery_discharge_kw", "dhw_heat_kw", "ev_charge_kw", "ts_charge_kw",
        "ts_discharge_kw", "indoor_temp_c", "battery_soc_kwh", "base_load_kw", "solar_kw",
    ]}
    comfort_soft = np.zeros(n, dtype=bool)
    comfort_hard = np.zeros(n, dtype=bool)
    interventions_log: list = []

    prev_hvac = 0.0
    for t in range(n):
        outage = bool(outage_mask[t]) if outage_mask is not None else False
        cap = 0.0 if outage else import_cap_kw

        ctx, internal_gain = build_step_context(
            building, world, t, horizon_steps, risk_level, weights, carbon_kg_per_kwh,
            forecast_base_load_fn, forecast_solar_fn, cap, coordination_price_per_kwh, prev_hvac, outage,
        )
        raw_action = policy_fn(ctx)

        ev_present_now = bool(building.profile.ev_present[t])
        if building_failure_mask is not None and building_failure_mask[t]:
            raw_action = {**raw_action, "hvac_kw": 0.0, "battery_charge_kw": 0.0, "dhw_heat_kw": 0.0}

        safe = shield_action(raw_action, building, world, t, float(internal_gain[0]) if len(internal_gain) else 0.0,
                              ev_present_now, apply_shield)
        interventions_log.append(safe.interventions)

        step_res = advance_physics(
            building, world, t, safe, float(internal_gain[0]) if len(internal_gain) else 0.0,
            cap, outage, demand_spike_addon_kw, solar_failure_mask,
        )
        building.state = step_res.next_state

        out["import_kw"][t] = step_res.grid.import_kw
        out["export_kw"][t] = step_res.grid.export_kw
        out["unserved_kw"][t] = step_res.grid.unserved_kw
        out["hvac_kw"][t] = safe.hvac_kw
        out["battery_charge_kw"][t] = safe.battery_charge_kw
        out["battery_discharge_kw"][t] = safe.battery_discharge_kw
        out["dhw_heat_kw"][t] = safe.dhw_heat_kw
        out["ev_charge_kw"][t] = safe.ev_charge_kw
        out["ts_charge_kw"][t] = safe.ts_charge_kw
        out["ts_discharge_kw"][t] = safe.ts_discharge_kw
        out["indoor_temp_c"][t] = step_res.next_state.indoor_temp_c
        out["battery_soc_kwh"][t] = step_res.next_state.battery_soc_kwh
        out["base_load_kw"][t] = step_res.base_load_now
        out["solar_kw"][t] = step_res.solar_now
        comfort_soft[t] = not (r.comfort_t_min <= step_res.next_state.indoor_temp_c <= r.comfort_t_max)
        comfort_hard[t] = not (r.hard_t_min <= step_res.next_state.indoor_temp_c <= r.hard_t_max)

        prev_hvac = safe.hvac_kw

    return SimulationSeries(
        index=world.index, import_kw=out["import_kw"], export_kw=out["export_kw"], unserved_kw=out["unserved_kw"],
        hvac_kw=out["hvac_kw"], battery_charge_kw=out["battery_charge_kw"],
        battery_discharge_kw=out["battery_discharge_kw"], dhw_heat_kw=out["dhw_heat_kw"],
        ev_charge_kw=out["ev_charge_kw"], ts_charge_kw=out["ts_charge_kw"], ts_discharge_kw=out["ts_discharge_kw"],
        indoor_temp_c=out["indoor_temp_c"], battery_soc_kwh=out["battery_soc_kwh"],
        comfort_soft_violation=comfort_soft, comfort_hard_violation=comfort_hard,
        shield_interventions=interventions_log, base_load_kw=out["base_load_kw"], solar_kw=out["solar_kw"],
    )
