"""Generates the what-if grid used by the world sim's live AI Coordinator
toggle: one fixed transformer rating (280 kVA, chosen by calibration probe
so the grid genuinely spans NORMAL through BREACH), three EV-penetration
levels, each run twice -- once with the engine's real curtailment logic on,
once with it off -- so the toggle shows two real simulation outputs, not a
fabricated before/after.

The heatwave axis originally planned was dropped after calibration showed
it makes no measurable difference to peak load at any EV level in this
dataset -- shipping a slider that visibly does nothing would be dishonest.

Run: python -m aethergrid.worldsim.generate_whatif"""
from __future__ import annotations

import time
from collections import Counter

from aethergrid.worldsim.engine.society import simulate_society
from aethergrid.worldsim.export.jsonio import export_society_json
from aethergrid.worldsim.schemas.scenario import SocietyScenario, WorldSimScenario
from aethergrid.worldsim.schemas.transformer import TransformerSpec

RATING = 195.0                  # recalibrated after the cold-start fix lowered peaks; probe showed 280 left the AI nothing to do
EV_LEVELS = [20, 40, 75]


def _run(ev_pct: int, enable_curtailment: bool):
    tag = "ai" if enable_curtailment else "noai"
    name = f"whatif_ev{ev_pct}_{tag}"
    scenario = WorldSimScenario(name=name, scenario=name, date="2026-07-15", seed=301,
                                 duration_hours=24, events=[])
    society = SocietyScenario(id="s0", n_households=60, has_workspace=True,
                               ev_penetration=ev_pct / 100, solar_penetration=0.45,
                               transformer=TransformerSpec(rating_kva=RATING))
    t0 = time.time()
    result = simulate_society(scenario, society, base_seed=301, enable_curtailment=enable_curtailment)
    export_society_json(scenario, society, result, f"viz/data/{name}.json")
    states = Counter(result.transformer_state)
    print(f"{name}: {round(time.time()-t0,2)}s peak={round(result.transformer_kva.max(),1)} "
          f"frac={round(result.transformer_kva.max()/RATING,2)} states={dict(states)}")


if __name__ == "__main__":
    for ev in EV_LEVELS:
        _run(ev, enable_curtailment=True)
        _run(ev, enable_curtailment=False)
