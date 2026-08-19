"""Pairwise edge feature computation for the Energy Opportunity Graph
(PART N / PART AZ). Every score is a plain statistic of the two buildings'
profiles/DNA -- traceable, not learned. `mechanism` records whether the
opportunity type requires physical energy transfer (only thermal_match, in
this system) or is purely a virtual/billing coordination (PART AZ: "Do not
assume physical transfer for Types 2-5")."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from aethergrid.core.building import Building
from aethergrid.energy_dna.signatures import EnergyDNA

OPPORTUNITY_MECHANISM = {
    "thermal_match": "physical_thermal_transfer",
    "flexibility_match": "virtual_schedule_coordination",
    "storage_coordination": "virtual_schedule_coordination",
    "solar_load_match": "virtual_billing_netting",
    "peak_complementarity": "virtual_billing_netting",
}

MAX_FEASIBLE_DISTANCE_M = 250.0  # beyond this, even virtual coordination is treated as impractical (comms/metering boundary)
MAX_THERMAL_PIPE_DISTANCE_M = 120.0  # physical thermal transfer needs short pipe runs to pencil out


@dataclass
class EdgeFeatures:
    source: str
    sink: str
    kind: str
    mechanism: str
    distance_m: float
    temporal_complementarity: float
    thermal_complementarity: float
    flexibility_compatibility: float
    capacity_compatibility: float
    geographic_feasibility: float
    infrastructure_cost_inr: float
    comfort_risk: float
    resilience_benefit: float

    def as_dict(self) -> dict:
        return {
            "source": self.source, "sink": self.sink, "kind": self.kind, "mechanism": self.mechanism,
            "distance_m": round(self.distance_m, 1),
            "temporal_complementarity": round(self.temporal_complementarity, 3),
            "thermal_complementarity": round(self.thermal_complementarity, 3),
            "flexibility_compatibility": round(self.flexibility_compatibility, 3),
            "capacity_compatibility": round(self.capacity_compatibility, 3),
            "geographic_feasibility": round(self.geographic_feasibility, 3),
            "infrastructure_cost_inr": round(self.infrastructure_cost_inr, 0),
            "comfort_risk": round(self.comfort_risk, 3),
            "resilience_benefit": round(self.resilience_benefit, 3),
        }


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    if np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def compute_edge_features(
    a: Building, b: Building, dna_a: EnergyDNA, dna_b: EnergyDNA,
    coord_a: tuple[float, float], coord_b: tuple[float, float], kind: str,
) -> EdgeFeatures:
    distance = math.hypot(coord_a[0] - coord_b[0], coord_a[1] - coord_b[1])
    load_corr = _corr(a.profile.base_load_kw, b.profile.base_load_kw)
    temporal_complementarity = float(np.clip((1 - load_corr) / 2, 0, 1))  # anti-correlated => near 1

    hour_gap = min(abs(dna_a.features["peak_timing_hour"] - dna_b.features["peak_timing_hour"]), 24 -
                    abs(dna_a.features["peak_timing_hour"] - dna_b.features["peak_timing_hour"]))
    inertia_gap = abs(dna_a.features["thermal_inertia_hours"] - dna_b.features["thermal_inertia_hours"])
    if kind == "thermal_match":
        # a good thermal match needs sustained heat REJECTION from one side (high base load /
        # low thermal inertia -> runs HVAC hard, continuously) overlapping in time with the
        # other side's DHW-type draw -- proxy via hour_gap small + one side high inertia (hospital: continuous)
        thermal_complementarity = float(np.clip(1 - hour_gap / 12, 0, 1)) * float(np.clip(inertia_gap / 400, 0, 1) + 0.3)
        thermal_complementarity = float(np.clip(thermal_complementarity, 0, 1))
    else:
        thermal_complementarity = float(np.clip(1 - hour_gap / 12, 0, 1)) * 0.5

    flex_a, flex_b = dna_a.features["flexible_load_capacity_kw"], dna_b.features["flexible_load_capacity_kw"]
    flexibility_compatibility = float(min(flex_a, flex_b) / max(flex_a, flex_b, 1e-6))

    if kind == "solar_load_match":
        cap_a, cap_b = dna_a.features["solar_capacity_factor"] * dna_a.features["peak_magnitude_kw"], flex_b
    elif kind == "storage_coordination":
        cap_a, cap_b = dna_a.features["battery_capacity_kwh"], dna_b.features["battery_capacity_kwh"]
    else:
        cap_a, cap_b = dna_a.features["peak_magnitude_kw"], dna_b.features["peak_magnitude_kw"]
    capacity_compatibility = float(min(cap_a, cap_b) / max(cap_a, cap_b, 1e-6))

    mechanism = OPPORTUNITY_MECHANISM[kind]
    max_dist = MAX_THERMAL_PIPE_DISTANCE_M if mechanism == "physical_thermal_transfer" else MAX_FEASIBLE_DISTANCE_M
    geographic_feasibility = float(np.clip(1 - distance / max_dist, 0, 1))

    if mechanism == "physical_thermal_transfer":
        infra_cost = 45000 + distance * 850  # piping/insulation, INR, synthetic unit cost
    elif mechanism == "virtual_schedule_coordination":
        infra_cost = 15000  # metering + control integration, distance-independent
    else:
        infra_cost = 6000  # billing/software integration only

    comfort_risk = float(np.clip(flexibility_compatibility * 0.4 + (1 - geographic_feasibility) * 0.1, 0, 1))
    resilience_benefit = float(np.clip((dna_a.features["criticality"] + dna_b.features["criticality"]) / 2 *
                                        capacity_compatibility, 0, 1))

    return EdgeFeatures(
        a.id, b.id, kind, mechanism, distance, temporal_complementarity, thermal_complementarity,
        flexibility_compatibility, capacity_compatibility, geographic_feasibility, infra_cost,
        comfort_risk, resilience_benefit,
    )
