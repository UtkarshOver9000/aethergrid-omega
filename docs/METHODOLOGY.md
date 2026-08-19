# METHODOLOGY

## Research question

Can a hierarchical, uncertainty-aware, safety-constrained controller
coordinate flexible loads across heterogeneous buildings more effectively
than independent building optimization, while remaining economically,
thermally and operationally feasible under distribution shift?

## The five hypotheses, and how each is actually tested

**H1 — Uncertainty-aware forecasting reduces costly peak-demand violations
relative to mean-only forecasting.**
Tested by `mean_mpc` vs `quantile_mpc` in `evaluation/baselines.py`: both
controllers run the IDENTICAL LP (`optimization/mpc.py`) with the IDENTICAL
objective weights; the only difference is which forecast quantile
(`optimization/chance_constraints.py`) is substituted for the demand/solar
forecast before solving. Any performance delta is attributable to the
uncertainty treatment alone.

**H2 — Hierarchical coordination improves district-level performance
relative to independent building optimization.**
Tested by comparing the `society` world (buildings optimized independently)
against the `connection` world's counterfactual RUN B/C
(`synergy/counterfactual.py`) and against `colony` mode's shared-capacity
allocation (`simulation/colony.py`). H2 is falsifiable per candidate: the
economics gate (`synergy/economics.py`) can and does return `REJECTED`
when coordination doesn't pay for itself.

**H3 — Adaptive RL improves performance under distribution shift relative
to a static optimization policy.**
Tested by running `rl`/`safe_rl` against `quantile_mpc` across the stress
scenarios in `evaluation/robustness.py`. Given the evidence cited in
`docs/LIMITATIONS.md` (CityLearn 2021-2023: no top team used RL for
scheduling), the working expectation going in was that RL would NOT beat
MPC here — the point of running it is to check that expectation against
this specific environment, not to assume it.

**H4 — Cross-building synergy discovery can identify economically
promising coordination opportunities that independent optimization cannot
see.**
Tested by `graph/graph.py:build_energy_opportunity_graph` — the discovery
+ feasibility + economics pipeline surfaces candidates (and their
`RECOMMENDED`/`REJECTED` status with a numeric reason) that a
single-building optimizer, by construction, never even considers.

**H5 — A safety-constrained hybrid controller provides a better
cost/comfort/resilience trade-off than unconstrained RL.**
Tested by `evaluation/ablation.py`'s `FULL_minus_safety_shield` variant
(runs the LP-based controller with `apply_shield=False`) and by comparing
the RL controller's behavior with and without the mandatory shield in the
same ablation harness.

## Why classical MPC, not RL, is the primary controller

This is a deliberate architectural choice, not a default. Two independent
sourced planning documents for this exact problem statement
(`docs/` predecessors — see git history / project notes) both cite the
same evidence: across CityLearn 2021, 2022 and 2023 at NeurIPS, no
top-performing team used reinforcement learning for scheduling; winning
solutions used classical optimization, heuristics, and hierarchical
forecast+MPC composition. The stated reason is the absence of a training
environment rich enough for RL to out-learn a well-specified optimizer —
and a hackathon-scale synthetic environment has less of that richness than
the competition did. AETHERGRID therefore treats `quantile_mpc` (labeled
"HYBRID" in the dashboard) as the primary/recommended controller, and RL
as a secondary, explicitly-tested comparison arm (H3) — not the hero.

## The chance-constraint mechanism (the one line that matters)

Inside `optimization/chance_constraints.py:build_horizon_arrays`, mode
`"quantile"` substitutes `q(1 - risk_level)` for the base-load forecast
and `q(risk_level)` for the solar forecast, instead of `q50` (the mean
controller's choice). Everything downstream — the LP, the safety shield,
the physics — is identical between `mean_mpc` and `quantile_mpc`. If the
underlying quantile forecast is miscalibrated (see the Forecast Report's
`CALIBRATED`/`UNCALIBRATED` flag, `forecasting/calibration.py`), this
guarantee is only as good as that calibration — which is exactly the
argument the system is built to let a judge test directly, not something
asserted on a slide.

## Objective-weight calibration rationale

`schemas/experiment.py:ObjectiveWeights` — `energy_cost`,
`demand_charge_risk` and `connection_cost` are already currency-denominated
(₹/kWh, ₹/kVA, ₹/kWh), so a weight of 1.0 means "the LP sees the real
economic cost." `comfort_penalty`'s raw unit (°C of soft-band slack per
15-minute step) is NOT naturally currency-scaled; its default (80.0) was
chosen empirically so that correcting ~1°C of drift costs the LP roughly
what a typical HVAC step actually costs for a mid-size building
(₹60-150), instead of the initial default (2.0) under which the LP
treated comfort as essentially free and produced unrealistic (~70%
soft-band violation) drift. This is documented here because it is exactly
the kind of tuning decision that could look like "cooking the results" if
left unexplained — it isn't; it is a one-time unit-consistency fix,
applied identically to every controller and every experiment.

## Baselines (PART V, all eight)

`no_control`, `rule_based`, `mean_mpc`, `quantile_mpc`, `rl`, `safe_rl`,
`hierarchical_hybrid`, `oracle` — see `evaluation/baselines.py` and
`evaluation/oracle.py`. `hierarchical_hybrid` currently runs the same LP
as `quantile_mpc` at the single-building evaluation-table level (Level-2/3
coordination is demonstrated separately in `colony`/`connection` worlds,
not folded into the portfolio-wide society bill) — see
`docs/LIMITATIONS.md` for why.

## Measurement & verification discipline

Every experiment computes `savings_captured_fraction`
(`evaluation/metrics.py`) — the fraction of the Oracle-vs-baseline gap a
controller actually captured — specifically so "we improved the bill" and
"we captured most of the theoretically achievable improvement" are never
conflated on a results slide.
