"""Electrical balance (PART P):

    grid_import = base_load + HVAC + DHW + EV + battery_charge - battery_discharge - solar

Anything left negative (excess generation) becomes grid_export instead of a
negative import, matching how utility meters actually report."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ElectricalBalance:
    grid_import_kw: float
    grid_export_kw: float
    total_load_kw: float
    solar_used_kw: float
    solar_curtailed_kw: float


def electrical_balance(
    base_load_kw: float, hvac_kw: float, dhw_kw: float, ev_kw: float,
    battery_charge_kw: float, battery_discharge_kw: float, solar_kw: float,
) -> ElectricalBalance:
    total_load_kw = base_load_kw + hvac_kw + dhw_kw + ev_kw + battery_charge_kw
    net = total_load_kw - battery_discharge_kw - solar_kw
    if net >= 0:
        grid_import_kw, grid_export_kw = net, 0.0
        solar_used_kw = solar_kw
        solar_curtailed_kw = 0.0
    else:
        grid_import_kw, grid_export_kw = 0.0, -net
        solar_used_kw = solar_kw - (-net)
        solar_curtailed_kw = 0.0
    return ElectricalBalance(grid_import_kw, grid_export_kw, total_load_kw, solar_used_kw, solar_curtailed_kw)
