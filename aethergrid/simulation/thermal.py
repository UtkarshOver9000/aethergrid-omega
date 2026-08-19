"""Single-zone RC thermal model (PART P/Q). Explicit Euler integration of

    T[t+1] = T[t] + dt/C * ((T_out - T)/R + Q_internal - Q_hvac + Q_transfer)

All Q terms are in kW (thermal), C is in kWh/K, R is in K/kW, dt in hours.
Positive Q_hvac cools (removes heat) by convention when `cooling=True`,
positive Q_hvac heats when `cooling=False` -- see `hvac_thermal_effect`.
"""
from __future__ import annotations

import numpy as np


def thermal_step(
    T: float,
    T_out: float,
    R: float,
    C: float,
    Q_internal_kw: float,
    Q_hvac_kw: float,
    dt_hours: float,
    Q_transfer_kw: float = 0.0,
) -> float:
    """Advance zone temperature by one timestep. Q_hvac_kw > 0 means net
    heat REMOVAL (cooling); pass negative for heating."""
    dT = (dt_hours / C) * ((T_out - T) / R + Q_internal_kw - Q_hvac_kw + Q_transfer_kw)
    return T + dT


def hvac_electrical_to_thermal_kw(electrical_kw: float, cop: float = 3.0) -> float:
    """Convert HVAC electrical draw to thermal effect via a coefficient of
    performance (assumed COP=3.0 for a typical heat-pump/chiller system,
    SYNTHETIC/ASSUMED)."""
    return electrical_kw * cop


def internal_gains_kw(occupancy_frac: float, floor_area_m2: float, solar_ghi_wm2: float,
                       gain_per_m2_occupied_w: float = 8.0, solar_gain_frac: float = 0.02) -> float:
    """Internal + solar heat gains for a zone (assumed coefficients)."""
    occ_gain_kw = occupancy_frac * floor_area_m2 * gain_per_m2_occupied_w / 1000.0
    solar_gain_kw = solar_ghi_wm2 * floor_area_m2 * solar_gain_frac / 1000.0
    return occ_gain_kw + solar_gain_kw


def simulate_thermal_series(
    T0: float, T_out: np.ndarray, R: float, C: float,
    Q_internal_kw: np.ndarray, Q_hvac_kw: np.ndarray, dt_hours: float,
) -> np.ndarray:
    """Vectorized-interface (but sequential, RC is stateful) simulation over
    a full series. Returns temperature array of len(T_out)+1 including T0."""
    n = len(T_out)
    T = np.empty(n + 1)
    T[0] = T0
    for t in range(n):
        T[t + 1] = thermal_step(T[t], T_out[t], R, C, Q_internal_kw[t], Q_hvac_kw[t], dt_hours)
    return T
