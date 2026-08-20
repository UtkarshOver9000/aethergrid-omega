"""Workspace/commercial building entity. Distinct from household
archetypes -- its load profile must visibly differ from residential
(daytime-weighted, computer/network loads, meeting-room bursts)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class WorkspaceArchetype(BaseModel):
    name: str
    floor_area_m2: float
    occupancy_capacity: int
    occupancy_start_hour: float
    occupancy_end_hour: float
    weekend_occupancy_factor: float

    lighting_kw_per_person: float
    computer_kw_per_person: float
    meeting_room_count: int
    meeting_room_kw_each: float

    hvac_capacity_kw: float
    comfort_t_min_c: float
    comfort_t_max_c: float
    thermal_R_k_per_kw: float
    thermal_C_kwh_per_k: float

    solar_kwp: float
    battery_kwh: float
    battery_kw: float
    ev_charger_count: int
    ev_charger_kw: float


WORKSPACE_ARCHETYPES: dict[str, WorkspaceArchetype] = {
    "coworking_office": WorkspaceArchetype(
        name="coworking_office", floor_area_m2=1200, occupancy_capacity=80,
        occupancy_start_hour=9.0, occupancy_end_hour=19.0, weekend_occupancy_factor=0.1,
        lighting_kw_per_person=0.03, computer_kw_per_person=0.12,
        meeting_room_count=4, meeting_room_kw_each=1.5,
        hvac_capacity_kw=35.0, comfort_t_min_c=21.0, comfort_t_max_c=25.0,
        thermal_R_k_per_kw=2.2, thermal_C_kwh_per_k=90,
        solar_kwp=25.0, battery_kwh=40.0, battery_kw=20.0,
        ev_charger_count=6, ev_charger_kw=7.4,
    ),
}
