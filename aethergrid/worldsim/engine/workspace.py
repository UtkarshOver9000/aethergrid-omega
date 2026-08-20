"""Workspace/commercial building entity -- a parallel path to household.py
using the same reused pure functions, but with an occupancy shape and
appliance mix that produces a visibly different (daytime-weighted,
computer/meeting-room driven) load profile than any residential archetype."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aethergrid.simulation.electrical import electrical_balance
from aethergrid.simulation.storage import battery_step
from aethergrid.simulation.thermal import internal_gains_kw, thermal_step
from aethergrid.worldsim.engine.weather import Environment
from aethergrid.worldsim.schemas.workspace import WorkspaceArchetype

HVAC_COP = 3.0
AC_HYSTERESIS_C = 1.0


def _workspace_occupancy(archetype: WorkspaceArchetype, index, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    hours = index.hour.values + index.minute.values / 60.0
    is_weekend = index.dayofweek.values >= 5

    def ramp(x):
        return 1.0 / (1.0 + np.exp(-x))
    up = ramp((hours - archetype.occupancy_start_hour) / 0.6 * 4)
    down = ramp((archetype.occupancy_end_hour - hours) / 0.6 * 4)
    base = np.clip(up * down, 0, 1)
    base = np.where(is_weekend, base * archetype.weekend_occupancy_factor, base)
    noise = rng.normal(0, 0.05, size=len(index))
    return np.clip(base + noise, 0, 1)


@dataclass
class WorkspaceSeries:
    kw: np.ndarray
    occupancy_frac: np.ndarray
    hvac_kw: np.ndarray
    lighting_kw: np.ndarray
    computer_kw: np.ndarray
    meeting_room_active: np.ndarray
    solar_kw: np.ndarray
    battery_soc_frac: np.ndarray
    ev_count_charging: np.ndarray
    indoor_temp_c: np.ndarray


def simulate_workspace(archetype: WorkspaceArchetype, env: Environment, dt_hours: float, seed: int) -> WorkspaceSeries:
    n = len(env.index)
    occ = _workspace_occupancy(archetype, env.index, seed)
    rng = np.random.default_rng(seed + 3)

    n_people = np.round(occ * archetype.occupancy_capacity).astype(int)
    lighting_kw = archetype.lighting_kw_per_person * n_people * 0.6 + 0.3
    computer_kw = archetype.computer_kw_per_person * n_people
    meeting_active = (rng.random(n) < (0.15 * occ)) & (occ > 0.3)
    meeting_kw = meeting_active * archetype.meeting_room_count * archetype.meeting_room_kw_each * 0.4

    T = (archetype.comfort_t_min_c + archetype.comfort_t_max_c) / 2.0
    ac_on = False
    batt_soc = archetype.battery_kwh * 0.5
    hvac_series = np.zeros(n)
    T_series = np.zeros(n)
    solar_series = np.zeros(n)
    battery_series = np.zeros(n)
    ev_charging_series = np.zeros(n, dtype=int)

    for t in range(n):
        if occ[t] > 0.15:
            if T > archetype.comfort_t_max_c:
                ac_on = True
            elif T < archetype.comfort_t_max_c - AC_HYSTERESIS_C:
                ac_on = False
        else:
            ac_on = False
        hvac_kw = archetype.hvac_capacity_kw * min(1.0, 0.3 + 0.7 * occ[t]) if ac_on else 0.0
        hvac_series[t] = hvac_kw

        gains = internal_gains_kw(occ[t], archetype.floor_area_m2, env.ghi_wm2[t] * (1 - 0.6 * env.cloud_factor[t]))
        T = thermal_step(T, env.temp_c[t], archetype.thermal_R_k_per_kw, archetype.thermal_C_kwh_per_k,
                          gains, HVAC_COP * hvac_kw, dt_hours)
        T_series[t] = T

        solar_kw = 0.0
        if env.sun_altitude[t] > 0:
            irradiance_factor = np.clip(env.ghi_wm2[t] / 1000.0, 0, 1.3) * (1 - 0.6 * env.cloud_factor[t])
            solar_kw = archetype.solar_kwp * irradiance_factor * 0.9
        solar_series[t] = solar_kw

        ev_charging_series[t] = int(round(min(archetype.ev_charger_count, occ[t] * archetype.ev_charger_count * 1.3)))
        ev_kw = ev_charging_series[t] * archetype.ev_charger_kw

        load_kw = lighting_kw[t] + computer_kw[t] + meeting_kw[t] + hvac_kw + ev_kw
        surplus = solar_kw - load_kw
        batt_c = max(0.0, surplus) if archetype.battery_kwh > 0 else 0.0
        batt_d = min(-min(0.0, surplus), archetype.battery_kw) if archetype.battery_kwh > 0 else 0.0
        batt_res = battery_step(batt_soc, archetype.battery_kwh, archetype.battery_kw, batt_c, batt_d, dt_hours)
        batt_soc = batt_res.soc_kwh
        battery_series[t] = batt_soc / archetype.battery_kwh if archetype.battery_kwh > 0 else 0.0

    kw_total = lighting_kw + computer_kw + meeting_kw + hvac_series + ev_charging_series * archetype.ev_charger_kw - solar_series
    kw_total = np.maximum(kw_total, -solar_series)  # allow export but keep it physically bounded by generation

    return WorkspaceSeries(
        kw=kw_total, occupancy_frac=occ, hvac_kw=hvac_series, lighting_kw=lighting_kw,
        computer_kw=computer_kw, meeting_room_active=meeting_active, solar_kw=solar_series,
        battery_soc_frac=battery_series, ev_count_charging=ev_charging_series, indoor_temp_c=T_series,
    )
