"""Society common infrastructure: real state, not decoration. Water tank
level actually depends on pump on/off; streetlights are strictly dusk-to-
dawn from `sun_altitude`; lift usage follows aggregate occupancy activity;
STP and clubhouse HVAC each have their own small state machine."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aethergrid.worldsim.engine.weather import Environment
from aethergrid.worldsim.schemas.appliance import COMMON_APPLIANCES
from aethergrid.worldsim.schemas.common_infra import CommonInfraSpec

PUMP_LOW_THRESHOLD_FRAC = 0.35
PUMP_HIGH_THRESHOLD_FRAC = 0.90


@dataclass
class CommonInfraSeries:
    water_tank_level_pct: np.ndarray
    pump_on: np.ndarray
    lift_active: np.ndarray
    streetlights_on: np.ndarray
    stp_on: np.ndarray
    clubhouse_hvac_kw: np.ndarray
    kw: np.ndarray                    # total common-infra electrical draw, pre-curtailment


def simulate_common_infra(spec: CommonInfraSpec, env: Environment, dt_hours: float,
                           aggregate_occupancy_frac: np.ndarray, seed: int) -> CommonInfraSeries:
    n = len(env.index)
    rng = np.random.default_rng(seed + 9)

    tank_level_l = spec.water_tank_capacity_l * 0.7
    tank_pct = np.zeros(n)
    pump_on = np.zeros(n, dtype=bool)
    stp_on = np.zeros(n, dtype=bool)

    # residents' water draw scales with aggregate occupancy (people home -> water used)
    base_draw_l_per_step = spec.water_tank_capacity_l * 0.015 * dt_hours * 4

    for t in range(n):
        draw = base_draw_l_per_step * (0.3 + 0.7 * aggregate_occupancy_frac[t])
        frac = tank_level_l / spec.water_tank_capacity_l
        if frac < PUMP_LOW_THRESHOLD_FRAC:
            pump_on[t] = True
        elif frac > PUMP_HIGH_THRESHOLD_FRAC:
            pump_on[t] = False
        else:
            pump_on[t] = pump_on[t - 1] if t > 0 else False
        fill = spec.pump_flow_l_per_min * 60 * dt_hours if pump_on[t] else 0.0
        tank_level_l = float(np.clip(tank_level_l + fill - draw, 0, spec.water_tank_capacity_l))
        tank_pct[t] = 100.0 * tank_level_l / spec.water_tank_capacity_l
        # STP runs a couple of scheduled sessions a day, roughly tied to peak drain windows
        hour = env.index.hour.values[t]
        stp_on[t] = spec.has_stp and hour in (10, 11, 22, 23) and (t % 4 < 2)

    lift_active = spec.has_lift & (aggregate_occupancy_frac > 0.15) & (rng.random(n) < 0.5)
    streetlights_on = env.sun_altitude <= 0.02

    hours = env.index.hour.values + env.index.minute.values / 60.0
    clubhouse_occ = np.clip(np.sin(np.pi * (hours - 16) / 10) if spec.has_clubhouse else np.zeros(n), 0, 1)
    clubhouse_hvac_kw = COMMON_APPLIANCES["clubhouse_common_hvac"].rated_kw * clubhouse_occ if spec.has_clubhouse else np.zeros(n)

    pump_kw = np.where(pump_on, COMMON_APPLIANCES["water_pump"].rated_kw, 0.0)
    lift_kw = np.where(lift_active, COMMON_APPLIANCES["lifts"].rated_kw * 0.4, COMMON_APPLIANCES["lifts"].rated_kw * 0.05)
    street_kw = np.where(streetlights_on, spec.streetlight_count * spec.streetlight_kw_each, 0.0)
    stp_kw = np.where(stp_on, COMMON_APPLIANCES["stp"].rated_kw, 0.0)
    security_kw = np.full(n, COMMON_APPLIANCES["security_fire_systems"].rated_kw)

    total_kw = pump_kw + lift_kw + street_kw + stp_kw + clubhouse_hvac_kw + security_kw

    return CommonInfraSeries(
        water_tank_level_pct=tank_pct, pump_on=pump_on, lift_active=lift_active,
        streetlights_on=streetlights_on, stp_on=stp_on, clubhouse_hvac_kw=clubhouse_hvac_kw, kw=total_kw,
    )
