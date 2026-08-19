"""Static explainer copy + tutorial preset definitions. Plain data/text --
no simulation logic. Every claim here is checked against docs/LIMITATIONS.md
so the in-app explanation never says more than the code actually does."""
from __future__ import annotations

from dataclasses import dataclass

SIDEBAR_MARKDOWN = """
### How this works
**World (JSON)** → **Building physics** (RC thermal + battery/DHW/EV/
thermal-storage) → **Forecast** (quantile ML, calibrated) →
**Chance-constrained MPC** (LP, re-solved every step) → **Safety
Shield** (hard-bound projection, always on) → **Digital Twin step**
→ **BillEngine** (the only place a currency number is computed).

---

**WORLD**
- `SOCIETY` — 8 heterogeneous buildings, each optimized on its own
- `COLONY` — 4 buildings sharing one constrained grid connection, with
  criticality-based rationing during an outage
- `CONNECTION` — discovers and economically tests coordination between
  building pairs (Energy Opportunity Graph)

**CONTROL**
- `BASELINE` — fixed-threshold heuristic, no forecasting
- `HYBRID` — the primary controller: an LP that substitutes a
  conservative forecast quantile (not the mean) before solving
- `SAFE RL` — a PPO policy (trained in-session), always passed through
  the same safety shield as every other controller

**STRESS LAB**
Injects a real, computed disturbance (heatwave, outage, sensor dropout,
demand spike, tariff change) into the exact same pipeline — nothing
about the controller changes, only the world it has to react to.

---

**Glossary**
- **Chance-constrained** — plans against a pessimistic forecast
  quantile (e.g. q95 demand) instead of the average, to avoid being
  surprised by a costly demand-charge peak.
- **Safety Shield** — the last line of defense: clips any proposed
  action to physical/comfort limits before it reaches the simulator.
- **Oracle** — a non-deployable reference controller given the *real*
  future (perfect foresight), used only to measure how much of the
  theoretically achievable saving a real controller actually captured.
- **Energy DNA** — an interpretable feature vector per building (peak
  timing, thermal inertia, flexible capacity, ...), not a black box.

Full technical writeup: `docs/METHODOLOGY.md` and `docs/LIMITATIONS.md`
in the repository.
"""

HOW_IT_WORKS_INTRO = """
AETHERGRID is a **closed-loop digital twin**, not a lookup table or a
canned demo. Every number on this page is computed, in this process, right
now, by the same code you can read in the repository. This page exists so
you don't have to take that on faith — here is exactly what happens
when you press a button above.
"""

PIPELINE_STEPS = [
    ("1. World (JSON)", "A scenario file defines buildings, a tariff, resource flags and a seed. Nothing about "
     "physics or economics is hardcoded — change the JSON, get a different (but still reproducible) world."),
    ("2. Building physics", "Each building gets a synthetic-but-realistic exogenous profile (base load, solar, "
     "occupancy) and a single-zone RC thermal model: T[t+1] = T[t] + dt/C · ((T_out−T)/R + Q_internal − Q_HVAC)."),
    ("3. Forecast", "A LightGBM quantile regressor predicts q05–q95 of future load/solar, evaluated for "
     "calibration on held-out data (see the Evidence tab)."),
    ("4. Chance-constrained MPC", "A rolling-horizon linear program (PuLP/CBC) re-solved every timestep. The "
     "HYBRID controller substitutes a conservative quantile for the forecast before solving — one line of "
     "code is the entire uncertainty guarantee."),
    ("5. Safety Shield", "Whatever the optimizer (or the RL policy) proposes gets clipped to hard physical/comfort "
     "bounds before it can reach the simulator. This runs unconditionally, for every controller."),
    ("6. Digital twin step", "The shielded action advances real physics: thermal state, battery/DHW/EV/thermal-"
     "storage SOC, and the resulting grid import/export."),
    ("7. BillEngine", "The ONLY module allowed to output a currency figure. Deterministic arithmetic against a "
     "validated tariff object — no ML or LLM ever touches a money decision."),
    ("8. Evaluation", "Every controller is compared against a perfect-foresight Oracle and a savings-captured "
     "fraction, not a bare percentage — see the Evidence tab for the actual numbers from the last full run."),
]

WHY_MPC_NOT_RL = """
Across the CityLearn 2021–2023 building-energy competitions, no
top-performing team used reinforcement learning for scheduling —
classical MPC and heuristics won, reportedly because no training
environment (a hackathon has even less of one) is rich enough for RL to
out-learn a well-specified optimizer. AETHERGRID trains a PPO policy
anyway (`SAFE RL`), specifically to test that finding here rather than
assume it — that's hypothesis H3. `HYBRID` (chance-constrained MPC)
remains the primary, recommended controller.
"""


@dataclass
class Tutorial:
    key: str
    title: str
    tag: str
    description: str
    world: str
    controller: str
    stress: str
    building_hint: str | None = None


TUTORIALS = [
    Tutorial(
        key="baseline_vs_hybrid", title="Baseline vs. chance-constrained MPC", tag="H1 · Uncertainty",
        description="See the bill and peak drop when the controller plans against a conservative demand forecast "
                     "instead of a fixed threshold heuristic. No stress, just the controller upgrade.",
        world="SOCIETY", controller="HYBRID (quantile chance-constrained MPC)", stress="NONE",
        building_hint="B01_office",
    ),
    Tutorial(
        key="heatwave", title="Heatwave stress test", tag="Stress Lab",
        description="Inject a sharp outdoor temperature rise and watch HVAC, comfort violations and cost react in "
                     "real time — same controller, harsher world.",
        world="SOCIETY", controller="HYBRID (quantile chance-constrained MPC)", stress="HEATWAVE",
        building_hint="B03_hospital",
    ),
    Tutorial(
        key="outage", title="Grid outage resilience", tag="H5 · Resilience",
        description="Force grid import to zero for 4 hours and see unserved load appear where the building's own "
                     "battery/thermal mass can't cover it — the honest limits of on-site backup.",
        world="SOCIETY", controller="HYBRID (quantile chance-constrained MPC)", stress="GRID OUTAGE",
        building_hint="B03_hospital",
    ),
    Tutorial(
        key="sensor_dropout", title="Sensor dropout — degrade gracefully", tag="H1 · Robustness",
        description="The forecaster loses fresh readings for 6 hours; its uncertainty band widens automatically "
                     "instead of pretending nothing changed.",
        world="SOCIETY", controller="HYBRID (quantile chance-constrained MPC)", stress="SENSOR DROPOUT",
        building_hint="B01_office",
    ),
    Tutorial(
        key="connection_graph", title="Discover a building-to-building opportunity", tag="H4 · Synergy",
        description="Switch to the CONNECTION world to see the Energy Opportunity Graph discover and technically "
                     "vet coordination candidates between buildings — nothing is assumed to physically connect.",
        world="CONNECTION", controller="HYBRID (quantile chance-constrained MPC)", stress="NONE",
        building_hint="N03_office",
    ),
]
