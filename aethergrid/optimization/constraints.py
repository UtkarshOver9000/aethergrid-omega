"""Shared hard/soft bound definitions so the MPC (optimization/mpc.py) and
the safety shield (optimization/safety_shield.py) can never silently drift
apart on what "safe" means for a given building."""
from __future__ import annotations

from dataclasses import dataclass

from aethergrid.core.resources import BuildingResources


@dataclass(frozen=True)
class HardBounds:
    t_min: float
    t_max: float
    battery_soc_min_kwh: float
    battery_soc_max_kwh: float
    hvac_max_kw: float
    battery_power_max_kw: float
    dhw_max_kw: float
    ev_max_kw: float
    ts_power_max_kw: float


def hard_bounds_for(r: BuildingResources) -> HardBounds:
    return HardBounds(
        t_min=r.hard_t_min, t_max=r.hard_t_max,
        battery_soc_min_kwh=r.battery_min_soc_frac * r.battery_capacity_kwh,
        battery_soc_max_kwh=r.battery_max_soc_frac * r.battery_capacity_kwh,
        hvac_max_kw=r.hvac_capacity_kw, battery_power_max_kw=r.battery_power_kw,
        dhw_max_kw=r.dhw_capacity_kw, ev_max_kw=r.ev_max_charge_kw * max(r.ev_count, 1),
        ts_power_max_kw=r.thermal_storage_power_kw,
    )


SOFT_COMFORT_BAND_NOTE = (
    "Soft comfort band (comfort_t_min/comfort_t_max) may be violated at a cost "
    "(objective.py comfort_penalty). Hard bounds (hard_t_min/hard_t_max) are "
    "never relaxed -- enforced as LP variable bounds in mpc.py and re-checked "
    "by safety_shield.py for any non-MPC proposer (e.g. RL)."
)
