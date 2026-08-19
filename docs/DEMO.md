# DEMO

## Setup

```bash
streamlit run aethergrid/ui/app.py
```

Opens one screen: WORLD selector (SOCIETY / COLONY / CONNECTION), CONTROL
selector (BASELINE / HYBRID / SAFE RL), STRESS LAB, a live grid chart, a
comfort chart, an AI decision explainer, and a live results table
(Baseline | Hybrid | Safe RL | Oracle).

## Suggested walkthrough (~2 minutes)

1. **Start on SOCIETY, BASELINE, no stress.** Point at the BILL/PEAK KPIs
   and the Live Grid chart — a simple rule-based controller, no
   forecasting, no optimization.

2. **Switch CONTROL to HYBRID.** Watch the bill and peak drop, and the
   comfort-band chart tighten. Open the AI Decision panel, drag the
   timestep slider to a battery-discharge moment, and read the generated
   reason ("Battery discharging X kW to offset grid import at ₹Y/kWh") —
   this is generated from real simulation state, not an LLM.

3. **Set STRESS LAB to GRID OUTAGE, switch WORLD to COLONY.** Re-run
   `python -m aethergrid.run --world colony --scenario
   aethergrid/configs/worlds/colony.json` in a terminal alongside (the
   dashboard's colony resilience view is CLI-driven, see
   `docs/LIMITATIONS.md`) — show the resilience summary: which building
   kept critical load served longest, and why (battery sizing relative to
   its own base load, not just its criticality flag).

4. **Switch WORLD to CONNECTION.** Show the Energy Opportunity Graph —
   discovered building pairs, colored by status
   (grey=DISCOVERED, yellow=TECHNICALLY_PLAUSIBLE, green=ECONOMICALLY_VIABLE
   /RECOMMENDED, red=REJECTED). Hover an edge to show its complementarity
   scores. Run `python -m aethergrid.run --world connection --scenario
   aethergrid/configs/worlds/connection.json` for the full counterfactual
   (RUN A/B/C) numbers and final recommendation, including a case where
   the system says **DO NOT CONNECT** if you push the infrastructure cost
   up (see `tests/test_counterfactual.py` for a scripted example).

5. **Close on the results table + Oracle row.** "This isn't a fixed 20%
   savings claim — it's the fraction of the theoretically achievable
   improvement we actually captured, computed the same way for every
   controller."

## What to say if asked "why not RL?"

"Across CityLearn 2021–2023, no top-performing team used RL for
scheduling — winning entries used classical MPC and heuristics, reportedly
because no training environment (including this one) is rich enough for
RL to out-learn a well-specified optimizer. We train RL anyway, as a
secondary controller, specifically to test that claim here rather than
assume it — see `docs/METHODOLOGY.md`."

## What to say if the forecast is wrong

"That's the point of the STRESS LAB. Trigger SENSOR DROPOUT or a
FORECAST_BIAS scenario and re-run — the chance-constrained controller
degrades gracefully because its whole guarantee is a calibrated quantile,
not a point estimate. If the quantile forecast is itself miscalibrated,
the Forecast Report will say `UNCALIBRATED`, not silently claim a
guarantee it can't back up."

## Known rough edges for a live demo

- The dashboard computes each (world, controller, building, stress)
  combination on first view (cached after that) — HYBRID/oracle rows in
  the results table take up to ~30s the first time; have `python -m
  aethergrid.evaluate --all` output pre-generated as a backup slide.
- `--world connection` from the CLI is the slowest command (several
  minutes) because it runs real counterfactual simulations for the top
  candidates — start it before the talk, not during it.
