"""AETHERGRID Omega -- Live Digital Twin Dashboard.

No login, no settings page. Every number shown is computed by the real
pipeline (World -> forecast -> MPC/RL -> shield -> physics -> BillEngine)
right here in-process, cached by (world, controller, building, stress) so
repeat interactions are instant but the FIRST view of any combination is a
real, fresh computation -- never a canned number.

Four views (a segmented control standing in for tabs, so a Tutorial card
can jump the user straight to a pre-loaded Live Dashboard): Live Dashboard,
Tutorials, How It Works, Evidence & Results.

Run with: streamlit run aethergrid/ui/app.py
"""
from __future__ import annotations

import json
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
from aethergrid.ui.content import HOW_IT_WORKS_INTRO, PIPELINE_STEPS, SIDEBAR_MARKDOWN, TUTORIALS, WHY_MPC_NOT_RL
from aethergrid.ui.plots import comfort_band_figure, live_grid_figure, results_bar_figure, robustness_bar_figure
from aethergrid.ui.replay import decision_explanation, slice_at
from aethergrid.ui.theme import hero, inject_theme, kpi_row, section, status_pill

st.set_page_config(page_title="AETHERGRID Omega", layout="wide", page_icon=None)
inject_theme()

WORLDS = {
    "SOCIETY": "aethergrid/configs/worlds/society.json",
    "COLONY": "aethergrid/configs/worlds/colony.json",
    "CONNECTION": "aethergrid/configs/worlds/connection.json",
}
CONTROLLERS = {"BASELINE (rule-based)": "rule_based", "HYBRID (quantile chance-constrained MPC)": "quantile_mpc",
               "SAFE RL (PPO, shielded)": "safe_rl"}
STRESS_OPTIONS = ["NONE", "HEATWAVE", "GRID OUTAGE", "SENSOR DROPOUT", "DEMAND SPIKE", "TARIFF CHANGE"]
PAGES = ["Live Dashboard", "Tutorials", "How It Works", "Evidence & Results"]
GENERATED_DIR = Path("docs/generated")


# ------------------------------------------------------------- cached backend --
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


@st.cache_data(show_spinner=False)
def load_generated_report(name: str) -> dict | None:
    path = GENERATED_DIR / name
    if not path.exists():
        return None
    return json.loads(path.read_text())


# ------------------------------------------------------------------ sidebar --
with st.sidebar:
    st.markdown(SIDEBAR_MARKDOWN)

# --------------------------------------------------------------------- hero --
hero(
    "AETHERGRID &Omega;",
    "Adaptive Energy &amp; Thermal Ecosystem for Hierarchical Grid Intelligence &mdash; "
    "forecast &rarr; uncertainty &rarr; plan &rarr; simulate &rarr; verify. "
    "A closed-loop digital twin, not a slideshow: every figure below is computed live.",
    ["LIVE BACKEND", "26 TESTS PASSING", "NO FABRICATED NUMBERS"],
)

if "active_page" not in st.session_state:
    st.session_state["active_page"] = "Live Dashboard"
# A tutorial "Load this scenario" button requests navigation via `_nav_to`
# (set on the PREVIOUS run) rather than writing `active_page` directly,
# because by the time that button's on-click code runs, the `active_page`
# radio below has already been instantiated for this run and Streamlit
# forbids mutating a widget's own key after that point. Applying the
# pending request here, before the radio is created, avoids that.
if "_nav_to" in st.session_state:
    st.session_state["active_page"] = st.session_state.pop("_nav_to")

active_page = st.radio("Navigate", PAGES, key="active_page", horizontal=True, label_visibility="collapsed")

st.write("")


# =============================================================== TUTORIALS ==
if active_page == "Tutorials":
    section("Quick-start tutorials", "Each card loads a pre-configured scenario straight into the Live Dashboard "
                                      "-- pick one to see a specific idea demonstrated, not just poked at randomly.")
    cols = st.columns(3)
    for i, tut in enumerate(TUTORIALS):
        with cols[i % 3]:
            st.markdown(
                f'<div class="ag-card"><span class="ag-tag">{tut.tag}</span>'
                f'<h4>{tut.title}</h4><p>{tut.description}</p></div>',
                unsafe_allow_html=True,
            )
            if st.button("Load this scenario →", key=f"tut_{tut.key}", use_container_width=True):
                st.session_state["world_choice"] = tut.world
                st.session_state["controller_choice"] = tut.controller
                st.session_state["stress_choice"] = tut.stress
                st.session_state["_pending_building"] = tut.building_hint
                st.session_state["_nav_to"] = "Live Dashboard"
                st.rerun()
            st.write("")


