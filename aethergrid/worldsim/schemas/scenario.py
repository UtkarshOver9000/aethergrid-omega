"""Top-level scenario configuration -- deliberately NOT WorldSpec
(aethergrid/schemas/world.py). WorldSpec is shaped for the optimizer
pipeline (world/tariff/buildings/resources/events/connections) and is
load-bearing for 26 existing tests via aethergrid/tests/conftest.py's
TINY_WORLD fixture; forcing this richer household/appliance/transformer
config into that shape would risk breaking it for no benefit."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from aethergrid.worldsim.schemas.common_infra import CommonInfraSpec
from aethergrid.worldsim.schemas.events import WorldEvent
from aethergrid.worldsim.schemas.transformer import TransformerSpec

WorldType = Literal["society", "colony", "connection"]


class SocietyScenario(BaseModel):
    """One society's configuration. A colony scenario embeds several of
    these; a standalone society scenario has exactly one, implicitly."""

    id: str = "soc_0"
    name: str = "Aethergrid Society"
    n_households: int = 60
    grid_cols: int = 10
    grid_rows: int = 6
    has_workspace: bool = True
    workspace_archetype: str = "coworking_office"
    common_infra: CommonInfraSpec = Field(default_factory=CommonInfraSpec)
    transformer: TransformerSpec = Field(default_factory=TransformerSpec)

    ev_penetration: float = Field(default=0.3, ge=0, le=1)     # scales archetype ev_ownership_prob
    override_rate: float = Field(default=0.15, ge=0, le=1)     # scales archetype override_probability
    solar_penetration: float = Field(default=0.4, ge=0, le=1)  # scales archetype solar_ownership_prob


class ConnectionEdgeSpec(BaseModel):
    id: str
    source: str
    sink: str
    capacity_kw: float
    loss_factor: float = Field(default=0.02, ge=0, le=1)


class WorldSimScenario(BaseModel):
    name: str
    world_type: WorldType = "society"
    scenario: str = "normal"          # normal | heatwave | high_ev | outage | cloudy | festival
    date: str = "2026-07-15"
    seed: int = 42
    interval_minutes: int = 15
    duration_hours: float = 24.0
    latitude_deg: float = 19.07       # Mumbai-ish default, used for sun-position calc
    longitude_deg: float = 72.87

    societies: list[SocietyScenario] = Field(default_factory=lambda: [SocietyScenario()])
    connection_edges: list[ConnectionEdgeSpec] = Field(default_factory=list)
    events: list[WorldEvent] = Field(default_factory=list)

    @property
    def n_steps(self) -> int:
        return int(self.duration_hours * 60 / self.interval_minutes)
