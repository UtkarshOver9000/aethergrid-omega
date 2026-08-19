"""Counterfactual connection test (PART O) -- the mechanism that lets the
system say "DO NOT CONNECT." Three runs, identical weather/demand/tariff/
seed/initial state:

  RUN A: both buildings optimized independently, billed independently.
  RUN B: same physical dispatch as A (connection changes nothing about
         HOW either building operates) but billed as ONE combined meter --
         isolates the pure financial-netting benefit of demand-charge
         diversity and solar export offsetting import (a real mechanism
         requiring no physical energy transfer at all, PART AZ Types 2-5).
  RUN C: both buildings re-optimize with a coordination price signal
         derived from the counterpart's RUN-A import trace (Level-2 style
         single-pass coordination), billed as one combined meter -- isolates
         the additional benefit of actually SCHEDULING around each other.

For `thermal_match` (the one mechanism this system allows to move real
energy, PART AZ Type 1), RUN C additionally reduces the sink building's DHW
electrical draw by a physically-grounded transferred-heat estimate.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from aethergrid.core.building import Building
from aethergrid.core.timestep import SimulationSeries, simulate_building_series
from aethergrid.core.world import World
from aethergrid.evaluation.baselines import quantile_mpc_policy
from aethergrid.forecasting.path_forecast import PathForecaster
from aethergrid.schemas.experiment import ObjectiveWeights
from aethergrid.tariff.bill import BillBreakdown, BillEngine

THERMAL_TRANSFER_EFFICIENCY = 0.55  # heat-exchanger + short-pipe-run loss, assumed


@dataclass
class CounterfactualResult:
    source_id: str
    sink_id: str
    kind: str
    bill_A_inr: float
    bill_B_inr: float
    bill_C_inr: float
    peak_A_sum_kw: float  # sum of each building's OWN peak if billed separately (RUN A demand-charge basis)
    peak_B_kw: float       # peak of the single combined meter, same dispatch as A (RUN B)
    peak_C_kw: float       # peak of the single combined meter, coordinated dispatch (RUN C)
    energy_A_kwh: float
    energy_C_kwh: float
    comfort_violations_A: int
    comfort_violations_C: int
    carbon_A_kg: float
    carbon_C_kg: float
    netting_benefit_inr: float     # A - B (financial netting alone, no re-dispatch)
    coordination_benefit_inr: float  # B - C (extra benefit of actual re-scheduling)
    total_benefit_inr: float       # A - C
    infrastructure_cost_inr: float
    payback_years: float | None
    recommendation: str

    def as_dict(self) -> dict:
        return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


def _simulate(building: Building, world: World, load_pf: PathForecaster, solar_pf: PathForecaster,
              weights: ObjectiveWeights, carbon_kg_per_kwh: float, coordination_price: np.ndarray | None = None,
              dhw_draw_override: np.ndarray | None = None) -> SimulationSeries:
    if dhw_draw_override is not None:
        original = building.profile.dhw_draw_kw
        building.profile.dhw_draw_kw = dhw_draw_override
    try:
        series = simulate_building_series(
            building, world, quantile_mpc_policy, horizon_steps=32, risk_level=0.05,
            weights=weights, carbon_kg_per_kwh=carbon_kg_per_kwh,
            forecast_base_load_fn=lambda t, H: load_pf.forecast_path(building.profile.base_load_kw, t, H),
            forecast_solar_fn=lambda t, H: solar_pf.forecast_path(building.profile.solar_potential_kw, t, H),
            coordination_price_per_kwh=coordination_price,
        )
    finally:
        if dhw_draw_override is not None:
            building.profile.dhw_draw_kw = original
    return series


def run_counterfactual(
    world: World, source_id: str, sink_id: str, kind: str,
    load_pf_by_type: dict[str, PathForecaster], solar_pf_by_type: dict[str, PathForecaster],
    weights: ObjectiveWeights, carbon_kg_per_kwh: float, infrastructure_cost_inr: float,
    price_scale: float = 3.0, evaluation_years: float = 10.0,
) -> CounterfactualResult:
    a, b = world.buildings[source_id], world.buildings[sink_id]
    load_pf_a, solar_pf_a = load_pf_by_type[a.archetype.type], solar_pf_by_type[a.archetype.type]
    load_pf_b, solar_pf_b = load_pf_by_type[b.archetype.type], solar_pf_by_type[b.archetype.type]

    # RUN A -- independent
    series_a = _simulate(a, world, load_pf_a, solar_pf_a, weights, carbon_kg_per_kwh)
    series_b = _simulate(b, world, load_pf_b, solar_pf_b, weights, carbon_kg_per_kwh)
    bill_a_solo = BillEngine.compute(world.index, series_a.import_kw, series_a.export_kw, world.dt_hours, world.tariff)
    bill_b_solo = BillEngine.compute(world.index, series_b.import_kw, series_b.export_kw, world.dt_hours, world.tariff)
    bill_A = bill_a_solo.total + bill_b_solo.total
    peak_A_sum = bill_a_solo.peak_demand_kw + bill_b_solo.peak_demand_kw

    # RUN B -- same dispatch, combined virtual meter (pure netting)
    combined_import_B = series_a.import_kw + series_b.import_kw
    combined_export_B = series_a.export_kw + series_b.export_kw
    bill_B_obj = BillEngine.compute(world.index, combined_import_B, combined_export_B, world.dt_hours, world.tariff)
    bill_B = bill_B_obj.total

    # RUN C -- coordinated re-dispatch (+ physical transfer if thermal_match)
    price_a = price_scale * series_b.import_kw / max(series_b.import_kw.max(), 1e-6)
    price_b = price_scale * series_a.import_kw / max(series_a.import_kw.max(), 1e-6)

    dhw_override_b = None
    if kind == "thermal_match" and b.resources.has_dhw:
        transferable_kw = np.clip(series_a.hvac_kw, 0, None) * 0.15 * THERMAL_TRANSFER_EFFICIENCY
        dhw_override_b = np.maximum(0.0, b.profile.dhw_draw_kw - transferable_kw)

    series_a_c = _simulate(a, world, load_pf_a, solar_pf_a, weights, carbon_kg_per_kwh, coordination_price=price_a)
    series_b_c = _simulate(b, world, load_pf_b, solar_pf_b, weights, carbon_kg_per_kwh,
                            coordination_price=price_b, dhw_draw_override=dhw_override_b)
    combined_import_C = series_a_c.import_kw + series_b_c.import_kw
    combined_export_C = series_a_c.export_kw + series_b_c.export_kw
    bill_C_obj = BillEngine.compute(world.index, combined_import_C, combined_export_C, world.dt_hours, world.tariff)
    bill_C = bill_C_obj.total

    energy_A = float(np.sum(series_a.import_kw + series_b.import_kw) * world.dt_hours)
    energy_C = float(np.sum(combined_import_C) * world.dt_hours)
    comfort_A = int(series_a.comfort_soft_violation.sum() + series_b.comfort_soft_violation.sum())
    comfort_C = int(series_a_c.comfort_soft_violation.sum() + series_b_c.comfort_soft_violation.sum())
    carbon_A = energy_A * carbon_kg_per_kwh
    carbon_C = energy_C * carbon_kg_per_kwh

    n_days = world.spec.world.duration_days
    annualize = 365.0 / n_days
    netting_benefit = (bill_A - bill_B) * annualize
    coordination_benefit = (bill_B - bill_C) * annualize
    total_benefit = (bill_A - bill_C) * annualize
    extrapolation_note = (
        f"NOTE: annualized figures are a naive linear extrapolation of a {n_days}-day simulated sample "
        f"(x{annualize:.1f}) -- they do NOT account for seasonal variation and should be read as an "
        f"indicative order of magnitude, not a validated annual forecast. See docs/LIMITATIONS.md."
    )

    if total_benefit <= 0:
        payback = None
        recommendation = "DO NOT CONNECT: no positive annualized benefit under coordinated operation."
    else:
        payback = infrastructure_cost_inr / total_benefit
        if payback > evaluation_years:
            recommendation = (
                f"DO NOT CONNECT: payback {payback:.1f}y exceeds {evaluation_years:.0f}y evaluation horizon."
            )
        else:
            recommendation = f"CONNECT: payback {payback:.1f}y within {evaluation_years:.0f}y horizon."
    recommendation = f"{recommendation} {extrapolation_note}"

    return CounterfactualResult(
        source_id=source_id, sink_id=sink_id, kind=kind,
        bill_A_inr=bill_A, bill_B_inr=bill_B, bill_C_inr=bill_C,
        peak_A_sum_kw=peak_A_sum, peak_B_kw=bill_B_obj.peak_demand_kw, peak_C_kw=bill_C_obj.peak_demand_kw,
        energy_A_kwh=energy_A, energy_C_kwh=energy_C,
        comfort_violations_A=comfort_A, comfort_violations_C=comfort_C,
        carbon_A_kg=carbon_A, carbon_C_kg=carbon_C,
        netting_benefit_inr=netting_benefit, coordination_benefit_inr=coordination_benefit,
        total_benefit_inr=total_benefit, infrastructure_cost_inr=infrastructure_cost_inr,
        payback_years=payback, recommendation=recommendation,
    )
