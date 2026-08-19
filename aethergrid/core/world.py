"""World: the fully-reproducible container built from a JSON world spec.
`World.load(path)` is the one entry point every experiment/controller/UI
starts from."""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from aethergrid.core.building import Building
from aethergrid.core.resources import resources_from_archetype
from aethergrid.core.weather import generate_weather
from aethergrid.schemas.world import WorldSpec
from aethergrid.tariff.compiler import compile_tariff


@dataclass
class World:
    spec: WorldSpec
    index: pd.DatetimeIndex
    dt_hours: float
    weather: pd.DataFrame
    buildings: dict[str, Building]
    tariff: "aethergrid.tariff.schema.CompiledTariff"  # noqa: F821 (string import to avoid cycle)
    grid_capacity_kw: float | None

    @classmethod
    def load(cls, world_path: str, tariff_path: str | None = None) -> "World":
        spec = WorldSpec.from_json_file(world_path)
        return cls.from_spec(spec, tariff_path=tariff_path)

    @classmethod
    def from_spec(cls, spec: WorldSpec, tariff_path: str | None = None) -> "World":
        dt_hours = spec.world.timestep_minutes / 60.0
        n_steps = int(spec.world.duration_days * 24 / dt_hours)
        start = pd.Timestamp(spec.world.start_date)

        weather = generate_weather(start, n_steps, spec.world.timestep_minutes, seed=spec.world.seed)
        for event in spec.events:
            if event.type == "heatwave":
                from aethergrid.stress.heatwave import apply as apply_heatwave_event
                weather = apply_heatwave_event(weather, event)

        if tariff_path is None:
            tariff_path = f"aethergrid/configs/tariffs/{spec.tariff.id}.json"
        with open(tariff_path, "r", encoding="utf-8") as f:
            tariff_json = json.load(f)
        tariff = compile_tariff(tariff_json)

        buildings: dict[str, Building] = {}
        for i, b in enumerate(spec.buildings):
            arch = b.resolved_archetype()
            res = resources_from_archetype(b.id, arch, spec.resources)
            buildings[b.id] = Building(
                building_id=b.id, archetype=arch, resources=res,
                criticality=b.resolved_criticality(), weather=weather,
                seed=spec.world.seed * 1000 + i,
            )

        return cls(
            spec=spec, index=weather.index, dt_hours=dt_hours, weather=weather,
            buildings=buildings, tariff=tariff,
            grid_capacity_kw=spec.resources.grid_capacity_kw,
        )

    @property
    def n_steps(self) -> int:
        return len(self.index)

    @property
    def building_ids(self) -> list[str]:
        return list(self.buildings.keys())

    def outdoor_temp_at(self, t: int) -> float:
        return float(self.weather["temp_c"].iloc[t])

    def reset_states(self) -> None:
        """Reset every building to its initial state (for re-running the
        same world under a different controller with an identical start
        condition -- required for counterfactual/baseline comparisons)."""
        for b in self.buildings.values():
            b.state = b._init_state()
