"""Storage physics: battery, thermal storage, DHW tank, EV. All steps
enforce SOC bounds and power limits by CLAMPING the requested action --
this is the last line of physical defense even if the safety shield
upstream already projected the action (defense in depth, tested in
tests/test_storage.py)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StorageStepResult:
    soc_kwh: float
    actual_charge_kw: float
    actual_discharge_kw: float
    loss_kw: float = 0.0


def battery_step(
    soc_kwh: float, capacity_kwh: float, power_limit_kw: float,
    charge_kw: float, discharge_kw: float, dt_hours: float,
    round_trip_eff: float = 0.92, min_soc_frac: float = 0.10, max_soc_frac: float = 0.95,
) -> StorageStepResult:
    if capacity_kwh <= 0:
        return StorageStepResult(0.0, 0.0, 0.0, 0.0)

    charge_kw = max(0.0, min(charge_kw, power_limit_kw))
    discharge_kw = max(0.0, min(discharge_kw, power_limit_kw))

    min_soc = min_soc_frac * capacity_kwh
    max_soc = max_soc_frac * capacity_kwh
    eff_c = round_trip_eff ** 0.5
    eff_d = round_trip_eff ** 0.5

    headroom_kwh = max(0.0, max_soc - soc_kwh)
    max_charge_kw = headroom_kwh / (eff_c * dt_hours) if dt_hours > 0 else 0.0
    charge_kw = min(charge_kw, max_charge_kw)

    available_kwh = max(0.0, soc_kwh - min_soc)
    max_discharge_kw = (available_kwh * eff_d) / dt_hours if dt_hours > 0 else 0.0
    discharge_kw = min(discharge_kw, max_discharge_kw)

    soc_next = soc_kwh + charge_kw * eff_c * dt_hours - (discharge_kw / eff_d) * dt_hours
    soc_next = max(min_soc, min(max_soc, soc_next))
    loss_kw = charge_kw * (1 - eff_c) + discharge_kw * (1 / eff_d - 1)
    return StorageStepResult(soc_next, charge_kw, discharge_kw, loss_kw)


def thermal_storage_step(
    soc_kwh: float, capacity_kwh: float, power_limit_kw: float,
    charge_kw: float, discharge_kw: float, dt_hours: float,
    loss_frac_per_step: float = 0.01,
) -> StorageStepResult:
    if capacity_kwh <= 0:
        return StorageStepResult(0.0, 0.0, 0.0, 0.0)

    charge_kw = max(0.0, min(charge_kw, power_limit_kw))
    discharge_kw = max(0.0, min(discharge_kw, power_limit_kw))

    headroom_kwh = max(0.0, capacity_kwh - soc_kwh)
    max_charge_kw = headroom_kwh / dt_hours if dt_hours > 0 else 0.0
    charge_kw = min(charge_kw, max_charge_kw)

    max_discharge_kw = soc_kwh / dt_hours if dt_hours > 0 else 0.0
    discharge_kw = min(discharge_kw, max_discharge_kw)

    soc_next = soc_kwh + (charge_kw - discharge_kw) * dt_hours
    soc_next *= (1 - loss_frac_per_step)
    soc_next = max(0.0, min(capacity_kwh, soc_next))
    loss_kw = soc_kwh * loss_frac_per_step / dt_hours if dt_hours > 0 else 0.0
    return StorageStepResult(soc_next, charge_kw, discharge_kw, loss_kw)


def dhw_step(
    soc_kwh: float, capacity_kwh: float, power_limit_kw: float,
    heat_kw: float, draw_kw: float, dt_hours: float,
) -> StorageStepResult:
    """DHW tank: `heat_kw` charges the tank (electric element), `draw_kw` is
    an exogenous hot-water demand that discharges it."""
    if capacity_kwh <= 0:
        return StorageStepResult(0.0, 0.0, 0.0, 0.0)
    heat_kw = max(0.0, min(heat_kw, power_limit_kw))
    soc_next = soc_kwh + (heat_kw - draw_kw) * dt_hours
    soc_next = max(0.0, min(capacity_kwh, soc_next))
    actual_heat = (soc_next - soc_kwh) / dt_hours + draw_kw if dt_hours > 0 else heat_kw
    return StorageStepResult(soc_next, max(0.0, actual_heat), draw_kw, 0.0)


def ev_step(
    soc_kwh: float, capacity_kwh: float, power_limit_kw: float,
    charge_kw: float, dt_hours: float, present: bool,
) -> StorageStepResult:
    if not present or capacity_kwh <= 0:
        return StorageStepResult(soc_kwh, 0.0, 0.0, 0.0)
    charge_kw = max(0.0, min(charge_kw, power_limit_kw))
    headroom_kwh = max(0.0, capacity_kwh - soc_kwh)
    max_charge_kw = headroom_kwh / dt_hours if dt_hours > 0 else 0.0
    charge_kw = min(charge_kw, max_charge_kw)
    soc_next = soc_kwh + charge_kw * dt_hours
    return StorageStepResult(soc_next, charge_kw, 0.0, 0.0)
