from __future__ import annotations

from aethergrid.optimization.constraints import hard_bounds_for


def test_hard_bounds_consistent_with_resources(tiny_world):
    b = tiny_world.buildings["T01_office"]
    bounds = hard_bounds_for(b.resources)
    assert bounds.t_min == b.resources.hard_t_min
    assert bounds.t_max == b.resources.hard_t_max
    assert bounds.battery_soc_min_kwh <= bounds.battery_soc_max_kwh
    assert bounds.hvac_max_kw == b.resources.hvac_capacity_kw
