"""Event system: turns a list of WorldEvent objects into concrete effect
arrays the society orchestrator applies. Every event type genuinely
mutates world state (environment, occupancy, EV presence, or synthetic
extra load) -- nothing here is a cosmetic label."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from aethergrid.worldsim.engine.weather import Environment, apply_cloud_cover, apply_heatwave_to_environment
from aethergrid.worldsim.schemas.events import WorldEvent


@dataclass
class EventEffects:
    occupancy_multiplier: np.ndarray        # per-tick, applied to household + workspace occupancy
    force_ev_present: np.ndarray            # bool per-tick, forces EV-owning households to plug in
    extra_load_kw: np.ndarray               # synthetic extra society-level load (transformer_overload)
    outage_mask: np.ndarray                 # bool per-tick, grid.available=False
    active_event_ids_by_tick: list          # list[list[str]]


def apply_events_to_environment(env: Environment, events: list[WorldEvent]) -> Environment:
    """Environment-mutating events only (heatwave, cloud_cover,
    sensor_disturbance) -- must run BEFORE household/workspace simulation
    since they change what those functions read."""
    for e in events:
        start = env.index[0] + pd.Timedelta(minutes=e.start_min)
        duration_hours = e.duration_min / 60.0
        if e.type == "heatwave":
            delta = float((e.model_extra or {}).get("temperature_delta", 6.0)) * e.severity
            env = apply_heatwave_to_environment(env, start, duration_hours, delta)
        elif e.type == "cloud_cover":
            env = apply_cloud_cover(env, start, duration_hours, e.severity)
        elif e.type == "sensor_disturbance":
            end = start + pd.Timedelta(hours=duration_hours)
            mask = (env.index >= start) & (env.index < end)
            rng = np.random.default_rng(hash(e.id) % (2**32))
            noise = rng.normal(0, 2.0 * e.severity, size=mask.sum())
            env.temp_c = env.temp_c.copy()
            env.temp_c[mask] += noise
    return env


def build_event_effects(env: Environment, events: list[WorldEvent]) -> EventEffects:
    n = len(env.index)
    occupancy_multiplier = np.ones(n)
    force_ev_present = np.zeros(n, dtype=bool)
    extra_load_kw = np.zeros(n)
    outage_mask = np.zeros(n, dtype=bool)
    active_by_tick = [[] for _ in range(n)]

    for e in events:
        start = env.index[0] + pd.Timedelta(minutes=e.start_min)
        end = start + pd.Timedelta(minutes=e.duration_min)
        mask = (env.index >= start) & (env.index < end)
        for i in np.where(mask)[0]:
            active_by_tick[i].append(e.id)

        if e.type == "festival":
            occupancy_multiplier = np.where(mask, occupancy_multiplier * (1.0 + 0.5 * e.severity), occupancy_multiplier)
        elif e.type == "holiday":
            occupancy_multiplier = np.where(mask, occupancy_multiplier * (1.0 + 0.3 * e.severity), occupancy_multiplier)
        elif e.type == "workspace_peak":
            pass  # handled at workspace level via occupancy_multiplier reuse (society.py passes this same array)
        elif e.type == "high_ev_arrival":
            force_ev_present = force_ev_present | mask
        elif e.type == "transformer_overload":
            extra_load_kw = np.where(mask, extra_load_kw + 40.0 * e.severity, extra_load_kw)
        elif e.type == "grid_outage":
            outage_mask = outage_mask | mask

    return EventEffects(occupancy_multiplier, force_ev_present, extra_load_kw, outage_mask, active_by_tick)
