"""Action space definition + decoding (PART L). The policy outputs a
Box(-1, 1) vector; this module maps it to physical setpoints. The RAW
decoded action is NOT trusted -- it still goes through
optimization/safety_shield.py like every other controller (RULE 3)."""
from __future__ import annotations

import numpy as np

from aethergrid.core.resources import BuildingResources

ACTION_DIM = 7
ACTION_KEYS = [
    "hvac_kw", "battery_charge_kw", "battery_discharge_kw",
    "dhw_heat_kw", "ev_charge_kw", "ts_charge_kw", "ts_discharge_kw",
]


def decode_action(raw: np.ndarray, resources: BuildingResources, ev_max_kw: float) -> dict:
    a = np.clip(raw, -1.0, 1.0)
    frac = (a + 1.0) / 2.0  # [-1,1] -> [0,1]
    limits = np.array([
        resources.hvac_capacity_kw, resources.battery_power_kw, resources.battery_power_kw,
        resources.dhw_capacity_kw, ev_max_kw, resources.thermal_storage_power_kw, resources.thermal_storage_power_kw,
    ])
    values = frac * limits
    return dict(zip(ACTION_KEYS, values.tolist()))
