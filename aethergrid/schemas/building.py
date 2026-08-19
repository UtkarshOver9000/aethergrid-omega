"""Building configuration + archetype defaults.

Every building JSON entry only needs {id, type, criticality}. All physical
parameters (thermal R/C, HVAC capacity, solar, battery, EV, DHW, occupancy
shape) come from an archetype library keyed by `type`, unless explicitly
overridden in the JSON `overrides` block. Archetype values are SYNTHETIC /
ASSUMED (no real building metering data backs them) -- this is surfaced in
the dashboard per PART Q, never presented as measured.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BuildingType = Literal[
    "office", "school", "hospital", "residential", "retail",
    "laboratory", "hotel", "public",
]


class BuildingArchetype(BaseModel):
    """Synthetic physical/behavioral defaults for one building type."""

    type: BuildingType
    floor_area_m2: float
    base_load_kw_mean: float
    base_load_kw_std: float
    occupancy_start_hour: float
    occupancy_end_hour: float
    weekend_occupancy_factor: float
    thermal_R_k_per_kw: float          # thermal resistance, envelope
    thermal_C_kwh_per_k: float         # thermal mass
    hvac_capacity_kw: float
    comfort_t_min_c: float
    comfort_t_max_c: float
    hard_t_min_c: float
    hard_t_max_c: float
    has_dhw: bool
    dhw_capacity_kw: float
    dhw_storage_kwh: float
    solar_kwp: float
    battery_kwh: float
    battery_kw: float
    has_ev: bool
    ev_count: int
    ev_capacity_kwh: float
    default_criticality: float
    weather_sensitivity_kw_per_c: float  # extra HVAC electrical kW per degree C outdoor delta
    peak_hour: float                     # typical hour-of-day of base-load peak


ARCHETYPES: dict[str, BuildingArchetype] = {
    "office": BuildingArchetype(
        type="office", floor_area_m2=4000, base_load_kw_mean=85, base_load_kw_std=25,
        occupancy_start_hour=8, occupancy_end_hour=19, weekend_occupancy_factor=0.15,
        thermal_R_k_per_kw=2.4, thermal_C_kwh_per_k=180, hvac_capacity_kw=120,
        comfort_t_min_c=21, comfort_t_max_c=25, hard_t_min_c=18, hard_t_max_c=29,
        has_dhw=False, dhw_capacity_kw=0, dhw_storage_kwh=0,
        solar_kwp=60, battery_kwh=120, battery_kw=60,
        has_ev=True, ev_count=6, ev_capacity_kwh=60,
        default_criticality=0.35, weather_sensitivity_kw_per_c=3.2, peak_hour=14,
    ),
    "school": BuildingArchetype(
        type="school", floor_area_m2=6000, base_load_kw_mean=55, base_load_kw_std=20,
        occupancy_start_hour=7.5, occupancy_end_hour=16, weekend_occupancy_factor=0.05,
        thermal_R_k_per_kw=2.0, thermal_C_kwh_per_k=220, hvac_capacity_kw=90,
        comfort_t_min_c=20, comfort_t_max_c=26, hard_t_min_c=17, hard_t_max_c=30,
        has_dhw=True, dhw_capacity_kw=15, dhw_storage_kwh=40,
        solar_kwp=80, battery_kwh=60, battery_kw=30,
        has_ev=False, ev_count=0, ev_capacity_kwh=0,
        default_criticality=0.3, weather_sensitivity_kw_per_c=2.6, peak_hour=11,
    ),
    "hospital": BuildingArchetype(
        type="hospital", floor_area_m2=9000, base_load_kw_mean=340, base_load_kw_std=40,
        occupancy_start_hour=0, occupancy_end_hour=24, weekend_occupancy_factor=1.0,
        thermal_R_k_per_kw=1.6, thermal_C_kwh_per_k=320, hvac_capacity_kw=260,
        comfort_t_min_c=21, comfort_t_max_c=24, hard_t_min_c=19, hard_t_max_c=27,
        has_dhw=True, dhw_capacity_kw=60, dhw_storage_kwh=200,
        solar_kwp=100, battery_kwh=400, battery_kw=150,
        has_ev=True, ev_count=4, ev_capacity_kwh=60,
        default_criticality=0.98, weather_sensitivity_kw_per_c=5.5, peak_hour=15,
    ),
    "residential": BuildingArchetype(
        type="residential", floor_area_m2=3500, base_load_kw_mean=45, base_load_kw_std=18,
        occupancy_start_hour=17, occupancy_end_hour=23, weekend_occupancy_factor=1.6,
        thermal_R_k_per_kw=2.8, thermal_C_kwh_per_k=150, hvac_capacity_kw=55,
        comfort_t_min_c=20, comfort_t_max_c=27, hard_t_min_c=16, hard_t_max_c=31,
        has_dhw=True, dhw_capacity_kw=20, dhw_storage_kwh=60,
        solar_kwp=40, battery_kwh=80, battery_kw=30,
        has_ev=True, ev_count=10, ev_capacity_kwh=55,
        default_criticality=0.45, weather_sensitivity_kw_per_c=2.1, peak_hour=20,
    ),
    "retail": BuildingArchetype(
        type="retail", floor_area_m2=2500, base_load_kw_mean=65, base_load_kw_std=20,
        occupancy_start_hour=9, occupancy_end_hour=21, weekend_occupancy_factor=1.2,
        thermal_R_k_per_kw=1.9, thermal_C_kwh_per_k=90, hvac_capacity_kw=80,
        comfort_t_min_c=20, comfort_t_max_c=26, hard_t_min_c=17, hard_t_max_c=30,
        has_dhw=False, dhw_capacity_kw=0, dhw_storage_kwh=0,
        solar_kwp=35, battery_kwh=50, battery_kw=25,
        has_ev=False, ev_count=0, ev_capacity_kwh=0,
        default_criticality=0.25, weather_sensitivity_kw_per_c=2.8, peak_hour=18,
    ),
    "laboratory": BuildingArchetype(
        type="laboratory", floor_area_m2=3000, base_load_kw_mean=180, base_load_kw_std=25,
        occupancy_start_hour=7, occupancy_end_hour=20, weekend_occupancy_factor=0.3,
        thermal_R_k_per_kw=1.7, thermal_C_kwh_per_k=140, hvac_capacity_kw=150,
        comfort_t_min_c=20, comfort_t_max_c=24, hard_t_min_c=18, hard_t_max_c=27,
        has_dhw=False, dhw_capacity_kw=0, dhw_storage_kwh=0,
        solar_kwp=45, battery_kwh=100, battery_kw=50,
        has_ev=False, ev_count=0, ev_capacity_kwh=0,
        default_criticality=0.7, weather_sensitivity_kw_per_c=4.0, peak_hour=13,
    ),
    "hotel": BuildingArchetype(
        type="hotel", floor_area_m2=7000, base_load_kw_mean=150, base_load_kw_std=30,
        occupancy_start_hour=0, occupancy_end_hour=24, weekend_occupancy_factor=1.3,
        thermal_R_k_per_kw=2.1, thermal_C_kwh_per_k=260, hvac_capacity_kw=180,
        comfort_t_min_c=21, comfort_t_max_c=25, hard_t_min_c=18, hard_t_max_c=29,
        has_dhw=True, dhw_capacity_kw=80, dhw_storage_kwh=300,
        solar_kwp=70, battery_kwh=150, battery_kw=70,
        has_ev=True, ev_count=8, ev_capacity_kwh=60,
        default_criticality=0.5, weather_sensitivity_kw_per_c=4.4, peak_hour=19,
    ),
    "public": BuildingArchetype(
        type="public", floor_area_m2=5000, base_load_kw_mean=60, base_load_kw_std=15,
        occupancy_start_hour=9, occupancy_end_hour=17, weekend_occupancy_factor=0.1,
        thermal_R_k_per_kw=2.2, thermal_C_kwh_per_k=200, hvac_capacity_kw=75,
        comfort_t_min_c=20, comfort_t_max_c=26, hard_t_min_c=17, hard_t_max_c=30,
        has_dhw=True, dhw_capacity_kw=10, dhw_storage_kwh=30,
        solar_kwp=50, battery_kwh=70, battery_kw=35,
        has_ev=False, ev_count=0, ev_capacity_kwh=0,
        default_criticality=0.55, weather_sensitivity_kw_per_c=2.5, peak_hour=12,
    ),
}


class BuildingInstance(BaseModel):
    """One building entry as it appears in a world JSON file."""

    id: str
    type: BuildingType
    criticality: float | None = Field(default=None, ge=0, le=1)
    overrides: dict = Field(default_factory=dict)

    def resolved_criticality(self) -> float:
        if self.criticality is not None:
            return self.criticality
        return ARCHETYPES[self.type].default_criticality

    def resolved_archetype(self) -> BuildingArchetype:
        base = ARCHETYPES[self.type]
        if not self.overrides:
            return base
        return base.model_copy(update=self.overrides)
