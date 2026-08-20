"""Pydantic mirror of the JSON frame contract (see plan doc) -- used by
export/validate.py to round-trip-check generated JSON before it's handed
to the renderer. This is the versioned source of truth's shape."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from aethergrid.worldsim.schemas.transformer import TransformerState

SCHEMA_VERSION = "1.0.0"


class StaticHouseMeta(BaseModel):
    id: int
    archetype: str
    has_ev: bool
    has_solar: bool
    has_battery: bool
    battery_kwh: float
    grid_x: int
    grid_z: int
    floors: int


class StaticWorkspaceMeta(BaseModel):
    id: str
    archetype: str
    has_ev: bool
    has_solar: bool
    battery_kwh: float
    grid_x: int
    grid_z: int


class EnvironmentFrame(BaseModel):
    temperature_c: float
    humidity_pct: float
    irradiance: float
    cloud_factor: float
    sun_altitude: float
    sun_azimuth: float


class GridFrame(BaseModel):
    available: bool
    transformer_kva: float
    rating_kva: float
    state: TransformerState


class CommonInfraFrame(BaseModel):
    water_tank_level_pct: float
    pump_on: bool
    lift_active: bool
    streetlights_on: bool
    stp_on: bool
    clubhouse_hvac_kw: float


class FairnessFrame(BaseModel):
    curtailed_house_ids: list[int]
    total_curtailed_kwh: float
    override_events: list[dict]


class SocietyFrame(BaseModel):
    common_kw: float
    solar_kw: float
    common_infra: CommonInfraFrame
    fairness: FairnessFrame


class WorkspaceFrame(BaseModel):
    kw: float
    occupancy_frac: float
    hvac_kw: float
    lighting_kw: float
    computer_kw: float
    meeting_room_active: bool
    solar_kw: float
    battery_soc: float
    ev_count_charging: int


EVState = Literal["absent", "idle", "charging", "full"]


class HouseFrameState(BaseModel):
    id: int
    kw: float
    ac_on: bool
    geyser_on: bool
    ev_state: EVState
    ev_soc: float
    solar_kw: float
    battery_soc: float
    indoor_temp_c: float
    comfort_dev_c: float
    occupancy: int
    curtailed: bool
    deferrables_active: list[str]


class Frame(BaseModel):
    t_min: int
    environment: EnvironmentFrame
    grid: GridFrame
    society: SocietyFrame
    workspace: WorkspaceFrame | None = None
    houses: list[HouseFrameState]
    events_active: list[str]


class WorldDescription(BaseModel):
    """One full exported scenario file for world_type == 'society'."""
    schema_version: str = SCHEMA_VERSION
    meta: dict
    houses: list[StaticHouseMeta]
    workspace: StaticWorkspaceMeta | None = None
    common_infra: dict
    events: list[dict]
    frames: list[Frame]
