"""TEST 6 (PART AR): BillEngine matches a hand calculation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aethergrid.tariff.bill import BillEngine
from aethergrid.tariff.schema import TariffSpec, TOUWindow


def test_bill_matches_hand_calculation_flat_rate():
    tariff = TariffSpec(
        id="hand_calc", flat_energy_rate_per_kwh=5.0, fixed_charge_per_day=10.0,
        demand_charge_per_kva=100.0, export_compensation_per_kwh=2.0,
    )
    idx = pd.date_range("2026-01-01", periods=4, freq="15min")  # exactly 1 hour, dt=0.25h
    import_kw = np.array([10.0, 20.0, 10.0, 0.0])
    export_kw = np.array([0.0, 0.0, 0.0, 5.0])

    bill = BillEngine.compute(idx, import_kw, export_kw, dt_hours=0.25, tariff=tariff, assumed_power_factor=1.0)

    # hand calc:
    import_kwh = np.array([2.5, 5.0, 2.5, 0.0])
    expected_energy_charge = float(np.sum(import_kwh) * 5.0)  # 10*5 = 50
    expected_peak_kva = 20.0  # assumed pf=1.0
    expected_demand_charge = expected_peak_kva * 100.0  # 2000
    expected_export_credit = 5.0 * 0.25 * 2.0  # 1.25 kWh * 2 = 2.5
    billing_days = (idx[-1] - idx[0]).total_seconds() / 86400 + 0.25 / 24
    expected_fixed = billing_days * 10.0
    expected_total = expected_energy_charge + expected_demand_charge + expected_fixed - expected_export_credit

    assert bill.energy_charge == pytest_approx(expected_energy_charge)
    assert bill.demand_charge == pytest_approx(expected_demand_charge)
    assert bill.export_credit == pytest_approx(expected_export_credit)
    assert bill.total == pytest_approx(expected_total)


def pytest_approx(x, tol=1e-6):
    import pytest
    return pytest.approx(x, abs=tol)


def test_contract_demand_excess_penalty_applies_only_above_contract():
    tariff = TariffSpec(
        id="excess_test", flat_energy_rate_per_kwh=1.0, demand_charge_per_kva=100.0,
        contract_demand_kva=50.0, demand_excess_penalty_multiplier=2.0,
    )
    idx = pd.date_range("2026-01-01", periods=2, freq="15min")

    under = BillEngine.compute(idx, np.array([40.0, 40.0]), np.zeros(2), 0.25, tariff, assumed_power_factor=1.0)
    assert not under.contract_demand_exceeded
    assert under.demand_excess_penalty == 0.0

    over = BillEngine.compute(idx, np.array([60.0, 60.0]), np.zeros(2), 0.25, tariff, assumed_power_factor=1.0)
    assert over.contract_demand_exceeded
    assert over.demand_excess_penalty == pytest_approx(10.0 * 100.0 * 1.0)  # 10 kVA excess * rate * (mult-1)
