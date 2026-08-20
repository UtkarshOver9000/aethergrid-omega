"""World event schema -- INDEPENDENT of aethergrid/schemas/event.py on
purpose (see plan: reusing that schema would couple the world-simulation
event system to the MPC stress-test system, which three existing modules
pattern-match on directly). Same field-naming spirit, zero import."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

WorldEventType = Literal[
    "heatwave",
    "grid_outage",
    "transformer_overload",
    "cloud_cover",
    "high_ev_arrival",
    "festival",
    "holiday",
    "workspace_peak",
    "sensor_disturbance",
]


class WorldEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: WorldEventType
    start_min: int
    duration_min: int
    severity: float = 1.0
    target_ids: list[str] | None = None   # None = affects the whole world

    def active_at(self, t_min: int) -> bool:
        return self.start_min <= t_min < self.start_min + self.duration_min
