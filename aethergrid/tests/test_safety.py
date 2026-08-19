"""TEST 2 / TEST 4 (PART AR): unsafe actions get blocked/projected, and
indoor temperature never violates HARD limits across a full simulation."""
from __future__ import annotations

import numpy as np

from aethergrid.core.timestep import simulate_building_series
from aethergrid.optimization.safety_shield import project_action
from aethergrid.schemas.experiment import ObjectiveWeights


def test_grossly_unsafe_action_is_clipped_to_bounds(tiny_world):
    b = tiny_world.buildings["T01_office"]
    r = b.resources
    unsafe = {
        "hvac_kw": 1e6, "battery_charge_kw": 1e6, "battery_discharge_kw": 1e6,
        "dhw_heat_kw": 1e6, "ev_charge_kw": 1e6, "ts_charge_kw": 1e6, "ts_discharge_kw": 1e6,
    }
    safe = project_action(unsafe, r, b.state, temp_out_c=30.0, internal_gain_kw=5.0, dt_hours=0.25, ev_present=True)
    assert safe.hvac_kw <= r.hvac_capacity_kw + 1e-9
    assert safe.battery_charge_kw <= r.battery_power_kw + 1e-9
    assert safe.dhw_heat_kw <= r.dhw_capacity_kw + 1e-9
    assert len(safe.interventions) > 0  # the shield must report what it changed


def test_negative_action_request_is_clipped_to_zero(tiny_world):
    b = tiny_world.buildings["T01_office"]
    unsafe = {"hvac_kw": -50.0, "battery_charge_kw": -10.0, "battery_discharge_kw": 0.0,
              "dhw_heat_kw": 0.0, "ev_charge_kw": 0.0, "ts_charge_kw": 0.0, "ts_discharge_kw": 0.0}
    safe = project_action(unsafe, b.resources, b.state, 25.0, 5.0, 0.25, False)
    assert safe.hvac_kw == 0.0
    assert safe.battery_charge_kw == 0.0


def _always_maximal_hvac_policy(ctx):
    return {"hvac_kw": ctx.resources.hvac_capacity_kw * 10, "battery_charge_kw": 0.0,
            "battery_discharge_kw": 0.0, "dhw_heat_kw": 0.0, "ev_charge_kw": 0.0,
            "ts_charge_kw": 0.0, "ts_discharge_kw": 0.0}


def test_indoor_temperature_never_breaches_hard_bounds_under_a_reckless_policy(tiny_world):
    """Even a policy that always requests absurd HVAC output must be kept
    within hard bounds by the shield -- this is the core RULE 3 guarantee."""
    b = tiny_world.buildings["T01_office"]
    series = simulate_building_series(
        b, tiny_world, _always_maximal_hvac_policy, horizon_steps=8, risk_level=0.05,
        weights=ObjectiveWeights(), carbon_kg_per_kwh=0.71,
        forecast_base_load_fn=lambda t, H: {}, forecast_solar_fn=lambda t, H: {},
    )
    assert not series.comfort_hard_violation.any(), "hard comfort bound was breached despite the safety shield"
