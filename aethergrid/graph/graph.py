"""EnergyOpportunityGraph: the orchestration that ties discovery ->
feasibility -> (top-K only) economics into one NetworkX graph the dashboard
and evaluation reports both consume (PART AG/AY). Built with plain
NetworkX + engineered features per the Tier-B fallback policy (no GNN)."""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from aethergrid.core.world import World
from aethergrid.energy_dna.signatures import EnergyDNA
from aethergrid.forecasting.path_forecast import PathForecaster
from aethergrid.graph.features import node_feature_dict, synthetic_coordinates
from aethergrid.graph.ranking import rank_and_select
from aethergrid.schemas.experiment import ObjectiveWeights
from aethergrid.synergy.counterfactual import CounterfactualResult
from aethergrid.synergy.discovery import SynergyCandidate, SynergyWeights, discover_candidates
from aethergrid.synergy.economics import assess_economics
from aethergrid.synergy.feasibility import assess_technical_feasibility

STATUS_COLOR = {
    "DISCOVERED": "#9aa0a6", "TECHNICALLY_PLAUSIBLE": "#f2c94c",
    "ECONOMICALLY_VIABLE": "#6fcf97", "RECOMMENDED": "#27ae60", "REJECTED": "#eb5757",
}


@dataclass
class OpportunityGraphResult:
    graph: nx.Graph
    all_candidates: list[SynergyCandidate]
    top_candidates: list[SynergyCandidate]
    counterfactuals: dict[str, CounterfactualResult]


def build_energy_opportunity_graph(
    world: World, dna_map: dict[str, EnergyDNA],
    load_pf_by_type: dict[str, PathForecaster] | None = None,
    solar_pf_by_type: dict[str, PathForecaster] | None = None,
    synergy_weights: SynergyWeights | None = None, objective_weights: ObjectiveWeights | None = None,
    carbon_kg_per_kwh: float = 0.71, k: int = 5, run_economics: bool = True,
) -> OpportunityGraphResult:
    synergy_weights = synergy_weights or SynergyWeights()
    objective_weights = objective_weights or ObjectiveWeights()

    G = nx.Graph()
    coords = {bid: synthetic_coordinates(bid) for bid in world.building_ids}
    for bid in world.building_ids:
        G.add_node(bid, **node_feature_dict(dna_map[bid], coords[bid]))

    all_candidates = discover_candidates(world, dna_map, synergy_weights)
    for c in all_candidates:
        assess_technical_feasibility(c)

    top_candidates = rank_and_select(all_candidates, k=k)

    counterfactuals: dict[str, CounterfactualResult] = {}
    if run_economics and load_pf_by_type and solar_pf_by_type:
        for c in top_candidates:
            c, cf = assess_economics(c, world, load_pf_by_type, solar_pf_by_type, objective_weights, carbon_kg_per_kwh)
            key = f"{c.edge.source}--{c.edge.sink}--{c.edge.kind}"
            counterfactuals[key] = cf

    for c in all_candidates:
        key = (c.edge.source, c.edge.sink)
        existing_score = G.edges[key]["score"] if G.has_edge(*key) else -1e18
        if c.score > existing_score:
            edge_attrs = c.edge.as_dict()  # already has source, sink, kind, mechanism, ...
            G.add_edge(
                c.edge.source, c.edge.sink, score=c.score, status=c.status,
                color=STATUS_COLOR[c.status], reasons=list(c.reasons), **edge_attrs,
            )

    return OpportunityGraphResult(G, all_candidates, top_candidates, counterfactuals)
