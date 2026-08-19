"""Top-K discovery (PART N): rank ALL discovered candidates cheaply, then
only the top K are ever handed to the (expensive, simulation-backed)
economics gate. This keeps the discovery step cheap and exhaustive while
keeping counterfactual testing tractable."""
from __future__ import annotations

from aethergrid.synergy.discovery import SynergyCandidate, top_k

DEFAULT_K = 5


def rank_and_select(candidates: list[SynergyCandidate], k: int = DEFAULT_K) -> list[SynergyCandidate]:
    plausible = [c for c in candidates if c.status == "TECHNICALLY_PLAUSIBLE"]
    return top_k(plausible, k)
