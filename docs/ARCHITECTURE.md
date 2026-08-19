# ARCHITECTURE — AETHERGRID Ω

## 0. Scope note (read this first)

This document describes what is actually implemented, not the full aspirational
vision in the brief. Every component below either exists in code or is
explicitly marked `[STUB]` / `[FALLBACK]` with the reason. See
`docs/LIMITATIONS.md` for the authoritative cut list. Tiering follows the
brief's own priority order (Tier S mandatory → Tier C cut first under time
pressure).

## 1. Repository inspection (pre-build state)

Empty directory, no git repo, no existing code/data. Python 3.11.9 with
numpy/pandas/scikit-learn/networkx/pydantic/scipy pre-installed. Installed for
this project: `pulp` (MILP/LP solver, CBC backend), `plotly`, `streamlit`,
`lightgbm`, `gymnasium`, `stable-baselines3` (torch already present).
No `highspy` — PuLP's bundled CBC is the LP/MILP backend used everywhere
`optimization/mpc.py` is invoked.

## 2. Components

| Layer | Module | Responsibility | Method |
|---|---|---|---|
| World | `core/world.py` | Load JSON world spec, instantiate buildings/resources/events | deterministic Python, Pydantic-validated |
| Building | `core/building.py`, `core/resources.py` | Per-building state: thermal zone, battery, thermal storage, EV, DHW, solar | RC physics + storage physics |
| EnergyDNA | `energy_dna/*` | Interpretable signature vector + flexibility map per building | feature engineering (FFT/autocorr/rolling stats), NOT a black box |
| Forecast | `forecasting/*` | Quantile forecasts (q05..q95) of load/thermal/solar | LightGBM quantile regression, sklearn `GradientBoostingRegressor(loss="quantile")` fallback |
| Calibration | `forecasting/calibration.py` | Pinball loss, empirical coverage, reliability curve, optional conformal correction | pure statistics on held-out data |
| Tariff | `tariff/*` | Compile tariff JSON → billing function | deterministic rule compiler, Pydantic schema-validated |
| Bill/M&V | `tariff/bill.py` | THE financial ground truth — energy/demand/ToU/PF/fixed charges | deterministic arithmetic, never ML/RL |
| Optimization | `optimization/*` | Rolling-horizon LP/MILP over flexible loads | PuLP + CBC, chance-constrained via quantile substitution |
| Safety Shield | `optimization/safety_shield.py` | Clip/project any proposed action (RL or MPC) onto the feasible/safe set | deterministic constraint projection, runs after every proposer |
| RL | `rl/*` | Adaptive policy layer that PROPOSES actions | PPO (stable-baselines3) when trainable in-session; deterministic adaptive controller fallback otherwise (`run_metadata.json` records which) |
| Digital Twin | `simulation/*` | RC thermal + electrical + storage physics, society/colony/connection orchestration | physics simulation, not learned |
| Graph / Synergy | `graph/*`, `synergy/*` | Energy Opportunity Graph: discover, test technical/economic feasibility of building-pair interactions | NetworkX + engineered features (no GNN in Tier S) |
| Stress Lab | `stress/*` | Inject adversarial JSON events into a running simulation | deterministic event application |
| Evaluation | `evaluation/*` | Baselines (8), Oracle, metrics, ablation, robustness, experiment runner, reports | all computed from simulator+bill output, never hand-entered |
| Dashboard | `ui/app.py` | Single-screen Streamlit view over stored run artifacts | Streamlit + Plotly |

## 3. Data flow (one control timestep)

```
JSON world/tariff/event
        │
        ▼
World.load() → Building[] (state) + FlexibilityMap[] + EnergyDNA[]
        │
        ▼
ForecastEngine.predict(history, horizon) → quantile forecast (q05..q95)
        │
        ▼
Controller (baseline | MPC | RL) → proposed action
        │
        ▼
SafetyShield.project(action, state, hard_constraints) → safe action
        │
        ▼
DigitalTwin.step(state, safe_action, weather, events) → next state, flows
        │
        ▼
BillEngine.accumulate(flows, tariff) → running bill
        │
        ▼
MetricsLogger.record(state, action, flows, bill) → timeseries row
        │
        └── loop to next timestep, feed new state back to Controller
```

## 4. Control flow (hierarchy)

```
Level 3 (Network/Connection Coordinator): evaluates candidate connection edges,
  activates only RECOMMENDED edges → passes connection budget down
Level 2 (Community Coordinator): allocates aggregate peak budget and shared
  flexibility across buildings, enforces per-building fairness caps
Level 1 (Local Building Controller): solves each building's own MPC/RL over
  HVAC/DHW/battery/EV/thermal-storage within the budget handed down
```

Levels 1–3 communicate through explicit numeric budgets/prices, not shared
mutable state — this keeps each level independently testable.

## 5. Experiment flow

```
configs/experiments/<name>.json (scenario) + controller name + seed
        │
        ▼
evaluation/experiments.py: run_experiment()
        │
        ├── run.json         (config hash, git hash, seed, controller/model versions)
        ├── timeseries.csv   (every timestep: state, action, flows, cost)
        ├── metrics.json     (PART AD metric set)
        └── summary.json     (headline numbers + comparison to Oracle/baseline)
        │
        ▼
evaluation/reports.py → docs-style JSON/markdown reports (forecast/control/robustness)
```

## 6. Tiering actually followed

- **Tier S (must work)**: JSON world, thermal simulator, tariff engine,
  BillEngine, EnergyDNA, quantile forecast, chance-constrained optimizer,
  synergy graph, counterfactual connection test, stress engine, evaluation
  table, dashboard. **Fully implemented.**
- **Tier A**: safety shield (implemented), hierarchical controller
  (implemented, 3 explicit levels), colony/resilience mode (implemented),
  PPO RL (implemented with documented fallback), robustness score
  (implemented).
- **Tier B**: GNN — **cut**, using engineered NetworkX graph aggregation
  instead (explicitly allowed fallback). Conformal calibration — implemented
  as an optional lightweight wrapper. Advanced embeddings — PCA baseline
  only. Multi-agent RL — **cut**.
- **Tier C**: LLM tariff extraction — **cut** (tariffs are hand-authored
  JSON, schema-validated). Natural-language decision verbalizer — **cut**
  (structured `DecisionExplainer` objects exist; no LLM narrates them).
  Advanced animations — **cut**.

## 7. Honesty mechanisms enforced in code

- `BillEngine` is the only path that produces a currency number; no other
  module is allowed to emit one (enforced by convention + tests).
- Every forecast interval ships with a calibration flag
  (`CALIBRATED`/`UNCALIBRATED`) computed from held-out coverage, not asserted.
- `run_metadata.json` per experiment records any Tier→fallback substitution
  (PART AV) so a viewer can see when e.g. PPO training fell back to the
  deterministic adaptive controller.
- Digital-twin RC parameters are tagged `PARAMETERS SYNTHETIC / ASSUMED`
  (no historical building data exists to identify them from) — surfaced in
  the dashboard, per PART Q.
