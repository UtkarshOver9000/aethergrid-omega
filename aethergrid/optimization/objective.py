"""Objective term weights (PART I). J = sum of these terms; every weight is
visible/configurable (schemas/experiment.py:ObjectiveWeights) -- nothing is
hidden inside the solver."""
from __future__ import annotations

from dataclasses import dataclass

from aethergrid.schemas.experiment import ObjectiveWeights

DEFAULT_WEIGHTS = ObjectiveWeights()

# HVAC electrical->thermal coefficient of performance (cooling-only HVAC
# convention used throughout the digital twin -- SYNTHETIC/ASSUMED, no
# heating mode is modeled). See ARCHITECTURE.md / LIMITATIONS.md.
HVAC_COP = 3.0


@dataclass(frozen=True)
class SolveConfig:
    weights: ObjectiveWeights
    carbon_kg_per_kwh: float
    demand_charge_per_kva: float = 0.0
    assumed_power_factor: float = 0.95
    reserve_target_frac: float = 0.3