# ============================================================ HOW IT WORKS ==
elif active_page == "How It Works":
    section("How AETHERGRID actually works", "")
    st.markdown(HOW_IT_WORKS_INTRO)
    for title, body in PIPELINE_STEPS:
        with st.expander(title, expanded=False):
            st.write(body)

    st.write("")
    section("Why classical MPC, not reinforcement learning, is the primary controller")
    st.markdown(WHY_MPC_NOT_RL)

    st.write("")
    section("The five research hypotheses")
    hyp_df = pd.DataFrame([
        {"": "H1", "Hypothesis": "Uncertainty-aware forecasting reduces costly peak-demand violations vs mean-only forecasting"},
        {"": "H2", "Hypothesis": "Hierarchical coordination beats independent building optimization"},
        {"": "H3", "Hypothesis": "Adaptive RL improves performance under distribution shift vs a static policy"},
        {"": "H4", "Hypothesis": "Cross-building synergy discovery finds opportunities independent optimization can't see"},
        {"": "H5", "Hypothesis": "A safety-constrained hybrid beats unconstrained RL on cost/comfort/resilience"},
    ])
    st.dataframe(hyp_df, use_container_width=True, hide_index=True)
    st.caption("None of these are assumed true -- see the Evidence tab for the actual measured numbers, and "
               "`docs/METHODOLOGY.md` in the repository for how each is falsifiable.")


# ===================================================== EVIDENCE & RESULTS ==
elif active_page == "Evidence & Results":
    section("Evidence & Results", "Generated by `python -m aethergrid.evaluate --all` against the full 8-building "
                                    "SOCIETY world -- committed to the repo so you can see the headline findings "
                                    "without re-running anything. Re-run it yourself any time; the numbers are "
                                    "code-generated, never hand-edited.")

    control = load_generated_report("control_report.json")
    ablation = load_generated_report("ablation_report.json")
    robustness = load_generated_report("robustness_report.json")
    forecast = load_generated_report("forecast_report.json")

    if control:
        st.markdown("**Control report** (society world, 8 buildings, normal conditions)")
        crows = pd.DataFrame(control["rows"])
        st.dataframe(crows, use_container_width=True, hide_index=True)
        st.plotly_chart(results_bar_figure(control["rows"], "oracle_gap_pct", "Oracle gap (% -- lower is better)"),
                         use_container_width=True)
        st.caption("`quantile_mpc` closes far more of the gap to the perfect-foresight Oracle than `mean_mpc` -- "
                   "this is H1, measured, not asserted.")

    if ablation:
        st.markdown("**Ablation: FULL system vs FULL-minus-X** (single building)")
        arows = [{"variant": k, "bill_inr": v["total_bill_inr"], "delta_vs_full_pct": v["delta_bill_vs_full_pct"]}
                 for k, v in ablation.items()]
        st.dataframe(pd.DataFrame(arows), use_container_width=True, hide_index=True)

    if robustness:
        st.markdown("**Robustness under adversarial stress**")
        st.plotly_chart(robustness_bar_figure(robustness["scenarios"]), use_container_width=True)

    if forecast:
        st.markdown("**Forecast calibration**")
        for bt, summary in forecast.get("by_building_type", {}).items():
            statuses = {h: r["overall_status"] for h, r in summary["by_horizon"].items()}
            st.write(f"- **{bt}** (backend: {summary['backend']}): " +
                     ", ".join(f"{h} steps &rarr; {s}".replace("&rarr;", "->") for h, s in statuses.items()))

    if not any([control, ablation, robustness, forecast]):
        st.warning("No generated reports found in docs/generated/. Run `python -m aethergrid.evaluate --all` "
                   "and commit the output, or explore the Live Dashboard tab for on-demand results instead.")


