"""TEST 9 (PART AR): injecting a stress scenario changes simulation state."""
from __future__ import annotations

import pandas as pd

from aethergrid.core.timestep import simulate_building_series
from aethergrid.core.world import World
from aethergrid.evaluation.baselines import rule_based_policy
from aethergrid.schemas.event import EventSpec
from aethergrid.schemas.experiment import ObjectiveWeights
from aethergrid.stress.engine import build_stress_context


def test_grid_outage_event_forces_zero_import_and_unserved_load(tiny_world_path):
    world = World.load(tiny_world_path)
    building = world.buildings["T01_office"]
    event = EventSpec(type="grid_outage", start=world.index[10], duration_hours=1.0)
    stress = build_stress_context(world, [event])

    series = simulate_building_series(
        building, world, rule_based_policy, horizon_steps=8, risk_level=0.05, weights=ObjectiveWeights(),
        carbon_kg_per_kwh=0.71, forecast_base_load_fn=lambda t, H: {}, forecast_solar_fn=lambda t, H: {},
        outage_mask=stress.outage_mask,
    )
    assert (series.import_kw[10:14] == 0.0).all()
    assert series.unserved_kw[10:14].sum() > 0


def test_demand_spike_event_measurably_increases_reported_base_load(tiny_world_path):
    world = World.load(tiny_world_path)
    building = world.buildings["T01_office"]
    event = EventSpec(type="demand_spike", start=world.index[5], duration_hours=1.0, magnitude_kw=500.0)
    stress = build_stress_context(world, [event])
    addon = stress.demand_spike_addon(world, "T01_office")
    assert addon[5] == 500.0
    assert addon[0] == 0.0


def test_solar_failure_zeroes_solar_during_window(tiny_world_path):
    world = World.load(tiny_world_path)
    event = EventSpec(type="solar_failure", start=world.index[20], duration_hours=2.0)
    stress = build_stress_context(world, [event])
    assert stress.solar_failure_mask[20:28].all()
    assert not stress.solar_failure_mask[0]
