"""Interpretable feature extraction for EnergyDNA (PART E). Every feature
here is a plain statistic of the building's exogenous profile / resources --
no black-box embedding is required to read any of these numbers."""
from __future__ import annotations

import numpy as np

from aethergrid.core.building import Building
from aethergrid.energy_dna.flexibility import compute_flexibility_map


def _autocorrelation(x: np.ndarray, lag: int) -> float:
    if lag >= len(x) or lag <= 0:
        return 0.0
    x = x - x.mean()
    denom = np.sum(x ** 2)
    if denom == 0:
        return 0.0
    return float(np.sum(x[:-lag] * x[lag:]) / denom)


def extract_dna_features(building: Building, steps_per_day: int) -> dict:
    load = building.profile.base_load_kw
    solar = building.profile.solar_potential_kw
    r = building.resources
    n = len(load)

    peak_idx = int(np.argmax(load))
    peak_hour = (peak_idx % steps_per_day) * (24.0 / steps_per_day)
    peak_kw = float(load[peak_idx])
    avg_kw = float(load.mean())
    load_factor = avg_kw / peak_kw if peak_kw > 0 else 0.0

    daily_periodicity = _autocorrelation(load, steps_per_day)
    weekly_periodicity = _autocorrelation(load, steps_per_day * 7) if n > steps_per_day * 7 else 0.0

    ramps = np.diff(load)
    max_ramp_kw = float(np.max(np.abs(ramps))) if len(ramps) else 0.0

    thermal_time_constant_h = r.thermal_R * r.thermal_C

    flex_samples = [compute_flexibility_map(building, t) for t in range(0, n, max(1, n // 20))]
    flexible_load_capacity_kw = float(np.mean([f.total_flexible_kw() for f in flex_samples]))
    rebound_tendency = float(np.mean([f.hvac.rebound_risk for f in flex_samples]))
    min_response_time_min = min(f.hvac.response_delay_min for f in flex_samples)
    max_response_duration_min = float(np.mean([f.hvac.max_duration_min for f in flex_samples]))

    solar_capacity_factor = float(solar.mean() / r.solar_kwp) if r.solar_kwp > 0 else 0.0
    comfort_band = max(r.comfort_t_max - r.comfort_t_min, 0.1)

    return {
        "peak_timing_hour": peak_hour,
        "peak_magnitude_kw": peak_kw,
        "avg_load_kw": avg_kw,
        "load_factor": load_factor,
        "daily_periodicity": daily_periodicity,
        "weekly_periodicity": weekly_periodicity,
        "max_ramp_kw": max_ramp_kw,
        "thermal_inertia_hours": thermal_time_constant_h,
        "flexible_load_capacity_kw": flexible_load_capacity_kw,
        "min_response_time_min": min_response_time_min,
        "max_response_duration_min": max_response_duration_min,
        "rebound_tendency": rebound_tendency,
        "weather_sensitivity_kw_per_c": r.weather_sensitivity_kw_per_c,
        "comfort_sensitivity": 1.0 / comfort_band,
        "solar_capacity_factor": solar_capacity_factor,
        "battery_capacity_kwh": r.battery_capacity_kwh,
        "occupancy_start_hour": building.archetype.occupancy_start_hour,
        "occupancy_end_hour": building.archetype.occupancy_end_hour,
        "criticality": building.criticality,
    }
