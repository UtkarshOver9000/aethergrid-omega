"""AETHERGRID Omega -- Live Digital Twin Dashboard (PART AH).

ONE SCREEN. No login. No settings page. Every number shown is computed by
the real pipeline (World -> forecast -> MPC/RL -> shield -> physics ->
BillEngine) right here in-process, cached by (world, controller, building,
stress) so repeat interactions are instant but the FIRST view of any
combination is a real, fresh computation -- never a canned number.

Run with: streamlit run aethergrid/ui/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd
import streamlit as st

from aethergrid.core.world import World
from aethergrid.energy_dna.signatures import compute_world_dna
from aethergrid.evaluation.baselines import quantile_mpc_policy, rule_based_policy, no_control_policy
from aethergrid.evaluation.metrics import compute_metrics
from aethergrid.evaluation.oracle import solve_oracle
from aethergrid.forecasting.path_forecast import PathForecaster
from aethergrid.forecasting.predict import build_training_building
from aethergrid.schemas.event import EventSpec
from aethergrid.schemas.experiment import ObjectiveWeights
from aethergrid.stress.engine import build_stress_context
from aethergrid.core.timestep import simulate_building_series
from aethergrid.tariff.bill import BillEngine
from aethergrid.ui.plots import comfort_band_figure, live_grid_figure, results_bar_figure, robustness_bar_figure
from aethergrid.ui.replay import decision_explanation, slice_at

st.set_page_config(page_title="AETHERGRID Omega", layout="wide", page_icon=None)

WORLDS = {
    "SOCIETY": "aethergrid/configs/worlds/society.json",
    "COLONY": "aethergrid/configs/worlds/colony.json",
    "CONNECTION": "aethergrid/configs/worlds/connection.json",
}
CONTROLLERS = {"BASELINE (rule-based)": "rule_based", "HYBRID (quantile chance-constrained MPC)": "quantile_mpc",
               "SAFE RL (PPO, shielded)": "safe_rl"}
STRESS_OPTIONS = ["NONE", "HEATWAVE", "GRID OUTAGE", "SENSOR DROPOUT", "DEMAND SPIKE", "TARIFF CHANGE"]


@st.cache_resource(show_spinner=False)
def get_world(world_path: str) -> World:
    return World.load(world_path)


@st.cache_resource(show_spinner=False)
def get_forecasters_cached(building_type: str, seed: int) -> tuple[PathForecaster, PathForecaster]:
    _, train_df = build_training_building(building_type, seed=seed + 500, n_days=45, dt_minutes=15)
    load_pf = PathForecaster.fit(train_df["base_load_kw"].values, 96, 32)
    solar_pf = PathForecaster.fit(train_df["solar_kw"].values, 96, 32)
    return load_pf, solar_pf


def _policy_for(name: str, building_type: str):
    if name == "rule_based":
        return rule_based_policy
    if name == "quantile_mpc":
        return quantile_mpc_policy
    if name == "safe_rl":
        from aethergrid.rl.evaluate import load_rl_policy
        policy_fn, meta = load_rl_policy(building_type)
        return policy_fn
    return no_control_policy


@st.cache_data(show_spinner=False)
def run_simulation(world_path: str, controller: str, building_id: str, stress: str, event_start_step: int = 40):
    world = get_world(world_path)
    building = world.buildings[building_id]
    load_pf, solar_pf = get_forecasters_cached(building.archetype.type, world.spec.world.seed)
    policy_fn = _policy_for(controller, building.archetype.type)

    events = []
    if stress != "NONE":
        start = world.index[event_start_step]
        spec_map = {
            "HEATWAVE": dict(type="heatwave", duration_hours=8, temperature_delta=7.0),
            "GRID OUTAGE": dict(type="grid_outage", duration_hours=4),
            "SENSOR DROPOUT": dict(type="sensor_dropout", duration_hours=6, uncertainty_inflation=3.0),
            "DEMAND SPIKE": dict(type="demand_spike", duration_hours=2, magnitude_frac_of_peak=0.6),
        }
        if stress in spec_map:
            events = [EventSpec.model_validate({**spec_map[stress], "start": start})]

    tariff_override = None
    if stress == "TARIFF CHANGE":
        import json
        with open("aethergrid/configs/tariffs/tariff_shift.json") as f:
            from aethergrid.tariff.compiler import compile_tariff
            tariff_override = compile_tariff(json.load(f))

    sim_world = world
    if tariff_override is not None:
        sim_world = World(spec=world.spec, index=world.index, dt_hours=world.dt_hours, weather=world.weather,
                           buildings=world.buildings, tariff=tariff_override, grid_capacity_kw=world.grid_capacity_kw)

    stress_ctx = build_stress_context(sim_world, events)
    base_fc = lambda t, H: load_pf.forecast_path(building.profile.base_load_kw, t, H)
    solar_fc = lambda t, H: solar_pf.forecast_path(building.profile.solar_potential_kw, t, H)
    if events:
        base_fc = stress_ctx.wrap_forecast(sim_world, base_fc)

    series = simulate_building_series(
        building, sim_world, policy_fn, horizon_steps=32, risk_level=0.05, weights=ObjectiveWeights(),
        carbon_kg_per_kwh=0.71, forecast_base_load_fn=base_fc, forecast_solar_fn=solar_fc,
        outage_mask=stress_ctx.outage_mask if events else None,
        solar_failure_mask=stress_ctx.solar_failure_mask if events else None,
        demand_spike_addon_kw=stress_ctx.demand_spike_addon(sim_world, building_id) if events else None,
    )
    bill = BillEngine.compute(sim_world.index, series.import_kw, series.export_kw, sim_world.dt_hours, sim_world.tariff)
    metrics = compute_metrics(series, bill, sim_world.dt_hours, 0.71)
    return series.to_frame(), bill.as_dict(), metrics


@st.cache_data(show_spinner=False)
def run_oracle_cached(world_path: str, building_id: str):
    world = get_world(world_path)
    building = world.buildings[building_id]
    series = solve_oracle(building, world, ObjectiveWeights(), 0.71)
    bill = BillEngine.compute(world.index, series.import_kw, series.export_kw, world.dt_hours, world.tariff)
    metrics = compute_metrics(series, bill, world.dt_hours, 0.71)
    return bill.as_dict(), metrics


# ---------------------------------------------------------------- header --
st.markdown("## AETHERGRID Omega")
st.caption("Adaptive Energy & Thermal Ecosystem for Hierarchical Grid Intelligence -- "
           "forecast -> uncertainty -> plan -> simulate -> verify")

top_l, top_m, top_r = st.columns([1.2, 1.2, 1])
with top_l:
    world_choice = st.radio("WORLD", list(WORLDS.keys()), horizontal=True)
with top_m:
    controller_choice = st.radio("CONTROL", list(CONTROLLERS.keys()), horizontal=True)
with top_r:
    stress_choice = st.selectbox("STRESS LAB", STRESS_OPTIONS)

world_path = WORLDS[world_choice]
world = get_world(world_path)
building_ids = list(world.buildings.keys())
building_choice = st.selectbox("Building (live view)", building_ids)

controller_key = CONTROLLERS[controller_choice]

with st.spinner(f"Running {controller_choice} on {building_choice} under {world_choice} "
                 f"({stress_choice})... (first run for this combination only)"):
    df, bill_dict, metrics = run_simulation(world_path, controller_key, building_choice, stress_choice)

# --------------------------------------------------------------- KPI row --
k1, k2, k3, k4 = st.columns(4)
k1.metric("BILL", f"Rs.{bill_dict['total']:,.0f}")
k2.metric("PEAK", f"{metrics['peak_demand_kw']:.1f} kW")
k3.metric("ENERGY", f"{metrics['total_electricity_kwh']:,.0f} kWh")
comfort_pct = 100 * (1 - metrics["comfort_soft_violations_steps"] / max(len(df), 1))
k4.metric("COMFORT", f"{comfort_pct:.0f}% within band")

st.divider()

# ---------------------------------------------------------- live grid + comfort --
grid_col, comfort_col = st.columns([1.5, 1])
building = world.buildings[building_choice]
with grid_col:
    st.plotly_chart(live_grid_figure(df, demand_ceiling_kw=world.tariff.contract_demand_kva), use_container_width=True)
with comfort_col:
    st.plotly_chart(comfort_band_figure(df, building.resources.comfort_t_min, building.resources.comfort_t_max,
                                         building.resources.hard_t_min, building.resources.hard_t_max),
                     use_container_width=True)

# --------------------------------------------------------------- AI decision --
st.markdown("#### AI Decision -- \"Why did we act?\"")
t = st.slider("Timestep", 0, len(df) - 1, min(40, len(df) - 1))
row = slice_at(df, t)
rate_now = world.tariff.rate_at(row["timestamp"].hour + row["timestamp"].minute / 60.0)
for reason in decision_explanation(row, building.resources, rate_now):
    st.write(f"- {reason}")
st.caption(f"Timestamp: {row['timestamp']} | Rate now: Rs.{rate_now:.2f}/kWh | "
           f"Method: chance-constrained MPC substitutes the conservative forecast quantile for demand/solar "
           f"before solving -- this is the whole uncertainty guarantee (see docs/METHODOLOGY.md).")

st.divider()

# ---------------------------------------------------------- energy opportunity graph --
if world_choice == "CONNECTION":
    st.markdown("#### Energy Opportunity Graph")
    st.caption("Discovery + technical feasibility shown live below (cheap). Full economic viability (RECOMMENDED / "
               "REJECTED with payback) requires real counterfactual simulation per candidate -- run "
               "`python -m aethergrid.run --world connection --scenario aethergrid/configs/worlds/connection.json` "
               "to generate it; this view shows the discovery layer only for responsiveness.")
    from aethergrid.synergy.discovery import discover_candidates
    from aethergrid.synergy.feasibility import assess_technical_feasibility
    from aethergrid.graph.features import node_feature_dict, synthetic_coordinates
    import networkx as nx
    from aethergrid.ui.graph_view import energy_opportunity_graph_figure

    dna = compute_world_dna(world)
    candidates = discover_candidates(world, dna)
    for c in candidates:
        assess_technical_feasibility(c)
    G = nx.Graph()
    coords = {bid: synthetic_coordinates(bid) for bid in world.building_ids}
    for bid in world.building_ids:
        G.add_node(bid, **node_feature_dict(dna[bid], coords[bid]))
    for c in candidates:
        key = (c.edge.source, c.edge.sink)
        if not G.has_edge(*key) or G.edges[key]["score"] < c.score:
            edge_attrs = c.edge.as_dict()
            G.add_edge(c.edge.source, c.edge.sink, score=c.score, status=c.status,
                        color={"DISCOVERED": "#9aa0a6", "TECHNICALLY_PLAUSIBLE": "#f2c94c",
                               "REJECTED": "#eb5757"}.get(c.status, "#9aa0a6"),
                        reasons=c.reasons, **edge_attrs)
    st.plotly_chart(energy_opportunity_graph_figure(G), use_container_width=True)
    st.divider()

# --------------------------------------------------------------- stress lab --
if stress_choice != "NONE":
    st.info(f"STRESS ACTIVE: {stress_choice} injected at step 40. Compare against STRESS=NONE to see degradation.")

st.divider()

# --------------------------------------------------------------- results table --
st.markdown("#### Results -- Baseline | Hybrid | Safe RL | Oracle")
st.caption(f"All rows below are for building **{building_choice}** only, world=**{world_choice}**, stress=**{stress_choice}** "
           f"(kept to one building for dashboard responsiveness -- portfolio-wide tables come from "
           f"`python -m aethergrid.evaluate --all`).")

rows = []
for label, key in CONTROLLERS.items():
    with st.spinner(f"Computing {label}..."):
        _, b, m = run_simulation(world_path, key, building_choice, stress_choice)
    rows.append({"controller": label, "bill_inr": b["total"], "peak_kw": m["peak_demand_kw"],
                 "energy_kwh": m["total_electricity_kwh"], "comfort_violations": m["comfort_soft_violations_steps"],
                 "carbon_kg": m["carbon_kg"]})

with st.spinner("Computing Oracle (perfect foresight upper bound)..."):
    oracle_bill, oracle_metrics = run_oracle_cached(world_path, building_choice)
rows.append({"controller": "ORACLE (perfect foresight)", "bill_inr": oracle_bill["total"],
             "peak_kw": oracle_metrics["peak_demand_kw"], "energy_kwh": oracle_metrics["total_electricity_kwh"],
             "comfort_violations": oracle_metrics["comfort_soft_violations_steps"], "carbon_kg": oracle_metrics["carbon_kg"]})

results_df = pd.DataFrame(rows)
st.dataframe(results_df, use_container_width=True, hide_index=True)

bar_col1, bar_col2 = st.columns(2)
with bar_col1:
    st.plotly_chart(results_bar_figure(rows, "bill_inr", "Bill (Rs.)"), use_container_width=True)
with bar_col2:
    st.plotly_chart(results_bar_figure(rows, "peak_kw", "Peak demand (kW)"), use_container_width=True)

st.caption(
    "AETHERGRID Omega -- WHAT IS SIMULATED: RC thermal + electrical digital twin with SYNTHETIC/ASSUMED weather "
    "and load profiles. WHAT IS OPTIMIZED: HVAC, battery, DHW, EV, thermal storage via a chance-constrained LP. "
    "WHAT IS NOT MODELED: real physical energy transfer between buildings, heating-mode HVAC, reactive-power "
    "dynamics beyond an assumed power factor. See docs/LIMITATIONS.md for the full claim-discipline statement."
)
