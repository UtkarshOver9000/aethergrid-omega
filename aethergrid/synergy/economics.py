"""Economic viability gate (PART O): TECHNICALLY_PLAUSIBLE -> ECONOMICALLY_VIABLE
-> RECOMMENDED, or REJECTED with an explicit "DO NOT CONNECT" reason. This
is the only module allowed to move an edge past TECHNICALLY_PLAUSIBLE, and
it never does so without a real counterfactual run backing the number."""
from __future__ import annotations

from aethergrid.core.world import World
from aethergrid.forecasting.path_forecast import PathForecaster
from aethergrid.schemas.experiment import ObjectiveWeights
from aethergrid.synergy.counterfactual import CounterfactualResult, run_counterfactual
from aethergrid.synergy.discovery import SynergyCandidate

MAX_PAYBACK_YEARS = 5.0
MAX_COMFORT_RISK_FOR_RECOMMENDATION = 0.5


def assess_economics(
    candidate: SynergyCandidate, world: World,
    load_pf_by_type: dict[str, PathForecaster], solar_pf_by_type: dict[str, PathForecaster],
    weights: ObjectiveWeights, carbon_kg_per_kwh: float,
) -> tuple[SynergyCandidate, CounterfactualResult]:
    if candidate.status != "TECHNICALLY_PLAUSIBLE":
        raise ValueError("assess_economics requires a TECHNICALLY_PLAUSIBLE candidate")

    e = candidate.edge
    cf = run_counterfactual(
        world, e.source, e.sink, e.kind, load_pf_by_type, solar_pf_by_type,
        weights, carbon_kg_per_kwh, e.infrastructure_cost_inr, evaluation_years=MAX_PAYBACK_YEARS * 2,
    )

    if cf.total_benefit_inr <= 0 or cf.payback_years is None or cf.payback_years > MAX_PAYBACK_YEARS:
        candidate.status = "REJECTED"
        candidate.reasons.append(cf.recommendation)
    else:
        candidate.status = "ECONOMICALLY_VIABLE"
        candidate.reasons.append(
            f"ECONOMICALLY_VIABLE: annualized benefit Rs.{cf.total_benefit_inr:,.0f}, "
            f"payback {cf.payback_years:.1f}y (threshold {MAX_PAYBACK_YEARS:.0f}y)"
        )
        if e.comfort_risk <= MAX_COMFORT_RISK_FOR_RECOMMENDATION and cf.comfort_violations_C <= cf.comfort_violations_A:
            candidate.status = "RECOMMENDED"
            candidate.reasons.append(
                f"RECOMMENDED: comfort_risk={e.comfort_risk:.2f} acceptable and coordinated comfort "
                f"violations ({cf.comfort_violations_C}) did not worsen vs baseline ({cf.comfort_violations_A})"
            )
        else:
            candidate.reasons.append(
                f"Held at ECONOMICALLY_VIABLE (not RECOMMENDED): comfort_risk={e.comfort_risk:.2f} or "
                f"comfort violations increased under coordination ({cf.comfort_violations_A} -> {cf.comfort_violations_C})"
            )

    return candidate, cf
