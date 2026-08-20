"""Household archetype schema (PART 4.1 of society_simulation_plan.md).

An archetype is DATA, not behavior -- the occupant-activity engine
(engine/occupancy.py) is archetype-agnostic and just reads whichever
archetype parameters apply to a given house id, mirroring the existing
`ARCHETYPES: dict[str, BuildingArchetype]` pattern in
aethergrid/schemas/building.py (which this module does NOT import from --
household archetypes are a distinct, unrelated entity, not a subtype of
the commercial BuildingArchetype)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

HouseholdArchetypeName = Literal[
    "dual_income_no_children",
    "family_with_children",
    "elderly_couple",
    "work_from_home",
    "joint_family",
    "frequently_absent",
]


class OccupancyPattern(BaseModel):
    """Parametrizes the per-archetype occupant-activity chain. The engine
    reads `home_prob_by_hour` as the base probability that at least one
    occupant is present at a given hour-of-day, then draws an actual
    occupant count and activity state from it each tick -- this is what
    keeps demand emergent (a consequence of a stochastic draw) rather
    than a fixed curve."""

    home_prob_by_hour: list[float] = Field(min_length=24, max_length=24)
    weekend_multiplier: float = 1.0
    mean_occupant_count: float
    occupant_count_std: float

    @field_validator("home_prob_by_hour")
    @classmethod
    def _in_unit_interval(cls, v: list[float]) -> list[float]:
        for p in v:
            if not (0.0 <= p <= 1.0):
                raise ValueError("home_prob_by_hour entries must be in [0,1]")
        return v


class HouseholdArchetype(BaseModel):
    name: HouseholdArchetypeName
    share: float = Field(gt=0, le=1)
    occupancy: OccupancyPattern

    comfort_t_min_c: float
    comfort_t_max_c: float
    comfort_tolerance_c: float          # how far the AC deadband can widen under a curtailment signal
    override_probability: float = Field(ge=0, le=1)   # chance a curtailment/quota signal is ignored this tick
    flexibility: float = Field(ge=0, le=1)             # how willing deferrables are to shift into a quota window

    ac_ownership_prob: float = Field(ge=0, le=1)
    ac_count_mean: float
    geyser_ownership_prob: float = Field(ge=0, le=1)
    washing_machine_ownership_prob: float = Field(ge=0, le=1)
    dishwasher_ownership_prob: float = Field(ge=0, le=1)
    ev_ownership_prob: float = Field(ge=0, le=1)       # baseline; scaled by scenario ev_penetration override
    solar_ownership_prob: float = Field(ge=0, le=1)
    battery_ownership_prob: float = Field(ge=0, le=1)

    thermal_R_k_per_kw: float           # RC envelope resistance -- household is smaller/leakier than a commercial zone
    thermal_C_kwh_per_k: float          # RC thermal mass
    floors_choices: list[int] = Field(default_factory=lambda: [1, 2])
