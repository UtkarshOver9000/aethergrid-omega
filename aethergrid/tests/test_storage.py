"""TEST 3 (PART AR): Battery SOC never leaves bounds, under adversarial
(deliberately excessive) requested actions."""
from __future__ import annotations

from aethergrid.simulation.storage import battery_step, dhw_step, ev_step, thermal_storage_step


def test_battery_soc_never_leaves_bounds_under_extreme_requests():
    soc = 50.0
    capacity, power_limit = 100.0, 1000.0  # absurdly high power limit relative to capacity
    min_frac, max_frac = 0.1, 0.95
    for _ in range(500):
        res = battery_step(soc, capacity, power_limit, charge_kw=1e6, discharge_kw=0.0, dt_hours=0.25,
                            min_soc_frac=min_frac, max_soc_frac=max_frac)
        soc = res.soc_kwh
        assert min_frac * capacity - 1e-6 <= soc <= max_frac * capacity + 1e-6

    for _ in range(500):
        res = battery_step(soc, capacity, power_limit, charge_kw=0.0, discharge_kw=1e6, dt_hours=0.25,
                            min_soc_frac=min_frac, max_soc_frac=max_frac)
        soc = res.soc_kwh
        assert min_frac * capacity - 1e-6 <= soc <= max_frac * capacity + 1e-6


def test_thermal_storage_soc_never_leaves_bounds():
    soc = 5.0
    capacity, power = 20.0, 500.0
    for _ in range(200):
        res = thermal_storage_step(soc, capacity, power, charge_kw=1e6, discharge_kw=0.0, dt_hours=0.25)
        soc = res.soc_kwh
        assert -1e-6 <= soc <= capacity + 1e-6


def test_dhw_and_ev_step_respect_capacity():
    res = dhw_step(soc_kwh=5.0, capacity_kwh=10.0, power_limit_kw=1000.0, heat_kw=1e6, draw_kw=0.0, dt_hours=0.25)
    assert res.soc_kwh <= 10.0 + 1e-6

    res_ev = ev_step(soc_kwh=5.0, capacity_kwh=10.0, power_limit_kw=1000.0, charge_kw=1e6, dt_hours=0.25, present=True)
    assert res_ev.soc_kwh <= 10.0 + 1e-6

    res_ev_absent = ev_step(soc_kwh=5.0, capacity_kwh=10.0, power_limit_kw=1000.0, charge_kw=1e6, dt_hours=0.25, present=False)
    assert res_ev_absent.soc_kwh == 5.0
    assert res_ev_absent.actual_charge_kw == 0.0
