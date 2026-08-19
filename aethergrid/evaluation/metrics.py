"""Metric computation (PART AD). Every value here is derived from a
SimulationSeries + BillBreakdown that already came out of the real
simulator/BillEngine -- this module only aggregates, it never invents."""
from __future__ import annotations

import numpy as np

from aethergrid.core.timestep import SimulationSeries
from aethergrid.tariff.bill import BillBreakdown


def compute_metrics(
    series: SimulationSeries, bill: BillBreakdown, dt_hours: float, carbon_kg_per_kwh: float,
    oracle_bill_total: float | None = None,
) -> dict:
    steps_per_day = max(1, round(24 / dt_hours))
    import_kw = series.import_kw
    total_kwh = float(np.sum(import_kw) * dt_hours)
    peak_kw = float(np.max(import_kw)) if len(import_kw) else 0.0
    avg_kw = float(np.mean(import_kw)) if len(import_kw) else 0.0
    load_factor = avg_kw / peak_kw if peak_kw > 0 else 0.0

    n_days = max(1, len(import_kw) // steps_per_day)
    daily_peaks = [
        float(np.max(import_kw[d * steps_per_day:(d + 1) * steps_per_day]))
        for d in range(n_days) if len(import_kw[d * steps_per_day:(d + 1) * steps_per_day]) > 0
    ]
    avg_daily_peak = float(np.mean(daily_peaks)) if daily_peaks else 0.0

    ramping = float(np.mean(np.abs(np.diff(import_kw)))) if len(import_kw) > 1 else 0.0

    total_served_kwh = total_kwh
    total_unserved_kwh = float(np.sum(series.unserved_kw) * dt_hours)
    critical_load_service = (
        total_served_kwh / (total_served_kwh + total_unserved_kwh)
        if (total_served_kwh + total_unserved_kwh) > 0 else 1.0
    )

    battery_throughput_kwh = float(np.sum(series.battery_charge_kw + series.battery_discharge_kw) * dt_hours)
    thermal_waste_kwh = 0.0  # populated by callers that track curtailed solar / thermal-storage losses directly

    metrics = {
        "total_electricity_kwh": round(total_kwh, 2),
        "peak_demand_kw": round(peak_kw, 2),
        "average_daily_peak_kw": round(avg_daily_peak, 2),
        "ramping_kw_per_step": round(ramping, 3),
        "load_factor": round(load_factor, 4),
        "energy_cost_inr": round(bill.energy_charge, 2),
        "demand_cost_inr": round(bill.demand_charge + bill.demand_excess_penalty, 2),
        "total_bill_inr": round(bill.total, 2),
        "carbon_kg": round(total_kwh * carbon_kg_per_kwh, 2),
        "comfort_soft_violations_steps": int(series.comfort_soft_violation.sum()),
        "comfort_hard_violations_steps": int(series.comfort_hard_violation.sum()),
        "critical_load_service_frac": round(critical_load_service, 4),
        "unserved_kwh": round(total_unserved_kwh, 2),
        "battery_throughput_kwh": round(battery_throughput_kwh, 2),
        "thermal_waste_kwh": round(thermal_waste_kwh, 2),
        "shield_interventions_count": int(sum(1 for s in series.shield_interventions if s)),
        "contract_demand_exceeded": bill.contract_demand_exceeded,
    }
    if oracle_bill_total is not None and oracle_bill_total not in (0, None):
        gap = (bill.total - oracle_bill_total) / abs(oracle_bill_total)
        metrics["oracle_gap_frac"] = round(gap, 4)
        metrics["oracle_bill_inr"] = round(oracle_bill_total, 2)
        metrics["savings_captured_frac"] = None  # filled in by caller once a no-control baseline is known
    return metrics


def savings_captured_fraction(baseline_bill: float, controller_bill: float, oracle_bill: float) -> float | None:
    """PART U: distinguishes "we improved" from "we captured most of the
    achievable improvement." Returns None if the baseline-to-oracle gap is
    ~zero (nothing achievable to capture)."""
    achievable = baseline_bill - oracle_bill
    if abs(achievable) < 1e-6:
        return None
    captured = baseline_bill - controller_bill
    return round(captured / achievable, 4)
