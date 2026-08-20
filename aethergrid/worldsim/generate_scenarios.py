"""Generates the 4 representative-day scenario JSON files into viz/data/.
Run: python -m aethergrid.worldsim.generate_scenarios"""
from __future__ import annotations

import time

from aethergrid.worldsim.engine.society import simulate_society
from aethergrid.worldsim.export.jsonio import export_society_json
from aethergrid.worldsim.schemas.events import WorldEvent
from aethergrid.worldsim.schemas.scenario import SocietyScenario, WorldSimScenario
from aethergrid.worldsim.schemas.transformer import TransformerSpec

RATING = 220.0


def _run(name: str, events: list[WorldEvent], seed: int, ev_penetration: float = 0.45,
         rating: float = RATING, outage: bool = False):
    scenario = WorldSimScenario(name=name, scenario=name, date="2026-07-15", seed=seed,
                                 duration_hours=24, events=events)
    society = SocietyScenario(id="s0", n_households=60, has_workspace=True,
                               ev_penetration=ev_penetration, solar_penetration=0.45,
                               transformer=TransformerSpec(rating_kva=rating))
    t0 = time.time()
    result = simulate_society(scenario, society, base_seed=seed)
    data = export_society_json(scenario, society, result, f"viz/data/{name}.json")
    from collections import Counter
    print(f"{name}: {round(time.time()-t0,2)}s, states={Counter(result.transformer_state)}, "
          f"kva peak={round(result.transformer_kva.max(),1)}")
    return data


if __name__ == "__main__":
    _run("normal", events=[], seed=42, ev_penetration=0.4, rating=230)

    _run("heatwave", events=[
        WorldEvent(id="hw1", type="heatwave", start_min=0, duration_min=8 * 60, severity=1.0, temperature_delta=7.0),
    ], seed=43, ev_penetration=0.4, rating=170)

    _run("high_ev", events=[
        WorldEvent(id="ev1", type="high_ev_arrival", start_min=17 * 60, duration_min=3 * 60, severity=1.0),
    ], seed=44, ev_penetration=0.75, rating=160)

    _run("outage", events=[
        WorldEvent(id="out1", type="grid_outage", start_min=13 * 60, duration_min=2 * 60, severity=1.0),
    ], seed=45, ev_penetration=0.4, rating=210)
