"""Orchestrates one full society simulation run: builds the environment,
applies events, initializes every household/workspace/common-infra
entity, runs the two-pass transformer-breach curtailment (pass 1:
uncurtailed baseline -> decide curtailment; pass 2: re-simulate only the
curtailed households with their curtailment applied), and returns
everything the export layer needs. This is where the 19-step tick order
is actually realized -- not literally as 19 separate function calls per
tick (the household/workspace simulators are internally-looped pure
functions for performance), but in the same causal order: environment
and events are resolved first, occupancy/appliances/thermal/EV/solar/
storage per entity next, aggregation and the transformer state machine
last."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from aethergrid.worldsim.archetypes.households import ARCHETYPES as HOUSEHOLD_ARCHETYPES
from aethergrid.worldsim.engine.common_infra import simulate_common_infra
from aethergrid.worldsim.engine.events import apply_events_to_environment, build_event_effects
from aethergrid.worldsim.engine.household import HouseholdConfig, HouseholdSeries, make_household_config, simulate_household
from aethergrid.worldsim.engine.transformer import decide_transformer_state_and_curtailment
from aethergrid.worldsim.engine.weather import build_environment
from aethergrid.worldsim.engine.workspace import WorkspaceSeries, simulate_workspace
from aethergrid.worldsim.schemas.scenario import SocietyScenario, WorldSimScenario
from aethergrid.worldsim.schemas.workspace import WORKSPACE_ARCHETYPES


@dataclass
class SocietyResult:
    index: pd.DatetimeIndex
    environment: object
    dt_hours: float
    house_configs: list[HouseholdConfig]
    house_series: list[HouseholdSeries]
    workspace_series: WorkspaceSeries | None
    common_infra_kw: np.ndarray
    common_infra_series: object
    transformer_kva: np.ndarray
    transformer_state: list
    outage_mask: np.ndarray
    curtailed_ids_by_tick: list
    total_curtailed_kwh_by_tick: np.ndarray
    active_events_by_tick: list


def _assign_grid_positions(n: int, cols: int) -> list[tuple[int, int]]:
    return [(i % cols, i // cols) for i in range(n)]


def simulate_society(scenario: WorldSimScenario, society: SocietyScenario, base_seed: int) -> SocietyResult:
    rng = np.random.default_rng(base_seed)
    start = pd.Timestamp(scenario.date)
    env = build_environment(start, scenario.n_steps, scenario.interval_minutes, seed=base_seed,
                             lat_deg=scenario.latitude_deg, lon_deg=scenario.longitude_deg)
    env = apply_events_to_environment(env, scenario.events)
    effects = build_event_effects(env, scenario.events)
    dt_hours = scenario.interval_minutes / 60.0

    # --- assign each household an archetype by population share, plus a grid position ---
    names = list(HOUSEHOLD_ARCHETYPES.keys())
    shares = np.array([HOUSEHOLD_ARCHETYPES[n].share for n in names])
    archetype_choices = rng.choice(names, size=society.n_households, p=shares / shares.sum())
    positions = _assign_grid_positions(society.n_households, society.grid_cols)

    configs: list[HouseholdConfig] = []
    for i in range(society.n_households):
        arch_name = archetype_choices[i]
        gx, gz = positions[i]
        cfg = make_household_config(i, arch_name, HOUSEHOLD_ARCHETYPES[arch_name], society.ev_penetration,
                                     society.solar_penetration, gx, gz, seed=base_seed * 1000 + i)
        configs.append(cfg)

    # --- pass 1: uncurtailed baseline ---
    baseline_series: list[HouseholdSeries] = []
    for cfg in configs:
        arch = HOUSEHOLD_ARCHETYPES[cfg.archetype_name]
        s = simulate_household(cfg, arch, env, dt_hours, curtail_mask=None,
                                occupancy_multiplier=effects.occupancy_multiplier,
                                force_ev_present=effects.force_ev_present)
        baseline_series.append(s)

    n_steps = scenario.n_steps
    kw_matrix = np.stack([s.kw for s in baseline_series], axis=1)
    flex_matrix = np.stack([
        np.where(s.ac_on, 1.0, 0.0) * 1.65 + np.where(s.geyser_on, 1.0, 0.0) * 2.0
        + np.array([1.0 if "ev_charger" in d else 0.0 for d in s.deferrables_active]) * 3.3
        for s in baseline_series
    ], axis=1)

    aggregate_occupancy_frac = np.mean([s.occupancy for s in baseline_series], axis=0) / max(
        1e-6, np.mean([HOUSEHOLD_ARCHETYPES[c.archetype_name].occupancy.mean_occupant_count for c in configs]))
    aggregate_occupancy_frac = np.clip(aggregate_occupancy_frac, 0, 1)

    common_infra_series = simulate_common_infra(society.common_infra, env, dt_hours, aggregate_occupancy_frac, seed=base_seed)

    workspace_series = None
    workspace_kw = np.zeros(n_steps)
    if society.has_workspace:
        ws_arch = WORKSPACE_ARCHETYPES[society.workspace_archetype]
        workspace_series = simulate_workspace(ws_arch, env, dt_hours, seed=base_seed + 555)
        workspace_kw = workspace_series.kw

    workspace_kw = workspace_kw + effects.extra_load_kw

    decision = decide_transformer_state_and_curtailment(
        society.transformer, society.common_infra, kw_matrix, flex_matrix,
        common_infra_series.kw, common_infra_series.pump_on, common_infra_series.lift_active,
        common_infra_series.streetlights_on, common_infra_series.stp_on, common_infra_series.clubhouse_hvac_kw,
        workspace_kw,
    )

    # force outage windows to TRIPPED / zero grid regardless of computed loading
    for t in np.where(effects.outage_mask)[0]:
        decision.state[t] = "TRIPPED"
        decision.kva[t] = 0.0

    # The energy accounting above already subtracts non-critical common-infra
    # load on BREACH/TRIPPED (decision.common_infra_shed) -- but the exported
    # DISPLAY state (streetlights_on/pump_on/stp_on) was computed independently
    # from sun position / tank level and does NOT yet reflect that shedding.
    # Force it to match here so "streetlights go dark on trip" is a fact in
    # the JSON, not a cosmetic renderer choice (per the plan's explicit design
    # decision that breach cascades belong in the engine).
    shed_mask = decision.common_infra_shed | effects.outage_mask
    common_infra_series.streetlights_on = common_infra_series.streetlights_on & ~shed_mask
    common_infra_series.pump_on = common_infra_series.pump_on & ~shed_mask
    common_infra_series.stp_on = common_infra_series.stp_on & ~shed_mask
    common_infra_series.clubhouse_hvac_kw = np.where(shed_mask, 0.0, common_infra_series.clubhouse_hvac_kw)
    # During a full grid outage, lifts also stop (no backup); security/fire
    # systems are assumed battery-backed and stay on -- both documented
    # assumptions, not measured facts.
    common_infra_series.lift_active = common_infra_series.lift_active & ~effects.outage_mask

    # --- pass 2: re-simulate only households that were curtailed at least once ---
    curtailed_house_ids = sorted({hid for ids in decision.curtailed_house_ids_by_tick for hid in ids})
    final_series = list(baseline_series)
    for hid in curtailed_house_ids:
        cfg = configs[hid]
        arch = HOUSEHOLD_ARCHETYPES[cfg.archetype_name]
        mask = decision.house_curtail_mask[:, hid] | effects.outage_mask
        final_series[hid] = simulate_household(cfg, arch, env, dt_hours, curtail_mask=mask,
                                                 occupancy_multiplier=effects.occupancy_multiplier,
                                                 force_ev_present=effects.force_ev_present)

    # during an outage, ALL non-critical households lose grid supply too (their own
    # solar/battery can still serve local load, simulate_household already nets that)
    if effects.outage_mask.any():
        for hid in range(society.n_households):
            if hid not in curtailed_house_ids:
                cfg = configs[hid]
                arch = HOUSEHOLD_ARCHETYPES[cfg.archetype_name]
                final_series[hid] = simulate_household(cfg, arch, env, dt_hours, curtail_mask=effects.outage_mask,
                                                         occupancy_multiplier=effects.occupancy_multiplier,
                                                         force_ev_present=effects.force_ev_present)

    return SocietyResult(
        index=env.index, environment=env, dt_hours=dt_hours, house_configs=configs, house_series=final_series,
        workspace_series=workspace_series, common_infra_kw=common_infra_series.kw,
        common_infra_series=common_infra_series, transformer_kva=decision.kva, transformer_state=decision.state,
        outage_mask=effects.outage_mask, curtailed_ids_by_tick=decision.curtailed_house_ids_by_tick,
        total_curtailed_kwh_by_tick=decision.total_curtailed_kwh_by_tick,
        active_events_by_tick=effects.active_event_ids_by_tick,
    )
