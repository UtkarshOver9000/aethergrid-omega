from __future__ import annotations

import json
from pathlib import Path

import pytest

from aethergrid.core.world import World

TINY_WORLD = {
    "world": {"name": "pytest_tiny", "type": "society", "duration_days": 1,
               "timestep_minutes": 15, "seed": 1, "start_date": "2026-01-05"},
    "tariff": {"id": "demo"},
    "buildings": [{"id": "T01_office", "type": "office"}],
    "resources": {"solar": True, "battery": True, "thermal_storage": True, "ev": True, "dhw": True, "grid_capacity_kw": None},
    "events": [], "connections": [],
}

TINY_WORLD_2B = {
    **TINY_WORLD,
    "buildings": [{"id": "T01_office", "type": "office"}, {"id": "T02_retail", "type": "retail"}],
}


@pytest.fixture()
def tiny_world_path(tmp_path: Path) -> str:
    p = tmp_path / "tiny_world.json"
    p.write_text(json.dumps(TINY_WORLD))
    return str(p)


@pytest.fixture()
def tiny_world_2b_path(tmp_path: Path) -> str:
    p = tmp_path / "tiny_world_2b.json"
    p.write_text(json.dumps(TINY_WORLD_2B))
    return str(p)


@pytest.fixture()
def tiny_world(tiny_world_path) -> World:
    return World.load(tiny_world_path)
