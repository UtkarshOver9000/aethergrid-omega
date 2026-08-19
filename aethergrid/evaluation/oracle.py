"""Perfect-foresight Oracle (PART AL). Not a deployable controller -- it is
handed the REALIZED future base load, solar and weather for the entire
simulation window and solves one global LP. It exists solely to estimate
the theoretical best achievable performance so every other controller can
be scored by its "oracle gap" (PART U/AL): how much of the theoretically
achievable improvement it actually captured."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aethergrid.core.building import Building
from aethergrid.core.timestep import SimulationSeries
from aethergrid.core.world import World
from aethergrid.optimization.mpc import solve_building_horizon
from aethergrid.optimization.objective import SolveConfig
from aethergrid.schemas.experiment import ObjectiveWeights
from aethergrid.simulation.electrical import electrical_balance
from aethergrid.simulation.grid import apply_grid_constraints


def solve_oracle(building: Building, world: World, weights: ObjectiveWeights, carbon_kg_per_kwh: float,
                  import_cap_kw: float | None = None, outage_mask: np.ndarray | None = None) -> SimulationSeries:
    building.state = building._init_state()
    n = world.n_steps
    r = building.resources
    idx = world.index
    dt = world.dt_hours

    hours = idx.hour.values + idx.minute.values / 60.0
    rates = np.array([world.tariff.rate_at(h) for h in hours])
    temp = world.weather["temp_c"].values
    occ = building.profile.occupancy_frac
    internal_gain = 8.0 * building.archetype.floor_area_m2 * occ / 1000.0 * 0.5 + \
        world.weather["ghi_wm2"].values * building.archetype.floor_area_m2 * 0.02 / 1000.0

    cfg = SolveConfig(weights=weights, carbon_kg_per_kwh=carbon_kg_per_kwh,
                       demand_charge_per_kva=world.tariff.demand_charge_per_kva)

    sol = solve_building_horizon(
        r, building.state, building.profile.base_load_kw, building.profile.solar_potential_kw,
        temp, internal_gain, building.profile.dhw_draw_kw, building.profile.ev_present,
        r.ev_capacity_kwh * r.ev_count * 0.85, rates, dt, cfg, import_cap_kw=import_cap_kw,
    )

    # Oracle already respects hard bounds via LP constraints, so no shield needed;
    # but outages restrict import after the fact (oracle cannot foresee unmodeled
    # outages unless told, matching how the stress lab injects them).
    import_kw, export_kw, unserved_kw = sol.grid_import_kw.copy(), sol.grid_export_kw.copy(), np.zeros(n)
    if outage_mask is not None:
        for t in range(n):
            if outage_mask[t]:
                unserved_kw[t] = import_kw[t]
                import_kw[t] = 0.0
                export_kw[t] = 0.0

    comfort_soft = (sol.indoor_temp_c[:n] < r.comfort_t_min) | (sol.indoor_temp_c[:n] > r.comfort_t_max)
    comfort_hard = (sol.indoor_temp_c[:n] < r.hard_t_min) | (sol.indoor_temp_c[:n] > r.hard_t_max)

    return SimulationSeries(
        index=idx, import_kw=import_kw, export_kw=export_kw, unserved_kw=unserved_kw,
        hvac_kw=sol.hvac_kw, battery_charge_kw=sol.battery_charge_kw, battery_discharge_kw=sol.battery_discharge_kw,
        dhw_heat_kw=sol.dhw_heat_kw, ev_charge_kw=sol.ev_charge_kw, ts_charge_kw=sol.ts_charge_kw,
        ts_discharge_kw=sol.ts_discharge_kw, indoor_temp_c=sol.indoor_temp_c[:n], battery_soc_kwh=sol.battery_soc_kwh[:n],
        comfort_soft_violation=comfort_soft, comfort_hard_violation=comfort_hard, shield_interventions=[[] for _ in range(n)],
        base_load_kw=building.profile.base_load_kw, solar_kw=building.profile.solar_potential_kw,
    )
