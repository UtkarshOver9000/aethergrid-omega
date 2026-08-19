"""Node features for the Energy Opportunity Graph: EnergyDNA plus a
synthetic site layout (no real GIS data exists in this environment, so
coordinates are deterministically derived from the building id -- this
is what lets `geographic_feasibility` be a real, reproducible number
instead of an invented one)."""
from __future__ import annotations

import hashlib

import numpy as np

from aethergrid.energy_dna.signatures import EnergyDNA


def synthetic_coordinates(building_id: str, site_span_m: float = 400.0) -> tuple[float, float]:
    h = hashlib.sha256(building_id.encode()).hexdigest()
    rng = np.random.default_rng(int(h[:8], 16))
    return float(rng.uniform(0, site_span_m)), float(rng.uniform(0, site_span_m))


def node_feature_dict(dna: EnergyDNA, coords: tuple[float, float]) -> dict:
    return {
        "building_id": dna.building_id, "building_type": dna.building_type,
        "x_m": coords[0], "y_m": coords[1],
        "peak_kw": dna.features["peak_magnitude_kw"], "peak_hour": dna.features["peak_timing_hour"],
        "flexible_kw": dna.features["flexible_load_capacity_kw"],
        "criticality": dna.features["criticality"],
        "battery_kwh": dna.features["battery_capacity_kwh"],
        "solar_capacity_factor": dna.features["solar_capacity_factor"],
        "thermal_inertia_hours": dna.features["thermal_inertia_hours"],
    }
