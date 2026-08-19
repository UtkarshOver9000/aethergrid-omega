from __future__ import annotations

import json

import numpy as np

from aethergrid.tariff.compiler import compile_tariff, rate_array_for_index
from aethergrid.tariff.validator import TariffValidationError, validate_tariff_dict


def test_rate_at_picks_correct_tou_window():
    with open("aethergrid/configs/tariffs/demo.json") as f:
        tariff = compile_tariff(json.load(f))
    assert tariff.rate_at(2.0) == 4.2     # off_peak
    assert tariff.rate_at(19.0) == 11.2   # peak_evening
    assert tariff.rate_at(10.0) == 9.5    # peak_morning


def test_rejects_tariff_with_uncovered_gap_and_no_flat_fallback():
    bad = {
        "id": "bad", "energy_rates": [{"name": "partial", "start_hour": 0, "end_hour": 10, "rate_per_kwh": 5.0}],
    }
    try:
        validate_tariff_dict(bad)
        assert False, "expected TariffValidationError"
    except TariffValidationError:
        pass


def test_swapping_tariff_json_changes_economics_without_touching_controller():
    """PART AA / TEST 8: the same import series must bill differently under
    a different tariff, using the exact same BillEngine code path."""
    from aethergrid.tariff.bill import BillEngine
    import pandas as pd

    idx = pd.date_range("2026-01-05", periods=96, freq="15min")
    import_kw = np.full(96, 50.0)
    export_kw = np.zeros(96)

    with open("aethergrid/configs/tariffs/demo.json") as f:
        t1 = compile_tariff(json.load(f))
    with open("aethergrid/configs/tariffs/tariff_shift.json") as f:
        t2 = compile_tariff(json.load(f))

    bill1 = BillEngine.compute(idx, import_kw, export_kw, 0.25, t1)
    bill2 = BillEngine.compute(idx, import_kw, export_kw, 0.25, t2)
    assert bill1.total != bill2.total
    assert bill2.total > bill1.total  # tariff_shift.json is deliberately more expensive
