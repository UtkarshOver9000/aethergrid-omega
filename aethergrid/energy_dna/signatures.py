"""Assembles the structured EnergyDNA object (PART E) for a building, and
builds normalized vectors across a fleet of buildings for graph/clustering
use. The interpretable dict (`EnergyDNA.features`) is always the primary
representation; the normalized vector is a derived, secondary view."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from aethergrid.core.building import Building
from aethergrid.core.world import World
from aethergrid.energy_dna.features import extract_dna_features

VECTOR_FEATURE_ORDER = [
    "peak_timing_hour", "peak_magnitude_kw", "avg_load_kw", "load_factor",
    "daily_periodicity", "weekly_periodicity", "max_ramp_kw", "thermal_inertia_hours",
    "flexible_load_capacity_kw", "min_response_time_min", "max_response_duration_min",
    "rebound_tendency", "weather_sensitivity_kw_per_c", "comfort_sensitivity",
    "solar_capacity_factor", "battery_capacity_kwh", "criticality",
]


@dataclass
class EnergyDNA:
    building_id: str
    building_type: str
    features: dict
    raw_vector: np.ndarray = field(repr=False)

    def to_dict(self) -> dict:
        return {"building_id": self.building_id, "building_type": self.building_type, **self.features}


def compute_energy_dna(building: Building, steps_per_day: int) -> EnergyDNA:
    feats = extract_dna_features(building, steps_per_day)
    vec = np.array([feats[k] for k in VECTOR_FEATURE_ORDER], dtype=float)
    return EnergyDNA(building.id, building.archetype.type, feats, vec)


def compute_world_dna(world: World) -> dict[str, EnergyDNA]:
    steps_per_day = int(24 * 60 / world.spec.world.timestep_minutes)
    return {bid: compute_energy_dna(b, steps_per_day) for bid, b in world.buildings.items()}


def normalized_dna_matrix(dna_map: dict[str, EnergyDNA]) -> tuple[np.ndarray, list[str]]:
    """Min-max normalize each feature across the fleet -> [0,1] matrix.
    With <2 buildings normalization is a no-op (returns raw values)."""
    ids = list(dna_map.keys())
    raw = np.stack([dna_map[i].raw_vector for i in ids])
    if raw.shape[0] < 2:
        return raw, ids
    lo, hi = raw.min(axis=0), raw.max(axis=0)
    span = np.where(hi - lo > 1e-9, hi - lo, 1.0)
    normed = (raw - lo) / span
    return normed, ids
