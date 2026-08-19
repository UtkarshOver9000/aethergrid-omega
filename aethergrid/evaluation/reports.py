"""The three mandatory scientific reports (PART AJ) + the results table
(PART AK), all generated from code -- never hand-edited."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def build_results_table(rows: list[dict]) -> pd.DataFrame:
    """rows: [{controller, bill, peak, energy, comfort, carbon, oracle_gap}, ...]"""
    df = pd.DataFrame(rows)
    cols = ["controller", "bill_inr", "peak_kw", "energy_kwh", "comfort_violations", "carbon_kg", "oracle_gap_pct"]
    return df[[c for c in cols if c in df.columns]]


def results_row_from_experiment(exp_result: dict, oracle_bill: float | None) -> dict:
    agg = exp_result["aggregate"]
    row = {
        "controller": exp_result.get("controller", "?"),
        "bill_inr": agg["total_bill_inr"],
        "peak_kw": agg["peak_demand_kw_sum"],
        "energy_kwh": agg["total_electricity_kwh"],
        "comfort_violations": agg["comfort_soft_violations_steps"],
        "carbon_kg": agg["carbon_kg"],
    }
    if oracle_bill:
        row["oracle_gap_pct"] = round(100 * (agg["total_bill_inr"] - oracle_bill) / abs(oracle_bill), 2)
    return row


def forecast_report(calibration_summaries: dict) -> dict:
    """calibration_summaries: {building_type: ForecastEngine.calibration_summary()}"""
    return {"report": "FORECAST_REPORT", "by_building_type": calibration_summaries}


def control_report(results_table_rows: list[dict], scenario_label: str = "NORMAL") -> dict:
    return {"report": "CONTROL_REPORT", "scenario": scenario_label, "rows": results_table_rows}


def robustness_report(robustness_by_scenario: dict) -> dict:
    """robustness_by_scenario: {scenario_name: RobustnessResult.as_dict()}"""
    return {"report": "ROBUSTNESS_REPORT", "scenarios": robustness_by_scenario}


def write_reports(output_dir: str, forecast: dict | None, control: dict | None, robustness: dict | None) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if forecast is not None:
        (out / "forecast_report.json").write_text(json.dumps(forecast, indent=2, default=str))
    if control is not None:
        (out / "control_report.json").write_text(json.dumps(control, indent=2, default=str))
    if robustness is not None:
        (out / "robustness_report.json").write_text(json.dumps(robustness, indent=2, default=str))
