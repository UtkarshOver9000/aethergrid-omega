"""Stress engine orchestration: turns a list of validated EventSpec objects
into the concrete masks/wrappers `core/timestep.py:simulate_building_series`
and the forecaster consume. Two application styles are used, both real and
neither silently swapped for the other:

  WINDOWED (within one simulation run): grid_outage, demand_spike,
    solar_failure, building_failure, sensor_dropout, forecast_bias,
    connection_failure -- these produce per-step masks/adjustments.

  WHOLE-SCENARIO (constant for the entire run): heatwave (baked into the
    weather before Building profiles are generated -- see
    core/world.py + stress/heatwave.py), tariff_change (swap the tariff
    file used for the whole run), parameter_drift (resources replaced once
    up front). This is a deliberate scope simplification for a
    hackathon-tractable stress lab, documented here rather than hidden.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from aethergrid.core.world import World
from aethergrid.schemas.event import EventSpec
from aethergrid.stress import building_failure, demand_spike, forecast_bias, outage, sensor_dropout, solar_failure


@dataclass
class StressContext:
    outage_mask: np.ndarray
    solar_failure_mask: np.ndarray
    events: list[EventSpec] = field(default_factory=list)

    def demand_spike_addon(self, world: World, building_id: str) -> np.ndarray:
        addon = np.zeros(world.n_steps)
        peak = float(world.buildings[building_id].profile.base_load_kw.max())
        for e in self.events:
            if e.type == "demand_spike" and (e.target_building_id in (None, building_id)):
                addon += demand_spike.addon_kw(world.index, e, peak)
        return addon

    def building_failure_mask(self, world: World, building_id: str) -> np.ndarray:
        mask = np.zeros(world.n_steps, dtype=bool)
        for e in self.events:
            if e.type == "building_failure":
                mask |= building_failure.building_failure_mask(world.index, e, building_id)
        return mask

    def wrap_forecast(self, world: World, base_fn):
        wrapped = base_fn
        dropout = np.zeros(world.n_steps, dtype=bool)
        for e in self.events:
            if e.type == "sensor_dropout":
                dropout |= sensor_dropout.dropout_mask(world.index, e)
        if dropout.any():
            first_dropout_event = next(e for e in self.events if e.type == "sensor_dropout")
            wrapped = sensor_dropout.wrap_degraded_forecast(wrapped, dropout, first_dropout_event)
        for e in self.events:
            if e.type == "forecast_bias":
                wrapped = forecast_bias.wrap_biased_forecast(wrapped, world.index, e)
        return wrapped


def build_stress_context(world: World, events: list[EventSpec]) -> StressContext:
    outage_m = np.zeros(world.n_steps, dtype=bool)
    solar_m = np.zeros(world.n_steps, dtype=bool)
    for e in events:
        if e.type == "grid_outage":
            outage_m |= outage.outage_mask(world.index, e)
        if e.type == "solar_failure":
            solar_m |= solar_failure.solar_failure_mask(world.index, e)
    return StressContext(outage_m, solar_m, list(events))
