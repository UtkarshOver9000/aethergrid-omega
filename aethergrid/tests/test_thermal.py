from __future__ import annotations

from aethergrid.simulation.thermal import thermal_step


def test_temperature_drifts_toward_outdoor_with_no_hvac_or_gains():
    # RC time constant here is R*C = 200h; run for ~5 time constants (1000h,
    # i.e. 4000 steps of 0.25h) so the exponential has actually converged.
    T = 20.0
    for _ in range(4000):
        T = thermal_step(T, T_out=30.0, R=2.0, C=100.0, Q_internal_kw=0.0, Q_hvac_kw=0.0, dt_hours=0.25)
    assert 29.9 < T <= 30.0  # converges toward outdoor temperature

    # sanity check on the exponential shape after a much shorter run (< 1 time constant)
    T_partial = 20.0
    for _ in range(200):  # 50h, 0.25 time constants
        T_partial = thermal_step(T_partial, T_out=30.0, R=2.0, C=100.0, Q_internal_kw=0.0, Q_hvac_kw=0.0, dt_hours=0.25)
    assert 21.5 < T_partial < 23.0


def test_cooling_hvac_reduces_temperature_trajectory():
    T_no_hvac = 24.0
    T_with_hvac = 24.0
    for _ in range(20):
        T_no_hvac = thermal_step(T_no_hvac, T_out=35.0, R=2.0, C=100.0, Q_internal_kw=2.0, Q_hvac_kw=0.0, dt_hours=0.25)
        T_with_hvac = thermal_step(T_with_hvac, T_out=35.0, R=2.0, C=100.0, Q_internal_kw=2.0, Q_hvac_kw=10.0, dt_hours=0.25)
    assert T_with_hvac < T_no_hvac


def test_thermal_step_is_a_pure_deterministic_function():
    a = thermal_step(22.0, 30.0, 2.0, 100.0, 1.0, 5.0, 0.25)
    b = thermal_step(22.0, 30.0, 2.0, 100.0, 1.0, 5.0, 0.25)
    assert a == b
