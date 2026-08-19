# LIMITATIONS — what AETHERGRID Ω actually is and isn't

This document exists because RULE 1 of this project is "never fake results."
Everything below is a real, deliberate scope or modeling choice, made
explicit so nobody mistakes a simplification for a measured fact.

## WHAT IS MEASURED

- Every currency figure comes from `tariff/bill.py:BillEngine`, computed
  from a realized `import_kw`/`export_kw` series and a validated tariff
  object. No other module emits a currency number.
- Forecast calibration (pinball loss, coverage, reliability) is computed
  against held-out data the model never trained on
  (`forecasting/calibration.py`).
- Safety-shield interventions are logged per timestep
  (`shield_interventions` on `SimulationSeries`) — you can see exactly
  when and why an action was clipped, for any run.

## WHAT IS SIMULATED

- A single-zone RC thermal model per building (`simulation/thermal.py`),
  a linear battery/thermal-storage/DHW/EV model with round-trip losses
  (`simulation/storage.py`), and an electrical balance
  (`simulation/electrical.py`). This is a digital twin, not a measurement
  of any real building.
- Rolling-horizon MPC is solved as a continuous LP (PuLP + CBC), re-solved
  every timestep. No binary variables are used anywhere in the optimizer —
  simultaneous charge/discharge is discouraged by cost, not forbidden by
  a mutual-exclusion constraint (the safety shield does forbid it as a
  final defense, see `optimization/safety_shield.py`).

## WHAT IS ASSUMED (SYNTHETIC / ASSUMED, not measured)

- **Weather and load profiles are fully synthetic**
  (`core/weather.py`, `core/building.py`). No real building meter data
  (e.g. Building Data Genome Project 2) is used in this build, despite
  the sourced execution plans recommending it — this was a deliberate
  time-tradeoff for a single-session build. The synthetic generator uses
  seeded seasonal/diurnal weather and archetype-shaped occupancy/load
  curves, which is exactly the fallback the sourced plans themselves
  authorize ("hand pick plausible values and say they are hand picked").
- **RC thermal parameters (R, C) per building type are hand-picked,
  not fit from data** (`schemas/building.py:ARCHETYPES`). The UI and
  reports should be read as "PARAMETERS SYNTHETIC / ASSUMED", never
  "PARAMETERS ESTIMATED FROM DATA."
- **HVAC is cooling-only.** `optimization/objective.py:HVAC_COP` converts
  electrical draw into heat REMOVAL only; there is no heating mode. In a
  cold-weather stress case the safety shield can only turn HVAC off, not
  turn on heating — an ambient-driven hard-bound breach in that situation
  is a genuine modeling gap, not a controller failure (see
  `optimization/safety_shield.py` docstring).
- **The tariff (`configs/tariffs/demo.json`) is an illustrative Indian
  commercial ToU/demand-charge structure inspired by publicly reported
  patterns (peak/off-peak multipliers, ₹/kVA demand charges), NOT a
  verbatim transcription of any specific state's published tariff order.**
  Swapping in a real, cited order (e.g. a specific TNERC/MSEDCL order) is
  a one-file change (`tariff/compiler.py` + a new JSON) and would not
  require touching the controller — this portability claim is tested in
  `tests/test_tariff.py`.
- **Building site coordinates for the Energy Opportunity Graph are
  synthetic**, deterministically derived from the building id
  (`graph/features.py:synthetic_coordinates`) — there is no real GIS data.
  Distance-based feasibility gating is real code, operating on fake
  distances.
- **Assumed power factor (0.95)** is used to convert kW to kVA for demand
  charges and power-factor penalties, since no reactive-power model exists
  in the digital twin.

## WHAT IS LEARNED

- **Quantile forecasting (`forecasting/predict.py:ForecastEngine`)** —
  LightGBM quantile regression (sklearn `GradientBoostingRegressor` as
  documented fallback) trained on an independently-generated synthetic
  history, evaluated on a held-out split. This is the model behind the
  Forecast Report (pinball loss, coverage, reliability diagram).
- **The MPC's own operational forecast (`forecasting/path_forecast.py`)**
  is a DIFFERENT, cheaper model (seasonal-naive point forecast + Gaussian
  band from empirically backtested residual std) used only to feed the
  rolling-horizon LP at every step of a simulation. It is not the model
  evaluated in the Forecast Report. This split exists because training
  7-quantile gradient-boosted models at every one of 32 horizon steps,
  every timestep, for every building, in a rolling simulation, is not
  compute-tractable in a hackathon setting. Both are real, computed
  models; they are simply different families for different jobs.
