"""Experiment runner (PART AC). Every experiment run writes reproducibility
metadata (git commit, config hash, seed, model/controller versions,
Tier-fallback records per PART AV) alongside its results, so any number in
`summary.json` can be traced back to the exact code+config that produced it."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from aethergrid.core.world import World
from aethergrid.evaluation.baselines import BASELINE_POLICIES
from aethergrid.evaluation.metrics import compute_metrics
from aethergrid.evaluation.oracle import solve_oracle
from aethergrid.evaluation.robustness import _make_event
from aethergrid.forecasting.predict import build_training_building
from aethergrid.forecasting.path_forecast import PathForecaster
from aethergrid.schemas.experiment import ExperimentSpec
from aethergrid.stress.engine import build_stress_context
from aethergrid.tariff.bill import BillEngine
from aethergrid.core.timestep import simulate_building_series

_FORECASTER_CACHE: dict[tuple[str, int], tuple[PathForecaster, PathForecaster]] = {}


def _git_commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        return "UNKNOWN (not a git repo yet / git unavailable)"


def _config_hash(spec: ExperimentSpec) -> str:
    payload = json.dumps(spec.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def get_forecasters(building_type: str, seed: int) -> tuple[PathForecaster, PathForecaster]:
    key = (building_type, seed)
    if key not in _FORECASTER_CACHE:
        _, train_df = build_training_building(building_type, seed=seed + 500, n_days=45, dt_minutes=15)
        load_pf = PathForecaster.fit(train_df["base_load_kw"].values, 96, 32)
        solar_pf = PathForecaster.fit(train_df["solar_kw"].values, 96, 32)
        _FORECASTER_CACHE[key] = (load_pf, solar_pf)
    return _FORECASTER_CACHE[key]


def run_experiment(spec: ExperimentSpec, output_dir: str = "aethergrid/runs", event_start_step: int = 40) -> dict:
    world = World.load(spec.world_config)
    fallback_records = []
    stress_events = [_make_event(name, world.index[event_start_step]) for name in spec.stress_events]
    per_building_frames, per_building_metrics = [], {}
    bill_total = 0.0

    for bid, building in world.buildings.items():
        load_pf, solar_pf = get_forecasters(building.archetype.type, spec.seed)
        if load_pf.method != "seasonal_naive_gaussian":
            fallback_records.append(f"{bid}: path forecaster fallback active")

        stress = build_stress_context(world, stress_events)
        base_fc = lambda t, H, b=building, pf=load_pf: pf.forecast_path(b.profile.base_load_kw, t, H)
        solar_fc = lambda t, H, b=building, pf=solar_pf: pf.forecast_path(b.profile.solar_potential_kw, t, H)
        if stress_events:
            base_fc = stress.wrap_forecast(world, base_fc)

        if spec.controller == "oracle":
            series = solve_oracle(building, world, spec.weights, spec.carbon_kg_per_kwh,
                                   outage_mask=stress.outage_mask if stress_events else None)
        elif spec.controller in ("rl", "safe_rl"):
            from aethergrid.rl.evaluate import load_rl_policy
            policy_fn, rl_meta = load_rl_policy(building.archetype.type, coordination_aware=(spec.controller == "safe_rl"))
            if rl_meta.get("fallback"):
                fallback_records.append(f"{bid}: RL controller fell back to deterministic adaptive policy ({rl_meta.get('error') or rl_meta.get('load_error') or 'no trained model found'})")
            series = simulate_building_series(
                building, world, policy_fn, horizon_steps=spec.horizon_steps, risk_level=spec.risk_level,
                weights=spec.weights, carbon_kg_per_kwh=spec.carbon_kg_per_kwh,
                forecast_base_load_fn=base_fc, forecast_solar_fn=solar_fc,
                outage_mask=stress.outage_mask if stress_events else None,
                solar_failure_mask=stress.solar_failure_mask if stress_events else None,
                demand_spike_addon_kw=stress.demand_spike_addon(world, bid) if stress_events else None,
                building_failure_mask=stress.building_failure_mask(world, bid) if stress_events else None,
            )
        else:
            policy_fn = BASELINE_POLICIES.get(spec.controller)
            if policy_fn is None:
                raise NotImplementedError(f"controller '{spec.controller}' not available")
            series = simulate_building_series(
                building, world, policy_fn, horizon_steps=spec.horizon_steps, risk_level=spec.risk_level,
                weights=spec.weights, carbon_kg_per_kwh=spec.carbon_kg_per_kwh,
                forecast_base_load_fn=base_fc, forecast_solar_fn=solar_fc,
                outage_mask=stress.outage_mask if stress_events else None,
                solar_failure_mask=stress.solar_failure_mask if stress_events else None,
                demand_spike_addon_kw=stress.demand_spike_addon(world, bid) if stress_events else None,
                building_failure_mask=stress.building_failure_mask(world, bid) if stress_events else None,
            )

        bill = BillEngine.compute(world.index, series.import_kw, series.export_kw, world.dt_hours, world.tariff)
        metrics = compute_metrics(series, bill, world.dt_hours, spec.carbon_kg_per_kwh)
        per_building_metrics[bid] = metrics
        bill_total += bill.total

        frame = series.to_frame()
        frame["building_id"] = bid
        per_building_frames.append(frame)

    timeseries = pd.concat(per_building_frames)
    aggregate = {
        "total_bill_inr": round(bill_total, 2),
        "total_electricity_kwh": round(sum(m["total_electricity_kwh"] for m in per_building_metrics.values()), 2),
        "peak_demand_kw_sum": round(sum(m["peak_demand_kw"] for m in per_building_metrics.values()), 2),
        "carbon_kg": round(sum(m["carbon_kg"] for m in per_building_metrics.values()), 2),
        "comfort_soft_violations_steps": sum(m["comfort_soft_violations_steps"] for m in per_building_metrics.values()),
        "comfort_hard_violations_steps": sum(m["comfort_hard_violations_steps"] for m in per_building_metrics.values()),
        "critical_load_service_frac_min": round(min(m["critical_load_service_frac"] for m in per_building_metrics.values()), 4),
        "unserved_kwh": round(sum(m["unserved_kwh"] for m in per_building_metrics.values()), 2),
    }

    run_id = f"{spec.name}_{spec.controller}_{_config_hash(spec)}"
    out_path = Path(output_dir) / run_id
    out_path.mkdir(parents=True, exist_ok=True)

    run_meta = {
        "run_id": run_id, "experiment": spec.model_dump(mode="json"),
        "git_commit": _git_commit_hash(), "config_hash": _config_hash(spec),
        "forecaster_backend": next(iter(_FORECASTER_CACHE.values()))[0].method if _FORECASTER_CACHE else "unknown",
        "fallback_records": fallback_records,
    }
    (out_path / "run.json").write_text(json.dumps(run_meta, indent=2, default=str))
    (out_path / "metrics.json").write_text(json.dumps({"aggregate": aggregate, "per_building": per_building_metrics}, indent=2))
    timeseries.to_csv(out_path / "timeseries.csv")
    summary = {"run_id": run_id, "controller": spec.controller, "world": spec.world_config, **aggregate}
    (out_path / "summary.json").write_text(json.dumps(summary, indent=2))

    return {"run_id": run_id, "path": str(out_path), "aggregate": aggregate, "per_building": per_building_metrics}
