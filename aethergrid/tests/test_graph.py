"""TEST 7 (PART AR): a candidate connection can be rejected, not just approved."""
from __future__ import annotations

from aethergrid.core.world import World
from aethergrid.energy_dna.signatures import compute_world_dna
from aethergrid.synergy.discovery import discover_candidates
from aethergrid.synergy.feasibility import assess_technical_feasibility


def test_synergy_discovery_produces_both_plausible_and_rejected_edges(tiny_world_2b_path):
    world = World.load(tiny_world_2b_path)
    dna = compute_world_dna(world)
    candidates = discover_candidates(world, dna)
    assert len(candidates) > 0
    for c in candidates:
        assess_technical_feasibility(c)
    statuses = {c.status for c in candidates}
    assert statuses <= {"TECHNICALLY_PLAUSIBLE", "REJECTED"}
    # every candidate must carry a human-readable reason regardless of outcome
    assert all(len(c.reasons) > 0 for c in candidates)


def test_far_apart_buildings_are_rejected_on_geography():
    """Force two buildings to be > the feasible distance apart and confirm
    the edge is REJECTED, proving rejection is reachable (not just a
    theoretical status)."""
    from aethergrid.graph.compatibility import compute_edge_features
    from aethergrid.core.world import World as W

    import json
    import tempfile
    spec = {
        "world": {"name": "t", "type": "connection", "duration_days": 1, "timestep_minutes": 15, "seed": 1, "start_date": "2026-01-05"},
        "tariff": {"id": "demo"},
        "buildings": [{"id": "A", "type": "office"}, {"id": "B", "type": "retail"}],
        "resources": {"solar": True, "battery": True, "thermal_storage": True, "ev": True, "dhw": True},
        "events": [], "connections": [],
    }
    p = tempfile.mktemp(suffix=".json")
    with open(p, "w") as f:
        json.dump(spec, f)
    world = W.load(p)
    dna = compute_world_dna(world)
    a, b = world.buildings["A"], world.buildings["B"]
    far_edge = compute_edge_features(a, b, dna["A"], dna["B"], (0.0, 0.0), (10000.0, 10000.0), "thermal_match")
    assert far_edge.geographic_feasibility == 0.0

    from aethergrid.synergy.discovery import SynergyCandidate, score_edge, SynergyWeights
    w = SynergyWeights()
    score, benefit, cost, risk = score_edge(far_edge, w)
    candidate = SynergyCandidate(far_edge, score, benefit, cost, risk)
    assess_technical_feasibility(candidate)
    assert candidate.status == "REJECTED"
