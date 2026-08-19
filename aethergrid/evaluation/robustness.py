"""Robustness / adversarial evaluation (PART R). For a given controller,
runs a NORMAL (no-event) simulation and each stress scenario, and reports
degradation relative to normal -- never a scenario in isolation, since a
"robustness score" is meaningless without the baseline it degrades from."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from aethergrid.core.building import Building
from aethergrid.core.timestep import PolicyFn, simulate_building_series
from aethergrid.core.world import World
from aethergrid.evaluation.metrics import compute_metrics
from aethergrid.schemas.event import EventSpec
from aethergrid.schemas.experiment import ObjectiveWeights
from aethergrid.stress.engine import build_stress_context
from aethergrid.tariff.bill import BillEngine

STRESS_SCENARIO_LIBRARY = {
    "heatwave": dict(type="heatwave", duration_hours=8, temperature_delta=6.0),
    "sensor_dropout": dict(type="sensor_dropout", duration_hours=6, uncertainty_inflation=2.5),
    "demand_spike": dict(type="demand_spike", duration_hours=2, magnitude_frac_of_peak=0.5),
    "solar_failure": dict(type="solar_failure", duration_hours=10),
    "grid_outage": dict(type="grid_outage", duration_hours=4),
    "building_failure": dict(type="building_failure", duration_hours=6),
    "forecast_bias": dict(type="forecast_bias", duration_hours=24, bias_pct=15.0),
}


@dataclass
class RobustnessResult:
    scenario: str
    normal_metrics: dict
    stressed_metrics: dict
    cost_degradation_frac: float
    comfort_degradation_steps: int
    peak_violation_kw: float
    critical_load_failure_frac: float
    recovery_time_steps: int | None
    robustness_score: float

    def as_dict(self) -> dict:
        return {
            "scenario": self.scenario, "cost_degradation_frac": round(self.cost_degradation_frac, 4),
            "comfort_degradation_steps": self.comfort_degradation_steps,
            "peak_violation_kw": round(self.peak_violation_kw, 2),
            "critical_load_failure_frac": round(self.critical_load_failure_frac, 4),
            "recovery_time_steps": self.recovery_time_steps,
            "robustness_score": round(self.robustness_score, 4),
            "normal_metrics": self.normal_metrics, "stressed_metrics": self.stressed_metrics,
        }


def _make_event(scenario_name: str, start: pd.Timestamp) -> EventSpec:
    spec = dict(STRESS_SCENARIO_LIBRARY[scenario_name])
    spec["start"] = start
    return EventSpec.model_validate(spec)


def _run(building: Building, world: World, policy_fn: PolicyFn, weights: ObjectiveWeights,
         carbon_kg_per_kwh: float, load_pf, solar_pf, risk_level: float, stress_events: list[EventSpec] | None):
    stress = build_stress_context(world, stress_events or [])
    base_fc = lambda t, H: load_pf.forecast_path(building.profile.base_load_kw, t, H)
    solar_fc = lambda t, H: solar_pf.forecast_path(building.profile.solar_potential_kw, t, H)
    if stress_events:
        base_fc = stress.wrap_forecast(world, base_fc)

    series = simulate_building_series(
        building, world, policy_fn, horizon_steps=32, risk_level=risk_level, weights=weights,
        carbon_kg_per_kwh=carbon_kg_per_kwh, forecast_base_load_fn=base_fc, forecast_solar_fn=solar_fc,
        outage_mask=stress.outage_mask if stress_events else None,
        solar_failure_mask=stress.solar_failure_mask if stress_events else None,
        demand_spike_addon_kw=stress.demand_spike_addon(world, building.id) if stress_events else None,
        building_failure_mask=stress.building_failure_mask(world, building.id) if stress_events else None,
    )
    bill = BillEngine.compute(world.index, series.import_kw, series.export_kw, world.dt_hours, world.tariff)
    metrics = compute_metrics(series, bill, world.dt_hours, carbon_kg_per_kwh)
    return series, bill, metrics


def run_robustness_suite(
    building: Building, world: World, policy_fn: PolicyFn, weights: ObjectiveWeights,
    carbon_kg_per_kwh: float, load_pf, solar_pf, risk_level: float = 0.05,
    scenarios: list[str] | None = None, event_start_step: int = 40,
) -> list[RobustnessResult]:
    scenarios = scenarios or list(STRESS_SCENARIO_LIBRARY.keys())
    normal_series, normal_bill, normal_metrics = _run(
        building, world, policy_fn, weights, carbon_kg_per_kwh, load_pf, solar_pf, risk_level, None,
    )
    hard_band = (building.resources.comfort_t_min, building.resources.comfort_t_max)

    results = []
    for name in scenarios:
        event = _make_event(name, world.index[event_start_step])
        stressed_series, stressed_bill, stressed_metrics = _run(
            building, world, policy_fn, weights, carbon_kg_per_kwh, load_pf, solar_pf, risk_level, [event],
        )

        cost_degradation = (
            (stressed_metrics["total_bill_inr"] - normal_metrics["total_bill_inr"]) / abs(normal_metrics["total_bill_inr"])
            if normal_metrics["total_bill_inr"] != 0 else 0.0
        )
        comfort_degradation = stressed_metrics["comfort_soft_violations_steps"] - normal_metrics["comfort_soft_violations_steps"]
        peak_violation = max(0.0, stressed_metrics["peak_demand_kw"] - normal_metrics["peak_demand_kw"])
        critical_failure = 1.0 - stressed_metrics["critical_load_service_frac"]

        end_step = event_start_step + int(event.duration_hours / world.dt_hours)
        recovery = None
        for t in range(end_step, world.n_steps):
            T = stressed_series.indoor_temp_c[t]
            if hard_band[0] <= T <= hard_band[1]:
                recovery = t - end_step
                break

        score = 1.0 - min(1.0, max(0.0, cost_degradation)) * 0.4 \
            - min(1.0, comfort_degradation / 50.0) * 0.3 \
            - critical_failure * 0.3
        score = float(np.clip(score, 0.0, 1.0))

        results.append(RobustnessResult(
            name, normal_metrics, stressed_metrics, cost_degradation, comfort_degradation,
            peak_violation, critical_failure, recovery, score,
        ))
    return results
