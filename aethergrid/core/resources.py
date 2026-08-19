"""Operational resource limits derived from a building archetype. Used
consistently by the simulator, the optimizer's constraint builder and the
EnergyDNA flexibility map so limits never diverge between subsystems."""
from __future__ import annotations

from dataclasses import dataclass

from aethergrid.schemas.building import BuildingArchetype


@dataclass(frozen=True)
class BuildingResources:
    building_id: str
    # thermal
    thermal_R: float
    thermal_C: float
    hvac_capacity_kw: float
    comfort_t_min: float
    comfort_t_max: float
    hard_t_min: float
    hard_t_max: float
    # battery
    battery_capacity_kwh: float
    battery_power_kw: float
    battery_round_trip_eff: float = 0.92
    battery_min_soc_frac: float = 0.10
    battery_max_soc_frac: float = 0.95
    # thermal storage
    thermal_storage_capacity_kwh: float = 0.0
    thermal_storage_power_kw: float = 0.0
    thermal_storage_loss_frac_per_step: float = 0.01
    # DHW
    has_dhw: bool = False
    dhw_capacity_kw: float = 0.0
    dhw_storage_kwh: float = 0.0
    # EV
    has_ev: bool = False
    ev_capacity_kwh: float = 0.0
    ev_max_charge_kw: float = 7.0
    ev_count: int = 0
    # solar
    solar_kwp: float = 0.0
    # weather sensitivity for base load (space heating/cooling embedded in base load, not HVAC-controlled)
    weather_sensitivity_kw_per_c: float = 0.0

    @property
    def has_thermal_storage(self) -> bool:
        return self.thermal_storage_capacity_kwh > 0

    @property
    def has_battery(self) -> bool:
        return self.battery_capacity_kwh > 0


def resources_from_archetype(building_id: str, arch: BuildingArchetype, resource_flags) -> BuildingResources:
    return BuildingResources(
        building_id=building_id,
        thermal_R=arch.thermal_R_k_per_kw,
        thermal_C=arch.thermal_C_kwh_per_k,
        hvac_capacity_kw=arch.hvac_capacity_kw,
        comfort_t_min=arch.comfort_t_min_c,
        comfort_t_max=arch.comfort_t_max_c,
        hard_t_min=arch.hard_t_min_c,
        hard_t_max=arch.hard_t_max_c,
        battery_capacity_kwh=arch.battery_kwh if resource_flags.battery else 0.0,
        battery_power_kw=arch.battery_kw if resource_flags.battery else 0.0,
        thermal_storage_capacity_kwh=(arch.dhw_storage_kwh * 0.5) if resource_flags.thermal_storage else 0.0,
        thermal_storage_power_kw=(arch.hvac_capacity_kw * 0.2) if resource_flags.thermal_storage else 0.0,
        has_dhw=arch.has_dhw and resource_flags.dhw,
        dhw_capacity_kw=arch.dhw_capacity_kw if resource_flags.dhw else 0.0,
        dhw_storage_kwh=arch.dhw_storage_kwh if resource_flags.dhw else 0.0,
        has_ev=arch.has_ev and resource_flags.ev,
        ev_capacity_kwh=arch.ev_capacity_kwh if resource_flags.ev else 0.0,
        ev_count=arch.ev_count if resource_flags.ev else 0,
        solar_kwp=arch.solar_kwp if resource_flags.solar else 0.0,
        weather_sensitivity_kw_per_c=arch.weather_sensitivity_kw_per_c,
    )
