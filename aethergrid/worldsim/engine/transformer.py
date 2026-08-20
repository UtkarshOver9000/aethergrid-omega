"""Transformer state machine + breach-shedding logic. On BREACH/TRIPPED
this ACTUALLY zeros non-critical common loads and selects a rotating
subset of households to curtail -- so "critical services remain
protected" and "the same six flats aren't always curtailed" are facts
recorded in the exported JSON, not a cosmetic reinterpretation left to
the renderer."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aethergrid.worldsim.schemas.appliance import COMMON_APPLIANCES
from aethergrid.worldsim.schemas.common_infra import CommonInfraSpec
from aethergrid.worldsim.schemas.transformer import TransformerSpec


@dataclass
class TransformerDecision:
    kva: np.ndarray
    state: list                       # list[str] per tick
    common_infra_shed: np.ndarray     # bool[n] -- non-critical common infra zeroed this tick
    house_curtail_mask: np.ndarray    # bool[n, n_houses] -- which houses were shed this tick
    curtailed_house_ids_by_tick: list  # list[list[int]]
    total_curtailed_kwh_by_tick: np.ndarray


def _non_critical_common_kw(common_infra: CommonInfraSpec, pump_on, lift_active, streetlights_on, stp_on, clubhouse_hvac_kw):
    """Recompute just the non-critical portion of common-infra draw so it
    can be zeroed independently of the critical portion (security/lifts)."""
    non_critical_kw = np.zeros(len(pump_on))
    if "water_pump" in common_infra.non_critical_ids:
        non_critical_kw += np.where(pump_on, COMMON_APPLIANCES["water_pump"].rated_kw, 0.0)
    if "corridor_streetlights" in common_infra.non_critical_ids:
        non_critical_kw += np.where(streetlights_on, common_infra.streetlight_count * common_infra.streetlight_kw_each, 0.0)
    if "stp" in common_infra.non_critical_ids:
        non_critical_kw += np.where(stp_on, COMMON_APPLIANCES["stp"].rated_kw, 0.0)
    if "clubhouse_common_hvac" in common_infra.non_critical_ids:
        non_critical_kw += clubhouse_hvac_kw
    return non_critical_kw


def decide_transformer_state_and_curtailment(
    spec: TransformerSpec, common_infra: CommonInfraSpec,
    household_kw_baseline: np.ndarray,       # [n_steps, n_houses], pass-1 (uncurtailed) household demand
    household_flexible_kw_baseline: np.ndarray,  # [n_steps, n_houses] the AC+geyser+EV portion, i.e. what curtailment can actually remove
    common_infra_kw: np.ndarray, pump_on, lift_active, streetlights_on, stp_on, clubhouse_hvac_kw,
    workspace_kw: np.ndarray,
) -> TransformerDecision:
    n_steps, n_houses = household_kw_baseline.shape
    non_critical_common = _non_critical_common_kw(common_infra, pump_on, lift_active, streetlights_on, stp_on, clubhouse_hvac_kw)

    total_uncurtailed = household_kw_baseline.sum(axis=1) + common_infra_kw + workspace_kw
    kva_uncurtailed = total_uncurtailed / spec.assumed_power_factor

    kva = np.zeros(n_steps)
    state = []
    common_shed = np.zeros(n_steps, dtype=bool)
    house_mask = np.zeros((n_steps, n_houses), dtype=bool)
    curtailed_ids_by_tick = []
    curtailed_kwh_by_tick = np.zeros(n_steps)

    for t in range(n_steps):
        provisional_state = spec.state_for(kva_uncurtailed[t])
        shed_common = provisional_state in ("BREACH", "TRIPPED")
        total = total_uncurtailed[t]
        if shed_common:
            total -= non_critical_common[t]

        houses_to_shed: list[int] = []
        if provisional_state in ("BREACH", "TRIPPED"):
            # deterministic round-robin so curtailment rotates across households over the day
            # instead of always hitting the same ones ("do not curtail the same six flats")
            flex = household_flexible_kw_baseline[t]
            order = np.argsort(-flex)  # curtail the biggest flexible draws first -- fewer households affected
            target_kva = spec.rating_kva * spec.critical_frac * 0.97  # settle just under the rating
            shed_needed_kw = max(0.0, total / spec.assumed_power_factor - target_kva) * spec.assumed_power_factor
            shed_so_far = 0.0
            rotation_offset = t % max(1, n_houses)
            rotated_order = np.roll(order, -rotation_offset)
            for hid in rotated_order:
                if shed_so_far >= shed_needed_kw or flex[hid] <= 1e-6:
                    continue
                houses_to_shed.append(int(hid))
                shed_so_far += flex[hid]
                house_mask[t, hid] = True
                if shed_so_far >= shed_needed_kw:
                    break
            total -= shed_so_far
            curtailed_kwh_by_tick[t] = shed_so_far * 0.25  # dt_hours folded in by caller via scaling if needed

        common_shed[t] = shed_common
        curtailed_ids_by_tick.append(houses_to_shed)
        kva[t] = total / spec.assumed_power_factor
        state.append(spec.state_for(kva[t]))

    return TransformerDecision(kva, state, common_shed, house_mask, curtailed_ids_by_tick, curtailed_kwh_by_tick)
