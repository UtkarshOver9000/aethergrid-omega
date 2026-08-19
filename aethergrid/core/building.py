"""Building state + exogenous (uncontrollable) profiles.

Exogenous profiles (base electrical load, occupancy, solar potential, DHW
draw, EV presence/arrival deficit) are generated once per building from a
seeded RNG so a (seed, world-json) pair is fully reproducible (TEST 1 in
PART AR). They represent SYNTHETIC demand patterns shaped by the building's
archetype schedule -- not measured data.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from aethergrid.core.resources import BuildingResources
from aethergrid.schemas.building import BuildingArchetype


@dataclass
class BuildingState:
    indoor_temp_c: float
    battery_soc_kwh: float
    thermal_storage_soc_kwh: float
    dhw_soc_kwh: float
    ev_soc_kwh: float
    cum_import_kwh: float = 0.0
    cum_export_kwh: float = 0.0
    cum_unserved_kwh: float = 0.0

    def copy(self, **changes) -> "BuildingState":
        return replace(self, **changes)


@dataclass
class ExogenousProfile:
    index: pd.DatetimeIndex
    base_load_kw: np.ndarray
    occupancy_frac: np.ndarray
    solar_potential_kw: np.ndarray
    dhw_draw_kw: np.ndarray
    ev_present: np.ndarray
    ev_arrival_deficit_kwh: np.ndarray


def _smooth_occupancy(hours: np.ndarray, start: float, end: float, ramp_h: float = 0.75) -> np.ndarray:
    def ramp(x):
        return 1.0 / (1.0 + np.exp(-x))
    if start <= end:
        up = ramp((hours - start) / ramp_h * 4)
        down = ramp((end - hours) / ramp_h * 4)
        return np.clip(up * down, 0, 1)
    # wraps past midnight (occupied hours span across 00:00, e.g. hotel/residential)
    outside = ramp((hours - end) / ramp_h * 4) * ramp((start - hours) / ramp_h * 4)
    return np.clip(1 - outside, 0, 1)


def _ev_schedule(building_type: str, hours: np.ndarray, weekday: np.ndarray) -> np.ndarray:
    if building_type in ("office", "laboratory", "school", "public"):
        present = (hours >= 8.5) & (hours <= 18.0) & weekday
    elif building_type == "residential":
        present = (hours >= 18.5) | (hours <= 7.5)
    elif building_type == "hotel":
        present = (hours >= 15.0) | (hours <= 11.0)
    else:
        present = (hours >= 9.0) & (hours <= 20.0)
    return present.astype(bool)


class Building:
    def __init__(self, building_id: str, archetype: BuildingArchetype, resources: BuildingResources,
                 criticality: float, weather: pd.DataFrame, seed: int):
        self.id = building_id
        self.archetype = archetype
        self.resources = resources
        self.criticality = criticality
        self.rng = np.random.default_rng(seed)
        self.profile = self._build_profile(weather)
        self.state = self._init_state()

    def _init_state(self) -> BuildingState:
        r = self.resources
        return BuildingState(
            indoor_temp_c=(r.comfort_t_min + r.comfort_t_max) / 2,
            battery_soc_kwh=r.battery_capacity_kwh * 0.5,
            thermal_storage_soc_kwh=r.thermal_storage_capacity_kwh * 0.5,
            dhw_soc_kwh=r.dhw_storage_kwh * 0.6,
            ev_soc_kwh=r.ev_capacity_kwh * r.ev_count * 0.4 if r.has_ev else 0.0,
        )

    def _build_profile(self, weather: pd.DataFrame) -> ExogenousProfile:
        idx = weather.index
        hours = idx.hour.values + idx.minute.values / 60.0
        weekday = idx.dayofweek.values < 5
        a = self.archetype
        n = len(idx)

        occ = _smooth_occupancy(hours, a.occupancy_start_hour, a.occupancy_end_hour)
        weekend_scale = np.where(weekday, 1.0, a.weekend_occupancy_factor)
        occ = np.clip(occ * weekend_scale, 0, 1)

        temp_delta = weather["temp_c"].values - 24.0
        weather_load = np.clip(np.abs(temp_delta) - 3, 0, None) * a.weather_sensitivity_kw_per_c * 0.3

        noise = self.rng.normal(0, a.base_load_kw_std * 0.15, size=n)
        base_load = a.base_load_kw_mean * (0.35 + 0.65 * occ) + weather_load + noise
        base_load = np.clip(base_load, a.base_load_kw_mean * 0.15, None)

        solar_potential = self.resources.solar_kwp * (weather["ghi_wm2"].values / 1000.0) * 0.92

        dhw_draw = np.zeros(n)
        if self.resources.has_dhw:
            dhw_draw = self.resources.dhw_capacity_kw * 0.25 * (0.3 + 0.7 * occ)
            dhw_draw += self.rng.normal(0, self.resources.dhw_capacity_kw * 0.03, size=n)
            dhw_draw = np.clip(dhw_draw, 0, self.resources.dhw_capacity_kw)

        ev_present = np.zeros(n, dtype=bool)
        ev_deficit = np.zeros(n)
        if self.resources.has_ev:
            ev_present = _ev_schedule(a.type, hours, weekday)
            arrivals = np.where(~ev_present[:-1] & ev_present[1:])[0] + 1
            fleet_kwh = self.resources.ev_capacity_kwh * self.resources.ev_count
            for arr in arrivals:
                ev_deficit[arr] = fleet_kwh * self.rng.uniform(0.25, 0.6)

        return ExogenousProfile(idx, base_load, occ, solar_potential, dhw_draw, ev_present, ev_deficit)
