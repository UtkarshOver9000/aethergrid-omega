"""Minimal replay helpers: scrub a stored simulation timeseries at a given
step and format it for the dashboard's "AI Decision" panel."""
from __future__ import annotations

import pandas as pd


def slice_at(df: pd.DataFrame, t: int) -> dict:
    t = max(0, min(t, len(df) - 1))
    row = df.iloc[t]
    return {"timestamp": df.index[t], **row.to_dict()}


def decision_explanation(row: dict, resources, rate_now: float) -> list[str]:
    """Structured, state-grounded reasons (PART AF) -- built from the
    actual state at this timestep, never invented by an LLM."""
    reasons = []
    if row.get("hvac_kw", 0) > 0.1:
        reasons.append(f"HVAC drawing {row['hvac_kw']:.1f} kW -- indoor temp {row['indoor_temp_c']:.1f}C "
                        f"vs comfort ceiling {resources.comfort_t_max:.1f}C")
    if row.get("battery_charge_kw", 0) > 0.1:
        reasons.append(f"Battery charging {row['battery_charge_kw']:.1f} kW -- current rate Rs.{rate_now:.2f}/kWh, "
                        f"SOC {row.get('battery_soc_kwh', 0):.0f} kWh")
    if row.get("battery_discharge_kw", 0) > 0.1:
        reasons.append(f"Battery discharging {row['battery_discharge_kw']:.1f} kW to offset grid import at "
                        f"Rs.{rate_now:.2f}/kWh")
    if row.get("comfort_soft_violation"):
        reasons.append(f"Operating outside the soft comfort band ({row['indoor_temp_c']:.1f}C) -- "
                        f"accepted per the comfort_penalty weight to reduce cost/peak")
    if not reasons:
        reasons.append("Flexible loads idle -- no economic or comfort signal favored action this step")
    return reasons
