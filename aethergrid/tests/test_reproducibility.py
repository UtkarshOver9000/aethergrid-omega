"""TEST 1 (PART AR): same seed + same JSON = identical results."""
from __future__ import annotations

import numpy as np

from aethergrid.core.world import World
from aethergrid.core.timestep import simulate_building_series
from aethergrid.evaluation.baselines import rule_based_policy
from aethergrid.schemas.experiment import ObjectiveWeights
from aethergrid.tariff.bill import BillEngine


def test_identical_seed_and_json_produce_identical_world(tiny_world_path):
    w1 = World.load(tiny_world_path)
    w2 = World.load(tiny_world_path)
    b1, b2 = w1.buildings["T01_office"], w2.buildings["T01_office"]
    np.testing.assert_array_equal(b1.profile.base_load_kw, b2.profile.base_load_kw)
    np.testing.assert_array_equal(b1.profile.solar_potential_kw, b2.profile.solar_potential_kw)
    np.testing.assert_array_equal(w1.weather["temp_c"].values, w2.weather["temp_c"].values)


def test_identical_seed_and_json_produce_identical_simulation_and_bill(tiny_world_path):
    def run():
        w = World.load(tiny_world_path)
        b = w.buildings["T01_office"]
        series = simulate_building_series(
            b, w, rule_based_policy, horizon_steps=8, risk_level=0.05, weights=ObjectiveWeights(),
            carbon_kg_per_kwh=0.71, forecast_base_load_fn=lambda t, H: {}, forecast_solar_fn=lambda t, H: {},
        )
        bill = BillEngine.compute(w.index, series.import_kw, series.export_kw, w.dt_hours, w.tariff)
        return series, bill

    series1, bill1 = run()
    series2, bill2 = run()
    np.testing.assert_array_equal(series1.import_kw, series2.import_kw)
    np.testing.assert_array_equal(series1.indoor_temp_c, series2.indoor_temp_c)
    assert bill1.total == bill2.total
