"""TEST 10 (PART AR): the evaluation results table is generated from code,
not hand-edited."""
from __future__ import annotations

from aethergrid.evaluation.metrics import compute_metrics, savings_captured_fraction
from aethergrid.evaluation.reports import build_results_table, results_row_from_experiment


def test_results_table_is_built_from_experiment_dicts():
    fake_results = [
        {"controller": "no_control", "aggregate": {
            "total_bill_inr": 1000.0, "peak_demand_kw_sum": 50.0, "total_electricity_kwh": 200.0,
            "comfort_soft_violations_steps": 10, "carbon_kg": 142.0,
        }},
        {"controller": "oracle", "aggregate": {
            "total_bill_inr": 700.0, "peak_demand_kw_sum": 30.0, "total_electricity_kwh": 180.0,
            "comfort_soft_violations_steps": 2, "carbon_kg": 128.0,
        }},
    ]
    rows = [results_row_from_experiment(r, oracle_bill=700.0) for r in fake_results]
    table = build_results_table(rows)
    assert list(table["controller"]) == ["no_control", "oracle"]
    assert table.loc[table.controller == "oracle", "oracle_gap_pct"].iloc[0] == 0.0
    assert table.loc[table.controller == "no_control", "oracle_gap_pct"].iloc[0] > 0


def test_savings_captured_fraction_distinguishes_improvement_from_capture():
    # controller captures half the achievable gap between baseline and oracle
    frac = savings_captured_fraction(baseline_bill=1000.0, controller_bill=850.0, oracle_bill=700.0)
    assert frac == 0.5

    # oracle itself captures 100%
    frac_oracle = savings_captured_fraction(baseline_bill=1000.0, controller_bill=700.0, oracle_bill=700.0)
    assert frac_oracle == 1.0
