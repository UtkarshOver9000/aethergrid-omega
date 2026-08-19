"""Reward function (PART L). Grounded in the same cost terms the MPC
objective uses (optimization/objective.py) -- energy cost at the real
tariff rate, a peak-risk term, comfort penalty, and a small
degradation/switching penalty -- so the RL policy is being pushed toward
the same economic target as the classical controller, making the
comparison in evaluation/baselines.py meaningful rather than apples-to-
oranges."""
from __future__ import annotations

from aethergrid.core.timestep import PhysicsStepResult, StepContext


def compute_reward(ctx: StepContext, step_res: PhysicsStepResult, peak_reference_kw: float) -> float:
    dt = ctx.dt_hours
    rate = ctx.horizon_rates[0] if len(ctx.horizon_rates) else 0.0
    energy_cost = step_res.grid.import_kw * rate * dt

    peak_risk = max(0.0, step_res.grid.import_kw - 0.85 * peak_reference_kw) * (ctx.demand_charge_per_kva / 15.0) * 0.02

    r = ctx.resources
    T = step_res.next_state.indoor_temp_c
    if T < r.comfort_t_min:
        comfort_penalty = (r.comfort_t_min - T) ** 2
    elif T > r.comfort_t_max:
        comfort_penalty = (T - r.comfort_t_max) ** 2
    else:
        comfort_penalty = 0.0

    hard_violation_penalty = 0.0
    if T < r.hard_t_min or T > r.hard_t_max:
        hard_violation_penalty = 50.0

    degradation = (step_res.safe.battery_charge_kw + step_res.safe.battery_discharge_kw) * dt * 0.01
    unserved_penalty = step_res.grid.unserved_kw * 2.0

    cost = (
        ctx.weights.energy_cost * energy_cost
        + ctx.weights.demand_charge_risk * peak_risk
        + ctx.weights.comfort_penalty * comfort_penalty
        + ctx.weights.degradation_cost * degradation
        + hard_violation_penalty + unserved_penalty
    )
    return -float(cost)
