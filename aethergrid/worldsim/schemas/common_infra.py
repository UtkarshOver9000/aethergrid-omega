"""Society common infrastructure: static configuration. Runtime state
(tank level, pump on/off, etc.) is plain engine state, not pydantic --
only the static description needs to round-trip through JSON validation."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CommonInfraSpec(BaseModel):
    water_tank_capacity_l: float = 20000.0
    pump_flow_l_per_min: float = 500.0
    has_lift: bool = True
    lift_count: int = 2
    has_stp: bool = True
    has_clubhouse: bool = True
    streetlight_count: int = 12
    streetlight_kw_each: float = 0.08

    # Priority hierarchy used by the transformer breach-shedding logic
    # (engine/transformer.py): critical loads are NEVER shed, non-critical
    # loads are shed first on BREACH/TRIPPED.
    critical_ids: list[str] = Field(default_factory=lambda: ["security_fire_systems", "lifts"])
    non_critical_ids: list[str] = Field(default_factory=lambda: [
        "corridor_streetlights", "clubhouse_common_hvac", "stp", "water_pump",
    ])
