"""Experiment JSON schema (PART AC). Every experiment run is fully
determined by {scenario path, controller name, seed, objective weights,
risk level} -- nothing else is allowed to vary the result."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ControllerName = Literal[
    "no_control", "rule_based", "mean_mpc", "quantile_mpc",
    "rl", "safe_rl", "hierarchical_hybrid", "oracle",
]


class ObjectiveWeights(BaseModel):
    """energy_cost, demand_charge_risk and connection_cost are already
    currency-denominated (Rs. per kWh / Rs. per kVA / Rs. per kWh), so a
    weight of 1.0 means "full real economic cost". comfort_penalty is NOT
    naturally currency-scaled (its raw unit is degrees-C of soft-band
    slack per 15-min step) -- its default of 80.0 was chosen so that
    correcting ~1 degree C of drift is worth roughly what a typical
    HVAC step actually costs (~Rs.60-150 for a mid-size building), which
    keeps the LP from treating comfort as effectively free. See
    docs/METHODOLOGY.md for the calibration rationale."""
    energy_cost: float = 1.0
    demand_charge_risk: float = 1.0
    carbon_cost: float = 0.15
    comfort_penalty: float = 80.0
    switching_penalty: float = 0.05
    degradation_cost: float = 0.1
    connection_cost: float = 0.5
    resilience_penalty: float = 1.0


class ExperimentSpec(BaseModel):
    name: str
    world_config: str
    controller: ControllerName
    seed: int = 42
    risk_level: float = Field(default=0.05, gt=0, lt=1)
    weights: ObjectiveWeights = Field(default_factory=ObjectiveWeights)
    horizon_steps: int = 32
    stress_events: list[str] = Field(default_factory=list)
    carbon_kg_per_kwh: float = 0.71  # grid emission factor, assumed (India-ish grid avg)
