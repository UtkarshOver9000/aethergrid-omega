"""CLI entry point: `python -m aethergrid.run --world {society,colony,connection} --scenario <path>`.

Runs the requested world end to end with the hierarchical_hybrid /
quantile-aware controller (the "AETHERGRID" arm) and prints a summary --
this is the smallest possible proof that JSON -> building -> forecast ->
optimizer -> simulator -> bill -> metrics is wired correctly (PART BE
quality gate)."""
from __future__ import annotations

import argparse
import json
import sys

from aethergrid.core.world import World
from aethergrid.energy_dna.signatures import compute_world_dna
from aethergrid.evaluation.experiments import get_forecasters
from aethergrid.evaluation.metrics import compute_metrics
from aethergrid.evaluation.baselines import quantile_mpc_policy
from aethergrid.schemas.experiment import ObjectiveWeights
from aethergrid.simulation.colony import simulate_colony, summarize_resilience
from aethergrid.stress.engine import build_stress_context
from aethergrid.tariff.bill import BillEngine
from aethergrid.core.timestep import simulate_building_series


def run_society_or_connection(world: World) -> dict:
    weights = ObjectiveWeights()
    per_building = {}
    total_bill = 0.0
    for bid, building in world.buildings.items():
        load_pf, solar_pf = get_forecasters(building.archetype.type, seed=world.spec.world.seed)
        base_fc = lambda t, H, b=building, pf=load_pf: pf.forecast_path(b.profile.base_load_kw, t, H)
        solar_fc = lambda t, H, b=building, pf=solar_pf: pf.forecast_path(b.profile.solar_potential_kw, t, H)
        series = simulate_building_series(
            building, world, quantile_mpc_policy, horizon_steps=32, risk_level=0.05, weights=weights,
            carbon_kg_per_kwh=0.71, forecast_base_load_fn=base_fc, forecast_solar_fn=solar_fc,
        )
        bill = BillEngine.compute(world.index, series.import_kw, series.export_kw, world.dt_hours, world.tariff)
        per_building[bid] = compute_metrics(series, bill, world.dt_hours, 0.71)
        total_bill += bill.total
        print(f"  [{bid:16s}] bill=Rs.{bill.total:>10,.0f}  peak={bill.peak_demand_kw:>7.1f}kW  "
              f"comfort_violations={per_building[bid]['comfort_soft_violations_steps']:>4d}")

    result = {"total_bill_inr": round(total_bill, 2), "per_building": per_building}

    if world.spec.world.type == "connection":
        from aethergrid.graph.graph import build_energy_opportunity_graph
        print("\n  Discovering Energy Opportunity Graph (this runs real counterfactual simulations, ~1-2 min per top candidate)...")
        dna = compute_world_dna(world)
        pf_by_type = {b.archetype.type: get_forecasters(b.archetype.type, world.spec.world.seed)[0] for b in world.buildings.values()}
        sf_by_type = {b.archetype.type: get_forecasters(b.archetype.type, world.spec.world.seed)[1] for b in world.buildings.values()}
        graph_result = build_energy_opportunity_graph(world, dna, pf_by_type, sf_by_type, k=2, run_economics=True)
        result["top_candidates"] = [c.as_dict() for c in graph_result.top_candidates]
        for c in graph_result.top_candidates:
            print(f"  [{c.edge.source} <-> {c.edge.sink}] {c.edge.kind}: {c.status} -- {c.reasons[-1] if c.reasons else ''}")

    return result


def run_colony(world: World) -> dict:
    weights = ObjectiveWeights()
    criticality = {bid: b.criticality for bid, b in world.buildings.items()}
    policies, forecast_fns = {}, {}
    for bid, building in world.buildings.items():
        load_pf, solar_pf = get_forecasters(building.archetype.type, seed=world.spec.world.seed)
        policies[bid] = quantile_mpc_policy
        forecast_fns[bid] = (
            lambda t, H, b=building, pf=load_pf: pf.forecast_path(b.profile.base_load_kw, t, H),
            lambda t, H, b=building, pf=solar_pf: pf.forecast_path(b.profile.solar_potential_kw, t, H),
        )

    import numpy as np
    outage_mask = np.zeros(world.n_steps, dtype=bool)
    outage_start = world.n_steps // 3
    outage_mask[outage_start:outage_start + int(4 / world.dt_hours)] = True
    print(f"  Simulating colony with a {4}h outage starting at step {outage_start}...")

    series = simulate_colony(world, policies, forecast_fns, criticality, weights, 0.71, outage_mask=outage_mask)
    bills_total = sum(
        BillEngine.compute(world.index, s.import_kw, s.export_kw, world.dt_hours, world.tariff).total
        for s in series.values()
    )
    for bid, s in series.items():
        print(f"  [{bid:16s}] criticality={criticality[bid]:.2f}  unserved_kwh={float(s.unserved_kw.sum()*world.dt_hours):>8.1f}")

    summary = summarize_resilience(series, world, criticality, outage_mask, bills_total)
    print("\n  Resilience summary:", json.dumps(summary.as_dict(), indent=2))
    return {"resilience": summary.as_dict()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an AETHERGRID Omega world end to end.")
    parser.add_argument("--world", required=True, choices=["society", "colony", "connection"])
    parser.add_argument("--scenario", required=True, help="Path to a world JSON config")
    args = parser.parse_args()

    print(f"Loading world '{args.world}' from {args.scenario} ...")
    world = World.load(args.scenario)
    print(f"  {len(world.buildings)} buildings, {world.n_steps} steps @ {world.dt_hours*60:.0f}min, "
          f"tariff='{world.tariff.id}'\n")

    if args.world == "colony":
        result = run_colony(world)
    else:
        result = run_society_or_connection(world)

    print("\nDone. Summary:")
    print(json.dumps({k: v for k, v in result.items() if k != "per_building"}, indent=2, default=str))


if __name__ == "__main__":
    main()
