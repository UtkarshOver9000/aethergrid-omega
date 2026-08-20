"""One household as a simulation entity. Owns its static config (identity,
position, archetype, appliance ownership) and simulates its own full
time series: occupancy-triggered untouchable/deferrable/thermostatic/
storage appliance state, real indoor-temperature RC dynamics, EV/battery/
DHW physical state via the REUSED pure functions from
aethergrid.simulation.{thermal,storage,electrical}.

Charging/heating/battery behavior here is deliberately UNCONTROLLED
("dumb") -- max-rate charging when present, thermostat bang-bang for AC,
greedy self-consumption for the battery. This is a world simulation, not
a controller: the point is to produce a believable baseline the (not-
built-here) optimizer could later act on, not to already be optimal.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from aethergrid.simulation.electrical import electrical_balance
from aethergrid.simulation.storage import battery_step, dhw_step, ev_step
from aethergrid.simulation.thermal import internal_gains_kw, thermal_step
from aethergrid.worldsim.engine.occupancy import OccupancyTrace, generate_occupancy_trace
from aethergrid.worldsim.engine.weather import Environment
from aethergrid.worldsim.schemas.appliance import HOUSEHOLD_APPLIANCES
from aethergrid.worldsim.schemas.household import HouseholdArchetype

HVAC_COP = 3.0                 # cooling-only convention, matches the parent optimizer project
AC_HYSTERESIS_C = 1.2
FLOOR_AREA_M2_PER_FLOOR = 55.0
FRIDGE_DUTY_CYCLE = 0.35


@dataclass
class HouseholdConfig:
    id: int
    archetype_name: str
    has_ev: bool
    has_solar: bool
    has_battery: bool
    solar_kwp: float
    battery_kwh: float
    battery_kw: float
    dhw_capacity_kwh: float
    dhw_power_kw: float
    ac_capacity_kw: float
    ev_capacity_kwh: float
    ev_charger_kw: float
    grid_x: int
    grid_z: int
    floors: int
    seed: int


def make_household_config(house_id: int, archetype_name: str, archetype: HouseholdArchetype,
                           ev_penetration: float, solar_penetration: float,
                           grid_x: int, grid_z: int, seed: int) -> HouseholdConfig:
    rng = np.random.default_rng(seed)
    has_solar = rng.random() < solar_penetration
    has_battery = has_solar and rng.random() < archetype.battery_ownership_prob
    has_ev = rng.random() < ev_penetration
    has_geyser = rng.random() < archetype.geyser_ownership_prob
    has_ac = rng.random() < archetype.ac_ownership_prob
    ac_count = max(1, int(round(rng.normal(archetype.ac_count_mean, 0.5)))) if has_ac else 0

    return HouseholdConfig(
        id=house_id, archetype_name=archetype_name,
        has_ev=has_ev, has_solar=has_solar, has_battery=has_battery,
        solar_kwp=round(rng.uniform(2.5, 4.5), 2) if has_solar else 0.0,
        battery_kwh=round(rng.uniform(4.0, 8.0), 1) if has_battery else 0.0,
        battery_kw=round(rng.uniform(2.5, 4.0), 1) if has_battery else 0.0,
        dhw_capacity_kwh=3.0 if has_geyser else 0.0,
        dhw_power_kw=HOUSEHOLD_APPLIANCES["geyser"].rated_kw if has_geyser else 0.0,
        ac_capacity_kw=HOUSEHOLD_APPLIANCES["ac_1_5_ton"].rated_kw * ac_count,
        ev_capacity_kwh=round(rng.uniform(30.0, 50.0), 1) if has_ev else 0.0,
        ev_charger_kw=HOUSEHOLD_APPLIANCES["ev_charger"].rated_kw if has_ev else 0.0,
        grid_x=grid_x, grid_z=grid_z,
        floors=int(rng.choice(archetype.floors_choices)),
        seed=seed,
    )


@dataclass
class HouseholdSeries:
    kw: np.ndarray
    ac_on: np.ndarray
    geyser_on: np.ndarray
    ev_state: list           # "absent" | "idle" | "charging" | "full"
    ev_soc_frac: np.ndarray
    solar_kw: np.ndarray
    battery_soc_frac: np.ndarray
    indoor_temp_c: np.ndarray
    comfort_dev_c: np.ndarray
    occupancy: np.ndarray
    deferrables_active: list  # list[list[str]] per tick


def simulate_household(config: HouseholdConfig, archetype: HouseholdArchetype, env: Environment,
                        dt_hours: float, curtail_mask: np.ndarray | None = None,
                        occupancy_multiplier: np.ndarray | None = None,
                        force_ev_present: np.ndarray | None = None) -> HouseholdSeries:
    """curtail_mask: optional bool array (len n_steps), True where the
    transformer breach-shedding logic (engine/transformer.py) has decided
    to shed this house's non-critical load this tick -- applied AFTER
    the household's own behavior is computed, per-appliance, respecting
    `archetype.override_probability` (a curtailed household still has a
    chance to keep running anyway).

    occupancy_multiplier: event-driven occupancy shift (festival/holiday).
    force_ev_present: event-driven forced EV plug-in window (high_ev_arrival),
    applied on top of the archetype's own occupancy-based presence pattern."""
    n = len(env.index)
    occ: OccupancyTrace = generate_occupancy_trace(archetype, env.index, seed=config.seed,
                                                    occupancy_multiplier=occupancy_multiplier)
    rng = np.random.default_rng(config.seed + 1)
    override_draws = rng.random(n) < archetype.override_probability
    # small per-house comfort-threshold jitter: real households of the same
    # archetype don't set their thermostat to the identical degree, and this
    # spreads out exactly when each AC clicks on/off, reducing artificial
    # synchronization (realism check: coincidence factor ~0.4-0.6, not ~1.0)
    comfort_jitter = rng.uniform(-0.7, 0.7)
    comfort_t_max = archetype.comfort_t_max_c + comfort_jitter
    comfort_t_min = archetype.comfort_t_min_c + comfort_jitter

    floor_area = config.floors * FLOOR_AREA_M2_PER_FLOOR
    T = (archetype.comfort_t_min_c + archetype.comfort_t_max_c) / 2.0
    ac_on_state = False
    dhw_soc = config.dhw_capacity_kwh * 0.6
    batt_soc = config.battery_kwh * 0.5
    ev_soc = config.ev_capacity_kwh * 0.4 if config.has_ev else 0.0
    ev_present_prev = False

    hours = env.index.hour.values + env.index.minute.values / 60.0

    out = HouseholdSeries(
        kw=np.zeros(n), ac_on=np.zeros(n, dtype=bool), geyser_on=np.zeros(n, dtype=bool),
        ev_state=["absent"] * n, ev_soc_frac=np.zeros(n), solar_kw=np.zeros(n),
        battery_soc_frac=np.zeros(n), indoor_temp_c=np.zeros(n), comfort_dev_c=np.zeros(n),
        occupancy=occ.occupant_count.copy(), deferrables_active=[[] for _ in range(n)],
    )

    for t in range(n):
        occupied = occ.occupancy_frac[t] > 0.2
        curtailed_now = bool(curtail_mask[t]) if curtail_mask is not None else False
        respects_curtailment = curtailed_now and not override_draws[t]

        # --- untouchable loads (occupancy-gated, never curtailed) ---
        fan_light = (HOUSEHOLD_APPLIANCES["ceiling_fan"].rated_kw + HOUSEHOLD_APPLIANCES["led_lighting"].rated_kw
                     + HOUSEHOLD_APPLIANCES["television_electronics"].rated_kw) * occ.occupancy_frac[t]
        cooking = HOUSEHOLD_APPLIANCES["cooking"].rated_kw * (1.0 if occ.cooking[t] else 0.0)
        fridge = HOUSEHOLD_APPLIANCES["refrigerator"].rated_kw * FRIDGE_DUTY_CYCLE
        untouchable_kw = fan_light + cooking + fridge + 0.05  # small standby baseline

        # --- thermostatic AC, hysteresis, only when occupied and owned ---
        ac_kw = 0.0
        if config.ac_capacity_kw > 0 and occupied:
            if T > comfort_t_max:
                ac_on_state = True
            elif T < comfort_t_max - AC_HYSTERESIS_C:
                ac_on_state = False
        else:
            ac_on_state = False
        if ac_on_state and not respects_curtailment:
            ac_kw = config.ac_capacity_kw
        out.ac_on[t] = ac_on_state and ac_kw > 0

        gains = internal_gains_kw(occ.occupancy_frac[t], floor_area, env.ghi_wm2[t] * (1 - 0.6 * env.cloud_factor[t]))
        T = thermal_step(T, env.temp_c[t], archetype.thermal_R_k_per_kw, archetype.thermal_C_kwh_per_k,
                          gains, HVAC_COP * ac_kw, dt_hours)
        out.indoor_temp_c[t] = T
        out.comfort_dev_c[t] = max(0.0, T - comfort_t_max) + max(0.0, comfort_t_min - T)

        # --- geyser (DHW storage) ---
        geyser_kw = 0.0
        if config.dhw_capacity_kwh > 0:
            draw = 0.0
            if occ.occupancy_frac[t] > 0.3 and (7 <= hours[t] < 9 or 19 <= hours[t] < 22):
                draw = 0.4 * max(1, out.occupancy[t])
            want_heat = dhw_soc < 0.85 * config.dhw_capacity_kwh
            heat_request = config.dhw_power_kw if (want_heat and not respects_curtailment) else 0.0
            dhw_res = dhw_step(dhw_soc, config.dhw_capacity_kwh, config.dhw_power_kw, heat_request, draw, dt_hours)
            dhw_soc, geyser_kw = dhw_res.soc_kwh, dhw_res.actual_charge_kw
        out.geyser_on[t] = geyser_kw > 0.05
        if out.geyser_on[t]:
            out.deferrables_active[t].append("geyser")

        # --- EV: uncontrolled max-rate charging while present ---
        ev_kw = 0.0
        ev_present = config.has_ev and (occ.occupancy_frac[t] > 0.35 or (force_ev_present is not None and force_ev_present[t]))
        if config.has_ev:
            if ev_present and not ev_present_prev:
                # arrival: car comes back partially depleted
                deficit = config.ev_capacity_kwh * rng.uniform(0.2, 0.55)
                ev_soc = max(0.0, ev_soc - deficit)
            if ev_present:
                target = 0.9 * config.ev_capacity_kwh
                want = config.ev_charger_kw if (ev_soc < target and not respects_curtailment) else 0.0
                ev_res = ev_step(ev_soc, config.ev_capacity_kwh, config.ev_charger_kw, want, dt_hours, True)
                ev_soc, ev_kw = ev_res.soc_kwh, ev_res.actual_charge_kw
                out.ev_state[t] = "charging" if ev_kw > 0.05 else ("full" if ev_soc >= target else "idle")
                if ev_kw > 0.05:
                    out.deferrables_active[t].append("ev_charger")
            else:
                out.ev_state[t] = "absent"
            out.ev_soc_frac[t] = ev_soc / config.ev_capacity_kwh if config.ev_capacity_kwh > 0 else 0.0
            ev_present_prev = ev_present

        # --- solar ---
        solar_kw = 0.0
        if config.has_solar and env.sun_altitude[t] > 0:
            irradiance_factor = np.clip(env.ghi_wm2[t] / 1000.0, 0, 1.3) * (1 - 0.6 * env.cloud_factor[t])
            solar_kw = config.solar_kwp * irradiance_factor * 0.9
        out.solar_kw[t] = solar_kw

        # --- battery: greedy self-consumption (not an optimizer, a fixed heuristic) ---
        batt_c = batt_d = 0.0
        if config.has_battery:
            provisional_load = untouchable_kw + ac_kw + geyser_kw + ev_kw
            surplus = solar_kw - provisional_load
            if surplus > 0:
                batt_c = surplus
            else:
                batt_d = min(-surplus, config.battery_kw)
            batt_res = battery_step(batt_soc, config.battery_kwh, config.battery_kw, batt_c, batt_d, dt_hours)
            batt_soc, batt_c, batt_d = batt_res.soc_kwh, batt_res.actual_charge_kw, batt_res.actual_discharge_kw
        out.battery_soc_frac[t] = batt_soc / config.battery_kwh if config.battery_kwh > 0 else 0.0

        bal = electrical_balance(untouchable_kw, ac_kw, geyser_kw, ev_kw, batt_c, batt_d, solar_kw)
        out.kw[t] = bal.grid_import_kw - bal.grid_export_kw  # net; can go negative if exporting

    return out
