"""World JSON schema (PART AA). A world file fully and reproducibly
specifies a scenario: meta, tariff reference, buildings, resource flags,
events and (for connection worlds) candidate connections."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from aethergrid.schemas.building import BuildingInstance
from aethergrid.schemas.event import EventSpec

WorldType = Literal["society", "colony", "connection"]


class WorldMeta(BaseModel):
    name: str
    type: WorldType
    duration_days: int = Field(gt=0)
    timestep_minutes: int = Field(default=15, gt=0)
    seed: int = 42
    weather_profile: str = "temperate_default"
    start_date: str = "2026-01-05"  # ISO date, a Monday for calendar consistency


class ResourcesSpec(BaseModel):
    solar: bool = True
    battery: bool = True
    thermal_storage: bool = True
    ev: bool = True
    dhw: bool = True
    grid_capacity_kw: float | None = None  # None => effectively unconstrained import


class ConnectionCandidateSpec(BaseModel):
    """An explicitly authored candidate edge; the graph/synergy engine also
    auto-discovers candidates, this lets a scenario force one in for demo
    purposes -- it still must pass the same feasibility/economics tests."""

    source: str
    sink: str
    kind: Literal[
        "thermal_match", "flexibility_match", "storage_coordination",
        "solar_load_match", "peak_complementarity",
    ] | None = None


class TariffRef(BaseModel):
    id: str


class WorldSpec(BaseModel):
    world: WorldMeta
    tariff: TariffRef
    buildings: list[BuildingInstance]
    resources: ResourcesSpec = Field(default_factory=ResourcesSpec)
    events: list[EventSpec] = Field(default_factory=list)
    connections: list[ConnectionCandidateSpec] = Field(default_factory=list)

    @classmethod
    def from_json_file(cls, path: str) -> "WorldSpec":
        import json
        with open(path, "r", encoding="utf-8") as f:
            return cls.model_validate(json.load(f))