- **RL (PPO via stable-baselines3)** is trained on a dedicated longer
  synthetic world (`configs/worlds/rl_train.json`, 20 days) and is
  intentionally a LIGHT training run, not a tuned, competitive policy.
  This is a deliberate choice, not an oversight: published evidence from
  the CityLearn 2021–2023 competitions found that no top-performing team
  used RL for scheduling — classical MPC/heuristics won, reportedly
  because no competition (or hackathon) has a rich enough training
  environment for RL to out-learn a well-specified optimizer. AETHERGRID
  trains RL anyway specifically to TEST that finding here (hypothesis
  H3), not to assume it will win. If `aethergrid/models/ppo_*.zip` is
  missing or fails to load, `rl`/`safe_rl` controllers fall back to
  `rl/policies.py:adaptive_fallback_policy`, a deterministic
  uncertainty-aware heuristic — this fallback is recorded in
  `run_metadata.json`, never silent.
- 'rl' and 'safe_rl' currently share the SAME trained policy and reward
  function; they differ only in whether the Level-2 coordination signal
  is exposed to the controller. Separately tuning two reward functions
  to make 'safe_rl' outperform 'rl' was judged not worth the additional
  training time relative to what it would prove.

## WHAT IS OPTIMIZED

- Per-building rolling-horizon MPC over HVAC, battery, DHW, EV and
  thermal-storage setpoints (`optimization/mpc.py`), with configurable
  objective weights (`schemas/experiment.py:ObjectiveWeights`).
- Chance-constrained control substitutes a conservative forecast quantile
  (q95 for demand, q05 for solar, configurable via `risk_level`) instead
  of the mean forecast — this is the single mechanism under test for H1.

## WHAT IS NOT MODELED

- **No real physical energy transfer between buildings**, ever. Only
  `thermal_match` edges represent a claimed physical mechanism (short-run
  heat exchange), and even then the transferred-heat estimate in
  `synergy/counterfactual.py` is a simplified proportional model, not a
  simulated heat-exchanger. All other opportunity types
  (`flexibility_match`, `storage_coordination`, `solar_load_match`,
  `peak_complementarity`) are billing/scheduling coordination only —
  see `graph/compatibility.py:OPPORTUNITY_MECHANISM`.
- **No multi-agent RL.** The RL environment (`rl/env.py`) is single-agent,
  single-building, per PART L's own instruction not to attempt
  multi-agent RL until the single-agent case works.
- **No GNN.** The Energy Opportunity Graph uses NetworkX + engineered
  features, not a learned graph neural network (documented Tier-B
  fallback).
- **No LLM anywhere in the money path.** No LLM tariff-order extraction,
  no LLM-generated decision explanations — `ui/replay.py:decision_explanation`
  builds its reasons directly from simulation state.
- **No reactive-power / three-phase electrical model.** Power factor is a
  single assumed scalar, not derived from any load's actual reactive
  behavior.

## Annualized economics: a specific, important caveat

The default world configs run **2-day** simulations for tractability.
`synergy/counterfactual.py` annualizes a 2-day sample by a flat
`365 / duration_days` multiplier. This is a **naive linear extrapolation**
that does NOT account for seasonal variation, weekday/weekend mix beyond
what 2 days happen to capture, or tariff changes over a year. Every
counterfactual result's `recommendation` string carries this caveat
verbatim. Treat annualized ₹ figures as **indicative order-of-magnitude**,
not validated annual forecasts — a defensible claim would require running
the same pipeline over a much longer window (weeks to a year), which is a
straightforward but compute-heavy extension (`world.duration_days` in the
JSON config is the only thing that needs to change).

## Ablation coverage

`evaluation/ablation.py` implements FULL vs FULL-minus-X for axes that are
cleanly separable at the single-building dispatch level: uncertainty
(mean vs quantile forecast), tariff-awareness (flat vs ToU rate), the
safety shield, and the resilience-reserve objective term. It does **not**
implement "minus EnergyDNA" or "minus graph coordination" as ablations of
the society-world bill, because those components act on building-PAIR
discovery decisions, not single-building dispatch — their contribution is
instead demonstrated directly, by comparing the connection world's
synergy-graph output against what independent (society-world) optimization
would have found.

## Resilience metric nuance (colony/outage mode)

During a true `grid_outage` event, `simulation/colony.py` forces shared
import capacity to exactly 0 for every building, regardless of
criticality — this matches PART Z ("grid import = 0") and means the
Level-2 criticality-based rationing mechanism only has an effect when
capacity is POSITIVE but insufficient, not during a full blackout. During
an actual outage, which building degrades most gracefully is therefore
driven by each building's own on-site battery/thermal-storage capacity
relative to its base load, not by the coordinator picking favorites. In
the default `colony.json` archetypes, the hospital's absolute load (~340kW
mean) is large relative to its battery power rating (150kW), so it can
show WORSE short-term outage service than a lower-criticality,
lower-absolute-load building — this is a genuine backup-sizing finding
("a critical facility needs commensurate on-site backup," not just a
priority flag), surfaced honestly rather than hidden.
