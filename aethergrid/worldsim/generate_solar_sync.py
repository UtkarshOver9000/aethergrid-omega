"""Generates the three solar-sync paired datasets used by the world sim's
Solar tab. "Sync ON" bundles two real behaviours together: EV charging
retimed toward daylight hours (household.py's enable_solar_sync), and a
big shared community solar station (60 kWp -- roughly 15-20x a single
house's rooftop capacity) whose output offsets aggregate society demand
directly. The existing whatif_ev*_ai.json files (curtailment on, no sync,
no station) are the real "before" baseline for comparison -- not
regenerated here, reused as-is.

Run: python -m aethergrid.worldsim.generate_solar_sync"""
from __future__ import annotations

import time
from collections import Counter

from aethergrid.worldsim.engine.society import simulate_society
from aethergrid.worldsim.export.jsonio import export_society_json
from aethergrid.worldsim.schemas.scenario import SocietyScenario, WorldSimScenario
from aethergrid.worldsim.schemas.transformer import TransformerSpec

RATING = 195.0                 # matches generate_whatif.py (recalibrated post cold-start fix)
COMMUNITY_SOLAR_KWP = 60.0      # the "big station" -- ~15-20x one house's rooftop array
EV_LEVELS = [20, 40, 75]


def _run(ev_pct: int):
    name = f"whatif_ev{ev_pct}_ai_solarsync"
    scenario = WorldSimScenario(name=name, scenario=name, date="2026-07-15", seed=301,
                                 duration_hours=24, events=[])
    society = SocietyScenario(id="s0", n_households=60, has_workspace=True,
                               ev_penetration=ev_pct / 100, solar_penetration=0.45,
                               transformer=TransformerSpec(rating_kva=RATING))
    t0 = time.time()
    result = simulate_society(scenario, society, base_seed=301, enable_curtailment=True,
                               enable_solar_sync=True, community_solar_kwp=COMMUNITY_SOLAR_KWP)
    export_society_json(scenario, society, result, f"viz/data/{name}.json")
    states = Counter(result.transformer_state)
    print(f"{name}: {round(time.time()-t0,2)}s peak={round(result.transformer_kva.max(),1)} "
          f"frac={round(result.transformer_kva.max()/RATING,2)} "
          f"station_peak_kw={round(result.community_solar_kw.max(),1)} states={dict(states)}")


if __name__ == "__main__":
    for ev in EV_LEVELS:
        _run(ev)
