"""Generates two additional society datasets (viz/data/society_b.json,
viz/data/society_c.json) representing neighbouring societies on the same
feeder, for the colony-scale Grid Brain view. Same engine, same honesty
rules as generate_scenarios.py -- different seeds/params only.
Run: python -m aethergrid.worldsim.generate_colony"""
from __future__ import annotations

import time
from collections import Counter

from aethergrid.worldsim.engine.society import simulate_society
from aethergrid.worldsim.export.jsonio import export_society_json
from aethergrid.worldsim.schemas.events import WorldEvent
from aethergrid.worldsim.schemas.scenario import SocietyScenario, WorldSimScenario
from aethergrid.worldsim.schemas.transformer import TransformerSpec


def _run(name: str, out: str, events: list[WorldEvent], seed: int, ev_penetration: float,
         rating: float, n_households: int = 48):
    scenario = WorldSimScenario(name=name, scenario=name, date="2026-07-15", seed=seed,
                                 duration_hours=24, events=events)
    society = SocietyScenario(id=out, n_households=n_households, has_workspace=False,
                               ev_penetration=ev_penetration, solar_penetration=0.4,
                               transformer=TransformerSpec(rating_kva=rating))
    t0 = time.time()
    result = simulate_society(scenario, society, base_seed=seed)
    data = export_society_json(scenario, society, result, f"viz/data/{out}.json")
    print(f"{out}: {round(time.time()-t0,2)}s, states={Counter(result.transformer_state)}, "
          f"kva peak={round(result.transformer_kva.max(),1)}")
    return data


if __name__ == "__main__":
    # Society B: older, smaller transformer, moderate EV -- runs hotter than A
    _run("society_b", "society_b", events=[
        WorldEvent(id="hw1", type="heatwave", start_min=0, duration_min=8 * 60, severity=0.6, temperature_delta=4.0),
    ], seed=201, ev_penetration=0.5, rating=128, n_households=48)

    # Society C: newer, better-rated transformer, low EV -- has headroom
    _run("society_c", "society_c", events=[], seed=202, ev_penetration=0.25, rating=210, n_households=48)
