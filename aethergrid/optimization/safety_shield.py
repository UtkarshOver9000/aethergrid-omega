"""SAFETY SHIELD (RULE 3 / PART K). Every proposed action -- whether from
the MPC, a rule-based controller, or the RL policy -- passes through here
before it is allowed to reach the digital twin. The shield only ever makes
an action MORE conservative (clips/reduces it); it never invents a more
aggressive action. Hard comfort/SOC limits are never softened here (soft
comfort slack is an MPC-objective concept, not a shield concept -- the
shield only cares about the HARD physical bounds)."""
from __future__ import annotations

from dataclasses import dataclass, field

from aethergrid.core.building import BuildingState
from aethergrid.core.resources import BuildingResources
from aethergrid.optimization.objective import HVAC_COP


@dataclass
class ShieldedAction:
    hvac_kw: float
    battery_charge_kw: float
    battery_discharge_kw: float
    dhw_heat_kw: float
    ev_charge_kw: float
    ts_charge_kw: float
    ts_discharge_kw: float
    interventions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "hvac_kw": self.hvac_kw, "battery_charge_kw": self.battery_charge_kw,
            "battery_discharge_kw": self.battery_discharge_kw, "dhw_heat_kw": self.dhw_heat_kw,
            "ev_charge_kw": self.ev_charge_kw, "ts_charge_kw": self.ts_charge_kw,
            "ts_discharge_kw": self.ts_discharge_kw,
        }


def project_action(
    action: dict, resources: BuildingResources, state: BuildingState,
    temp_out_c: float, internal_gain_kw: float, dt_hours: float,
    ev_present: bool, dhw_draw_kw: float = 0.0,
) -> ShieldedAction:
    r = resources
    interventions: list[str] = []

    def clip(name, value, lo, hi):
        v = max(lo, min(hi, value))
        if abs(v - value) > 1e-9:
            interventions.append(f"{name}: requested {value:.2f} clipped to [{lo:.2f},{hi:.2f}] -> {v:.2f}")
        return v

    hvac = clip("hvac_kw", action.get("hvac_kw", 0.0), 0.0, r.hvac_capacity_kw)

    # Predict next-step indoor temperature under the (bound-clipped) proposal;
    # if it would breach the HARD ceiling, override toward more cooling.
    predicted_T = state.indoor_temp_c + (dt_hours / max(r.thermal_C, 1e-6)) * (
        (temp_out_c - state.indoor_temp_c) / max(r.thermal_R, 1e-6) + internal_gain_kw - HVAC_COP * hvac
    )
    if predicted_T > r.hard_t_max:
        hvac = r.hvac_capacity_kw
        interventions.append(
            f"hvac_kw: predicted T={predicted_T:.2f}C > hard_t_max={r.hard_t_max:.2f}C -> forced to max capacity"
        )
        predicted_T_after = state.indoor_temp_c + (dt_hours / max(r.thermal_C, 1e-6)) * (
            (temp_out_c - state.indoor_temp_c) / max(r.thermal_R, 1e-6) + internal_gain_kw - HVAC_COP * hvac
        )
        if predicted_T_after > r.hard_t_max:
            interventions.append(
                f"hvac_kw: hard limit still at risk even at full HVAC capacity "
                f"(predicted {predicted_T_after:.2f}C) -- physically saturated, not a controller failure"
            )
    elif predicted_T < r.hard_t_min:
        # HVAC is cooling-only in this digital twin (objective.py:HVAC_COP convention) --
        # it cannot heat, so the only lever against an undershoot is to stop cooling entirely.
        hvac = 0.0
        interventions.append(
            f"hvac_kw: predicted T={predicted_T:.2f}C < hard_t_min={r.hard_t_min:.2f}C -> forced to zero "
            f"(HVAC is cooling-only and cannot correct an undershoot)"
        )
        predicted_T_after = state.indoor_temp_c + (dt_hours / max(r.thermal_C, 1e-6)) * (
            (temp_out_c - state.indoor_temp_c) / max(r.thermal_R, 1e-6) + internal_gain_kw
        )
        if predicted_T_after < r.hard_t_min:
            interventions.append(
                f"hvac_kw: hard limit still at risk even with HVAC off (predicted {predicted_T_after:.2f}C) "
                f"-- ambient/envelope driven, not a controller failure (no heating equipment modeled)"
            )

    soc_frac = (state.battery_soc_kwh / r.battery_capacity_kwh) if r.battery_capacity_kwh > 0 else 0.0
    eff = r.battery_round_trip_eff ** 0.5
    max_charge_by_soc = max(0.0, (r.battery_max_soc_frac * r.battery_capacity_kwh - state.battery_soc_kwh) / (eff * dt_hours)) if dt_hours > 0 else 0.0
    max_discharge_by_soc = max(0.0, (state.battery_soc_kwh - r.battery_min_soc_frac * r.battery_capacity_kwh) * eff / dt_hours) if dt_hours > 0 else 0.0
    batt_c = clip("battery_charge_kw", action.get("battery_charge_kw", 0.0), 0.0, min(r.battery_power_kw, max_charge_by_soc))
    batt_d = clip("battery_discharge_kw", action.get("battery_discharge_kw", 0.0), 0.0, min(r.battery_power_kw, max_discharge_by_soc))
    if batt_c > 0 and batt_d > 0:
        # never allow simultaneous charge+discharge through the shield even if the
        # upstream proposer suggested it (physically wasteful / meaningless)
        if batt_c >= batt_d:
            interventions.append(f"battery: simultaneous charge+discharge requested, discharge zeroed")
            batt_d = 0.0
        else:
            interventions.append(f"battery: simultaneous charge+discharge requested, charge zeroed")
            batt_c = 0.0

    dhw_headroom = max(0.0, (r.dhw_storage_kwh - state.dhw_soc_kwh) / dt_hours + dhw_draw_kw) if dt_hours > 0 else 0.0
    dhw = clip("dhw_heat_kw", action.get("dhw_heat_kw", 0.0), 0.0, min(r.dhw_capacity_kw, dhw_headroom) if r.has_dhw else 0.0)

    ev_cap_total = r.ev_capacity_kwh * r.ev_count
    ev_headroom = max(0.0, (ev_cap_total - state.ev_soc_kwh) / dt_hours) if dt_hours > 0 else 0.0
    ev_max = min(r.ev_max_charge_kw * r.ev_count, ev_headroom) if (r.has_ev and ev_present) else 0.0
    ev = clip("ev_charge_kw", action.get("ev_charge_kw", 0.0), 0.0, ev_max)

    ts_charge_headroom = max(0.0, (r.thermal_storage_capacity_kwh - state.thermal_storage_soc_kwh) / dt_hours) if dt_hours > 0 else 0.0
    ts_discharge_headroom = max(0.0, state.thermal_storage_soc_kwh / dt_hours) if dt_hours > 0 else 0.0
    ts_c = clip("ts_charge_kw", action.get("ts_charge_kw", 0.0), 0.0, min(r.thermal_storage_power_kw, ts_charge_headroom))
    ts_d = clip("ts_discharge_kw", action.get("ts_discharge_kw", 0.0), 0.0, min(r.thermal_storage_power_kw, ts_discharge_headroom))

    return ShieldedAction(hvac, batt_c, batt_d, dhw, ev, ts_c, ts_d, interventions)
