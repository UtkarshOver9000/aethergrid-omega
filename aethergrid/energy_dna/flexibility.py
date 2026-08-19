"""Flexibility Map (PART F): "what can I actually change right now?" for
each controllable asset. Computed from BuildingResources (static limits)
plus the building's current dynamic state -- this is the actionability
layer the optimizer and RL policy consume; it is NOT a forecast."""
from __future__ import annotations

from dataclasses import dataclass

from aethergrid.core.building import Building


@dataclass
class HVACFlex:
    available_flex_kw: float
    response_delay_min: float
    max_duration_min: float
    rebound_risk: float


@dataclass
class DHWFlex:
    available_flex_kw: float
    response_delay_min: float
    storage_headroom_kwh: float


@dataclass
class BatteryFlex:
    charge_limit_kw: float
    discharge_limit_kw: float
    soc_frac: float


@dataclass
class EVFlex:
    present: bool
    required_energy_kwh: float
    max_charge_kw: float
    soc_frac: float


@dataclass
class ThermalStorageFlex:
    capacity_kwh: float
    charge_limit_kw: float
    discharge_limit_kw: float
    soc_frac: float
    loss_frac_per_step: float


@dataclass
class FlexibilityMap:
    building_id: str
    hvac: HVACFlex
    dhw: DHWFlex
    battery: BatteryFlex
    ev: EVFlex
    thermal_storage: ThermalStorageFlex

    def total_flexible_kw(self) -> float:
        return (
            self.hvac.available_flex_kw + self.dhw.available_flex_kw
            + self.battery.charge_limit_kw + self.battery.discharge_limit_kw
            + self.thermal_storage.charge_limit_kw + self.thermal_storage.discharge_limit_kw
        )


def compute_flexibility_map(building: Building, t: int) -> FlexibilityMap:
    r = building.resources
    s = building.state

    band = max(r.comfort_t_max - r.comfort_t_min, 0.1)
    headroom_up = max(0.0, r.comfort_t_max - s.indoor_temp_c) / band
    headroom_down = max(0.0, s.indoor_temp_c - r.comfort_t_min) / band
    hvac_flex_frac = min(1.0, headroom_up + headroom_down)
    time_constant_h = (r.thermal_R * r.thermal_C) if r.thermal_C > 0 else 0.0
    hvac = HVACFlex(
        available_flex_kw=r.hvac_capacity_kw * hvac_flex_frac,
        response_delay_min=5.0,
        max_duration_min=max(5.0, time_constant_h * 60 * 0.15),
        rebound_risk=max(0.0, 1.0 - min(1.0, time_constant_h / 20.0)),
    )

    dhw = DHWFlex(
        available_flex_kw=r.dhw_capacity_kw if r.has_dhw else 0.0,
        response_delay_min=0.0,
        storage_headroom_kwh=max(0.0, r.dhw_storage_kwh - s.dhw_soc_kwh),
    )

    soc_frac = (s.battery_soc_kwh / r.battery_capacity_kwh) if r.battery_capacity_kwh > 0 else 0.0
    battery = BatteryFlex(
        charge_limit_kw=r.battery_power_kw if soc_frac < r.battery_max_soc_frac else 0.0,
        discharge_limit_kw=r.battery_power_kw if soc_frac > r.battery_min_soc_frac else 0.0,
        soc_frac=soc_frac,
    )

    ev_present = bool(building.profile.ev_present[t]) if r.has_ev else False
    ev_capacity_total = r.ev_capacity_kwh * r.ev_count
    ev_soc_frac = (s.ev_soc_kwh / ev_capacity_total) if ev_capacity_total > 0 else 0.0
    ev = EVFlex(
        present=ev_present,
        required_energy_kwh=max(0.0, ev_capacity_total * 0.85 - s.ev_soc_kwh) if ev_present else 0.0,
        max_charge_kw=r.ev_max_charge_kw * r.ev_count if ev_present else 0.0,
        soc_frac=ev_soc_frac,
    )

    ts_soc_frac = (s.thermal_storage_soc_kwh / r.thermal_storage_capacity_kwh) if r.thermal_storage_capacity_kwh > 0 else 0.0
    thermal_storage = ThermalStorageFlex(
        capacity_kwh=r.thermal_storage_capacity_kwh,
        charge_limit_kw=r.thermal_storage_power_kw if ts_soc_frac < 0.95 else 0.0,
        discharge_limit_kw=r.thermal_storage_power_kw if ts_soc_frac > 0.05 else 0.0,
        soc_frac=ts_soc_frac,
        loss_frac_per_step=r.thermal_storage_loss_frac_per_step,
    )

    return FlexibilityMap(building.id, hvac, dhw, battery, ev, thermal_storage)
