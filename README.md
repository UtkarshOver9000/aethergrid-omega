# AETHERGRID Ω

**Adaptive Energy & Thermal Ecosystem for Hierarchical Grid Intelligence**

AI-based electricity demand optimization for smart buildings — a
closed-loop digital twin and hierarchical control system spanning three
scales: a single **building**, a **colony** (constrained microgrid with a
critical-load priority hierarchy and resilience mode), and a **connection**
layer that discovers and economically validates (or rejects) coordination
opportunities between buildings.

> Most systems optimize the building. AETHERGRID forecasts with
> uncertainty, controls with a safety shield in front of every action,
> discovers when buildings can help each other, and proves — via a
> deterministic bill engine and a perfect-foresight oracle — whether every
> intervention was actually worth it.

## Quick start

```bash
pip install -r requirements.txt
python -m pytest -q

python -m aethergrid.run --world society --scenario aethergrid/configs/worlds/society.json
python -m aethergrid.run --world colony --scenario aethergrid/configs/worlds/colony.json
python -m aethergrid.run --world connection --scenario aethergrid/configs/worlds/connection.json

python -m aethergrid.evaluate --all
streamlit run aethergrid/ui/app.py
```

See `docs/DEMO.md` for a guided walkthrough and `docs/EXPERIMENTS.md` for
what each command produces.

## Architecture (short version)

```
JSON world/tariff/event  ->  World/Building (RC thermal + storage physics)
        -> EnergyDNA (interpretable signatures) + Flexibility Map
        -> Forecast (LightGBM quantile regression, calibrated)
        -> Chance-constrained rolling-horizon MPC (PuLP/CBC LP)
           [+ RL policy, comparison arm]
        -> Safety Shield (hard-bound projection, RULE 3, always on)
        -> Digital Twin physics step
        -> BillEngine (deterministic financial ground truth)
        -> Evaluation (8 baselines, Oracle, ablation, robustness, reports)
```

Full diagram and module-by-module responsibilities: `docs/ARCHITECTURE.md`.

## Why this shape

Classical chance-constrained MPC, not reinforcement learning, is the
primary controller here. Across CityLearn 2021–2023 at NeurIPS, no
top-performing team used RL for building-energy scheduling; winning
entries used classical optimization and hierarchical forecast+MPC
composition — reportedly because no training environment (a hackathon has
even less of one than a competition) is rich enough for RL to out-learn a
well-specified optimizer. AETHERGRID trains a PPO policy anyway, as a
secondary comparison arm, specifically to test that finding in this
environment rather than assume it. See `docs/METHODOLOGY.md`.

The one mechanical idea that does the real work: the MPC solves the exact
same LP whether it's given the mean forecast or a conservative quantile
(q95 demand / q05 solar) — chance-constrained control is a one-line
substitution (`optimization/chance_constraints.py`), which is what makes
the uncertainty-vs-mean comparison in the results table a fair,
apples-to-apples test rather than two different optimizers.

## The five research hypotheses

| | Hypothesis | Where it's tested |
|---|---|---|
| H1 | Uncertainty-aware forecasting reduces costly peak-demand violations vs mean-only forecasting | `mean_mpc` vs `quantile_mpc`, `evaluation/baselines.py` |
| H2 | Hierarchical coordination beats independent building optimization | `society` vs `colony`/`connection` worlds, `simulation/colony.py`, `synergy/counterfactual.py` |
| H3 | Adaptive RL improves performance under distribution shift vs a static policy | `rl`/`safe_rl` vs `quantile_mpc` under stress, `evaluation/robustness.py` |
| H4 | Cross-building synergy discovery finds opportunities independent optimization can't see | `graph/graph.py`, `synergy/discovery.py` |
| H5 | A safety-constrained hybrid beats unconstrained RL on cost/comfort/resilience | `evaluation/ablation.py:FULL_minus_safety_shield` |

None of these are assumed true going in — see `docs/METHODOLOGY.md` for
how each is actually falsifiable, and `docs/generated/` (produced by
`python -m aethergrid.evaluate --all`) for the real numbers.

## What is measured / simulated / assumed / learned / optimized / NOT modeled

Full claim-discipline statement, including the specific things this build
deliberately did NOT do given a single-session time budget (real building
meter data, multi-agent RL, a GNN, physical energy transfer between most
building pairs, an LLM anywhere in the money path): **`docs/LIMITATIONS.md`**.
Read this before quoting any number from this project.

## Repository layout

```
aethergrid/
  configs/{worlds,tariffs,experiments}/   JSON scenario definitions
  schemas/          Pydantic schemas (world, building, tariff, event, experiment)
  core/             World/Building/resources, weather, the reusable simulation loop
  energy_dna/       Interpretable building signatures + flexibility map
  forecasting/      Quantile ML forecaster, calibration, MPC's fast path forecaster
  tariff/           Tariff compiler, validator, BillEngine (financial ground truth)
  simulation/       RC thermal, storage, electrical, grid, colony orchestration
  optimization/     MPC (LP), chance constraints, safety shield, constraints
  rl/               Gymnasium env, PPO training/eval, deterministic fallback policy
  graph/            Energy Opportunity Graph (NetworkX + engineered features)
  synergy/          Discovery, technical/economic feasibility, counterfactual test
  stress/           Adversarial event injectors (heatwave, outage, sensor dropout, ...)
  evaluation/       Baselines, Oracle, metrics, ablation, robustness, experiment runner, reports
  ui/                Streamlit one-screen dashboard
  tests/            pytest suite (reproducibility, safety, bill-matches-hand-calc, ...)
  run.py            `python -m aethergrid.run --world ... --scenario ...`
  evaluate.py       `python -m aethergrid.evaluate --all`
docs/
  ARCHITECTURE.md   Component/data-flow/control-flow diagrams
  METHODOLOGY.md    Hypotheses, why MPC over RL, weight calibration rationale
  EXPERIMENTS.md    How to run and reproduce every reported number
  LIMITATIONS.md    Claim discipline: measured / simulated / assumed / not modeled
  DEMO.md           Guided walkthrough script
```

## Stack

Python 3.11 · NumPy/Pandas/scikit-learn · LightGBM (quantile regression) ·
PuLP+CBC (LP) · Gymnasium + stable-baselines3 (PPO) · NetworkX · Plotly ·
Streamlit · Pydantic
