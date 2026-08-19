# EXPERIMENTS

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

## What each command does

- **`aethergrid.run --world society`** — runs `quantile_mpc` on every
  building in `society.json` independently, prints per-building
  bill/peak/comfort, sums to a portfolio total.
- **`aethergrid.run --world colony`** — runs the shared-capacity,
  criticality-rationed colony controller (`simulation/colony.py`) with a
  4-hour outage injected partway through, prints the resilience summary
  (`hours_survived`, `critical_load_service_frac`,
  `min_battery_reserve_frac`, ...).
- **`aethergrid.run --world connection`** — runs `quantile_mpc`
  independently per building, then builds the Energy Opportunity Graph
  (discovery -> technical feasibility -> economics for the top-K
  candidates), printing each candidate's final status and reasoning. This
  is the slowest of the three (each economics assessment re-simulates two
  buildings three times) — expect several minutes.
- **`aethergrid.evaluate --all`** — the representative evaluation slice:
  a control-report table across `[no_control, rule_based, mean_mpc,
  quantile_mpc, oracle]` on the society world, a robustness suite (7
  stress scenarios) on one building, an ablation study (FULL vs
  FULL-minus-X), and a forecast calibration report for three building
  types. Writes `docs/generated/{forecast,control,robustness,ablation}_report.json`.
  This is intentionally NOT the full exhaustive matrix (every controller
  x every stress scenario x every world) — that would take hours of
  wall-clock LP-solving. Use the functions in `evaluation/experiments.py`
  and `evaluation/robustness.py` directly for a larger sweep.

## Experiment artifacts (PART AC)

Every call to `evaluation/experiments.py:run_experiment` writes, under
`aethergrid/runs/<run_id>/`:

- `run.json` — the full `ExperimentSpec`, git commit hash, config hash,
  seed, forecaster backend, and any Tier-fallback records (PART AV).
- `metrics.json` — aggregate + per-building metrics (PART AD).
- `timeseries.csv` — every timestep, every building, concatenated.
- `summary.json` — headline numbers.

`run_id` is `{experiment_name}_{controller}_{config_hash}` — identical
inputs always produce the identical `run_id` and (per TEST 1) identical
contents.

## Reproducing a specific number

Every reported number traces back through: `run.json` (which config +
seed + git commit produced it) -> `timeseries.csv` (the exact realized
series) -> `tariff/bill.py:BillEngine.compute` (the exact deterministic
arithmetic). There is no manual-entry step anywhere in this chain.

## Extending the evaluation matrix

To run the FULL controller x stress-scenario matrix instead of the
representative slice:

```python
from aethergrid.evaluation.experiments import run_experiment
from aethergrid.schemas.experiment import ExperimentSpec

for controller in ["no_control", "rule_based", "mean_mpc", "quantile_mpc",
                    "rl", "safe_rl", "hierarchical_hybrid", "oracle"]:
    spec = ExperimentSpec(name="full_matrix", world_config="aethergrid/configs/worlds/society.json",
                           controller=controller, seed=42)
    run_experiment(spec)
```

Combine with `evaluation/robustness.py:run_robustness_suite` per
controller for the full PART AK table (5 scenarios x 8 controllers = 40
runs; budget accordingly, each `quantile_mpc`-class run over the default
2-day/8-building society world takes ~3 minutes).
