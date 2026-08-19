"""Counterfactual connection test sanity (PART O). Confirms the mechanism
runs end to end, is deterministic, and CAN recommend against connecting --
i.e. the system is capable of saying "DO NOT CONNECT", not just approving
whatever is discovered."""
from __future__ import annotations

from aethergrid.core.world import World
from aethergrid.forecasting.path_forecast import PathForecaster
from aethergrid.forecasting.predict import build_training_building
from aethergrid.schemas.experiment import ObjectiveWeights
from aethergrid.synergy.counterfactual import run_counterfactual


def _forecasters_for(world: World, seed: int):
    load_pf, solar_pf = {}, {}
    for b in world.buildings.values():
        _, train_df = build_training_building(b.archetype.type, seed=seed, n_days=20, dt_minutes=15)
        load_pf[b.archetype.type] = PathForecaster.fit(train_df["base_load_kw"].values, 96, 32)
        solar_pf[b.archetype.type] = PathForecaster.fit(train_df["solar_kw"].values, 96, 32)
    return load_pf, solar_pf


def test_counterfactual_runs_and_is_deterministic(tiny_world_2b_path):
    world = World.load(tiny_world_2b_path)
    load_pf, solar_pf = _forecasters_for(world, seed=3)

    r1 = run_counterfactual(world, "T01_office", "T02_retail", "peak_complementarity",
                             load_pf, solar_pf, ObjectiveWeights(), 0.71, infrastructure_cost_inr=6000)
    r2 = run_counterfactual(world, "T01_office", "T02_retail", "peak_complementarity",
                             load_pf, solar_pf, ObjectiveWeights(), 0.71, infrastructure_cost_inr=6000)

    assert r1.bill_A_inr == r2.bill_A_inr
    assert r1.bill_C_inr == r2.bill_C_inr
    assert r1.recommendation == r2.recommendation


def test_counterfactual_can_reject_an_uneconomic_connection(tiny_world_2b_path):
    """An absurdly high infrastructure cost must force a DO NOT CONNECT
    recommendation -- proving REJECTED is a reachable outcome, not just
    RECOMMENDED (PART O)."""
    world = World.load(tiny_world_2b_path)
    load_pf, solar_pf = _forecasters_for(world, seed=3)

    result = run_counterfactual(
        world, "T01_office", "T02_retail", "peak_complementarity",
        load_pf, solar_pf, ObjectiveWeights(), 0.71, infrastructure_cost_inr=1e9,
    )
    assert result.payback_years is None or result.payback_years > 5
    assert "DO NOT CONNECT" in result.recommendation
