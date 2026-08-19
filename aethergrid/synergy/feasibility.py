"""Technical feasibility gate (PART D/N): DISCOVERED -> TECHNICALLY_PLAUSIBLE
or REJECTED. This never touches economics -- only "can this physically /
operationally work at all", per opportunity-type-specific criteria."""
from __future__ import annotations

from aethergrid.synergy.discovery import SynergyCandidate

MIN_COMPLEMENTARITY = 0.30
MIN_GEOGRAPHIC_FEASIBILITY = 0.05
MIN_CAPACITY_COMPATIBILITY = 0.10


def assess_technical_feasibility(candidate: SynergyCandidate) -> SynergyCandidate:
    e = candidate.edge
    reasons = []

    if e.geographic_feasibility <= MIN_GEOGRAPHIC_FEASIBILITY:
        reasons.append(
            f"REJECTED: distance {e.distance_m:.0f}m exceeds feasible range for mechanism "
            f"'{e.mechanism}' (geographic_feasibility={e.geographic_feasibility:.2f})"
        )

    if e.kind == "thermal_match":
        if e.thermal_complementarity < MIN_COMPLEMENTARITY:
            reasons.append(
                f"REJECTED: thermal_complementarity={e.thermal_complementarity:.2f} below "
                f"threshold {MIN_COMPLEMENTARITY} -- no meaningful heat-reject/heat-need overlap"
            )
    elif e.kind in ("flexibility_match", "storage_coordination"):
        if e.flexibility_compatibility < MIN_COMPLEMENTARITY and e.capacity_compatibility < MIN_CAPACITY_COMPATIBILITY:
            reasons.append(
                f"REJECTED: flexibility_compatibility={e.flexibility_compatibility:.2f} and "
                f"capacity_compatibility={e.capacity_compatibility:.2f} both below usable thresholds"
            )
    elif e.kind in ("solar_load_match", "peak_complementarity"):
        if e.temporal_complementarity < MIN_COMPLEMENTARITY:
            reasons.append(
                f"REJECTED: temporal_complementarity={e.temporal_complementarity:.2f} below "
                f"threshold {MIN_COMPLEMENTARITY} -- profiles do not meaningfully offset"
            )

    if reasons:
        candidate.status = "REJECTED"
        candidate.reasons.extend(reasons)
    else:
        candidate.status = "TECHNICALLY_PLAUSIBLE"
        candidate.reasons.append(
            f"TECHNICALLY_PLAUSIBLE: mechanism='{e.mechanism}', "
            f"distance={e.distance_m:.0f}m, complementarity checks passed"
        )
    return candidate
