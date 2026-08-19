"""Automatic ablation engine (PART W/AP): FULL system vs FULL-minus-X, run
on the same building/world/seed so any metric difference is attributable
to exactly the removed component. Axes implemented here are the ones
cleanly separable in this codebase; graph/coordination and EnergyDNA axes
are evaluated separately in the connection-world synergy report
(synergy/discovery.py + graph/graph.py), since those components act on
building-PAIR decisions, not single-building dispatch -- see
docs/LIMITATIONS.md for the full list of what an ablation axis here does
and does not cover."""
from __future__ import annotations

import json

from aethergrid.core.building import Building
from aethergrid.core.timestep import simulate_building_series
from aethergrid.core.world import World
from aethergrid.evaluation.baselines import mean_mpc_policy, quantile_mpc_policy
from aethergrid.evaluation.metrics import compute_metrics
from aethergrid.forecasting.path_forecast import PathForecaster
from aethergrid.schemas.experiment import ObjectiveWeights
from aethergrid.tariff.bill import BillEngine
from aethergrid.tariff.compiler import compile_tariff


def _flat_tariff(world: World):
    hours = world.index.hour.values + world.index.minute.values / 60.0
    avg_rate = float(sum(world.tariff.rate_at(h) for h in hours) / len(hours))
    return compile_tariff({
        "id": f"{world.tariff.id}_flattened", "flat_energy_rate_per_kwh": avg_rate,
        "fixed_charge_per_day": world.tariff.fixed_charge_per_day,
        "demand_charge_per_kva": world.tariff.demand_charge_per_kva,
        "contract_demand_kva": world.tariff.contract_demand_kva,
        "demand_excess_penalty_multiplier": world.tariff.demand_excess_penalty_multiplier,
    })


def run_ablation(building: Building, world: World, load_pf: PathForecaster, solar_pf: PathForecaster,
                  carbon_kg_per_kwh: float = 0.71, risk_level: float = 0.05) -> dict:
    base_fc = lambda t, H: load_pf.forecast_path(building.profile.base_load_kw, t, H)
    solar_fc = lambda t, H: solar_pf.forecast_path(building.profile.solar_potential_kw, t, H)
    real_tariff = world.tariff

    def run(policy, weights, tariff_for_planning=None, apply_shield=True, label=""):
        w = world
        if tariff_for_planning is not None:
            w = World(spec=world.spec, index=world.index, dt_hours=world.dt_hours, weather=world.weather,
                      buildings=world.buildings, tariff=tariff_for_planning, grid_capacity_kw=world.grid_capacity_kw)
        series = simulate_building_series(
            building, w, policy, horizon_steps=32, risk_level=risk_level, weights=weights,
            carbon_kg_per_kwh=carbon_kg_per_kwh, forecast_base_load_fn=base_fc, forecast_solar_fn=solar_fc,
            apply_shield=apply_shield,
        )
        bill = BillEngine.compute(world.index, series.import_kw, series.export_kw, world.dt_hours, real_tariff)
        return compute_metrics(series, bill, world.dt_hours, carbon_kg_per_kwh)

    flat_tariff = _flat_tariff(world)
    full_weights = ObjectiveWeights()
    no_resilience_weights = ObjectiveWeights(resilience_penalty=0.0)

    variants = {
        "FULL": lambda: run(quantile_mpc_policy, full_weights),
        "FULL_minus_uncertainty": lambda: run(mean_mpc_policy, full_weights),
        "FULL_minus_tariff_awareness": lambda: run(quantile_mpc_policy, full_weights, tariff_for_planning=flat_tariff),
        "FULL_minus_resilience": lambda: run(quantile_mpc_policy, no_resilience_weights),
        "FULL_minus_safety_shield": lambda: run(quantile_mpc_policy, full_weights, apply_shield=False),
    }

    results = {name: fn() for name, fn in variants.items()}
    full_bill = results["FULL"]["total_bill_inr"]
    for name, m in results.items():
        m["delta_bill_vs_full_inr"] = round(m["total_bill_inr"] - full_bill, 2)
        m["delta_bill_vs_full_pct"] = round(100 * (m["total_bill_inr"] - full_bill) / abs(full_bill), 2) if full_bill else 0.0

    return results
