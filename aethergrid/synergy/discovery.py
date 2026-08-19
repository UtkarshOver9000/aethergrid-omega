"""Synergy discovery (PART N): for every building pair and every
opportunity type, compute S(A,B) = weighted_benefit - weighted_cost -
weighted_risk. Weights are an explicit, visible dataclass -- never hidden
inside the scoring function (PART N: "Weights must be visible in
configuration. Do not hide them.")."""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Literal

from aethergrid.core.world import World
from aethergrid.energy_dna.signatures import EnergyDNA
from aethergrid.graph.compatibility import EdgeFeatures, compute_edge_features
from aethergrid.graph.features import synthetic_coordinates

EdgeStatus = Literal[
    "DISCOVERED", "TECHNICALLY_PLAUSIBLE", "ECONOMICALLY_VIABLE", "RECOMMENDED", "REJECTED",
]

OPPORTUNITY_TYPES = [
    "thermal_match", "flexibility_match", "storage_coordination",
    "solar_load_match", "peak_complementarity",
]


@dataclass
class SynergyWeights:
    """Visible, configurable weights for S(A,B). Sums are not constrained
    to 1.0 -- these are relative importances, not a probability simplex."""
    w_temporal_complementarity: float = 1.0
    w_thermal_complementarity: float = 1.0
    w_flexibility_compatibility: float = 0.8
    w_capacity_compatibility: float = 0.6
    w_geographic_feasibility: float = 0.5
    w_resilience_benefit: float = 0.7
    w_infrastructure_cost: float = 1.0   # cost term, INR normalized by DIVISOR below
    w_comfort_risk: float = 1.2          # risk term
    infrastructure_cost_divisor: float = 50000.0  # normalizes INR cost onto ~[0,1+] scale


@dataclass
class SynergyCandidate:
    edge: EdgeFeatures
    score: float
    benefit_component: float
    cost_component: float
    risk_component: float
    status: EdgeStatus = "DISCOVERED"
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = self.edge.as_dict()
        d.update({
            "score": round(self.score, 4), "status": self.status, "reasons": self.reasons,
            "benefit_component": round(self.benefit_component, 4),
            "cost_component": round(self.cost_component, 4),
            "risk_component": round(self.risk_component, 4),
        })
        return d


def score_edge(edge: EdgeFeatures, w: SynergyWeights) -> tuple[float, float, float, float]:
    benefit = (
        w.w_temporal_complementarity * edge.temporal_complementarity
        + w.w_thermal_complementarity * edge.thermal_complementarity
        + w.w_flexibility_compatibility * edge.flexibility_compatibility
        + w.w_capacity_compatibility * edge.capacity_compatibility
        + w.w_geographic_feasibility * edge.geographic_feasibility
        + w.w_resilience_benefit * edge.resilience_benefit
    )
    cost = w.w_infrastructure_cost * (edge.infrastructure_cost_inr / w.infrastructure_cost_divisor)
    risk = w.w_comfort_risk * edge.comfort_risk
    score = benefit - cost - risk
    return score, benefit, cost, risk


def discover_candidates(world: World, dna_map: dict[str, EnergyDNA], weights: SynergyWeights | None = None,
                         opportunity_types: list[str] | None = None) -> list[SynergyCandidate]:
    weights = weights or SynergyWeights()
    opportunity_types = opportunity_types or OPPORTUNITY_TYPES
    coords = {bid: synthetic_coordinates(bid) for bid in world.building_ids}

    candidates = []
    for a_id, b_id in combinations(world.building_ids, 2):
        a, b = world.buildings[a_id], world.buildings[b_id]
        for kind in opportunity_types:
            edge = compute_edge_features(a, b, dna_map[a_id], dna_map[b_id], coords[a_id], coords[b_id], kind)
            score, benefit, cost, risk = score_edge(edge, weights)
            candidates.append(SynergyCandidate(edge, score, benefit, cost, risk))
    return candidates


def top_k(candidates: list[SynergyCandidate], k: int = 5) -> list[SynergyCandidate]:
    return sorted(candidates, key=lambda c: c.score, reverse=True)[:k]