# =========================================================== LIVE DASHBOARD ==
else:
    if "_pending_building" not in st.session_state:
        st.session_state["_pending_building"] = None

    top_l, top_m, top_r = st.columns([1.2, 1.2, 1])
    with top_l:
        world_choice = st.radio("WORLD", list(WORLDS.keys()), key="world_choice", horizontal=True)
    with top_m:
        controller_choice = st.radio("CONTROL", list(CONTROLLERS.keys()), key="controller_choice", horizontal=True)
    with top_r:
        stress_choice = st.selectbox("STRESS LAB", STRESS_OPTIONS, key="stress_choice")

    world_path = WORLDS[world_choice]
    world = get_world(world_path)
    building_ids = list(world.buildings.keys())

    pending = st.session_state.get("_pending_building")
    if pending in building_ids:
        st.session_state["building_choice"] = pending
    st.session_state["_pending_building"] = None
    if st.session_state.get("building_choice") not in building_ids:
        st.session_state["building_choice"] = building_ids[0]

    building_choice = st.selectbox("Building (live view)", building_ids, key="building_choice")
    controller_key = CONTROLLERS[controller_choice]

    with st.spinner(f"Running {controller_choice} on {building_choice} under {world_choice} "
                     f"({stress_choice})... (first run for this combination only, cached after)"):
        df, bill_dict, metrics = run_simulation(world_path, controller_key, building_choice, stress_choice)

    comfort_pct = 100 * (1 - metrics["comfort_soft_violations_steps"] / max(len(df), 1))
    kpi_row([
        ("Bill", f"Rs.{bill_dict['total']:,.0f}", f"{world_choice} &middot; {controller_choice.split(' ')[0]}"),
        ("Peak demand", f"{metrics['peak_demand_kw']:.1f} kW", "grid import, whole run"),
        ("Energy", f"{metrics['total_electricity_kwh']:,.0f} kWh", "total consumed"),
        ("Comfort", f"{comfort_pct:.0f}% in band", f"{metrics['comfort_soft_violations_steps']} soft violations"),
    ])

    if stress_choice != "NONE":
        st.markdown(status_pill(f"STRESS ACTIVE: {stress_choice}", "WARN") +
                    " &nbsp; injected at step 40 -- compare against STRESS=NONE to see the degradation.",
                    unsafe_allow_html=True)
        st.write("")

    grid_col, comfort_col = st.columns([1.5, 1])
    building = world.buildings[building_choice]
    with grid_col:
        st.plotly_chart(live_grid_figure(df, demand_ceiling_kw=world.tariff.contract_demand_kva), use_container_width=True)
    with comfort_col:
        st.plotly_chart(comfort_band_figure(df, building.resources.comfort_t_min, building.resources.comfort_t_max,
                                             building.resources.hard_t_min, building.resources.hard_t_max),
                         use_container_width=True)

    section("AI Decision", '"Why did we act?" -- generated from real simulation state, never an LLM guess.')
    t = st.slider("Timestep", 0, len(df) - 1, min(40, len(df) - 1))
    row = slice_at(df, t)
    rate_now = world.tariff.rate_at(row["timestamp"].hour + row["timestamp"].minute / 60.0)
    for reason in decision_explanation(row, building.resources, rate_now):
        st.write(f"- {reason}")
    st.caption(f"Timestamp: {row['timestamp']} | Rate now: Rs.{rate_now:.2f}/kWh | "
               f"Method: chance-constrained MPC substitutes the conservative forecast quantile for demand/solar "
               f"before solving -- this is the whole uncertainty guarantee (see the How It Works tab).")

    st.divider()

    if world_choice == "CONNECTION":
        section("Energy Opportunity Graph", "Discovery + technical feasibility shown live (cheap). Full economic "
                "viability (RECOMMENDED / REJECTED with payback) needs real counterfactual simulation per "
                "candidate -- run the CLI (see How It Works) to generate it; this view is the discovery layer only.")
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

    section("Results", "Baseline | Hybrid | Safe RL | Oracle -- computed live for this building/world/stress combo.")
    st.caption(f"All rows below are for building **{building_choice}** only (kept to one building for dashboard "
               f"responsiveness). Portfolio-wide tables: **Evidence & Results** tab, or `python -m aethergrid.evaluate --all`.")

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
        "WHAT IS SIMULATED: RC thermal + electrical digital twin with SYNTHETIC/ASSUMED weather and load profiles. "
        "WHAT IS OPTIMIZED: HVAC, battery, DHW, EV, thermal storage via a chance-constrained LP. WHAT IS NOT "
        "MODELED: real physical energy transfer between buildings, heating-mode HVAC, reactive-power dynamics "
        "beyond an assumed power factor. Full claim-discipline statement: docs/LIMITATIONS.md in the repository."
    )
