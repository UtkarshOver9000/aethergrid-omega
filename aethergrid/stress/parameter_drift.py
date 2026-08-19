"""PARAMETER_DRIFT: physical asset parameters degrade over the run (e.g.
battery round-trip efficiency fading, thermal envelope degrading). This
mutates a BuildingResources snapshot -- callers substitute it for the
affected window so the digital twin genuinely operates on drifted physics,
not just a cosmetic label. Degraded insulation means MORE heat leakage,
i.e. LOWER thermal resistance R -- not higher."""
from __future__ import annotations

from dataclasses import replace

from aethergrid.core.resources import BuildingResources
from aethergrid.schemas.event import EventSpec
from aethergrid.stress._window import extra


def drift_resources(resources: BuildingResources, event: EventSpec) -> BuildingResources:
    assert event.type == "parameter_drift"
    eff_drop = extra(event, "battery_efficiency_drop_pct", 8.0) / 100.0 * event.severity
    r_drift = extra(event, "thermal_R_drift_pct", 10.0) / 100.0 * event.severity
    return replace(
        resources,
        battery_round_trip_eff=max(0.5, resources.battery_round_trip_eff * (1 - eff_drop)),
        thermal_R=max(0.1, resources.thermal_R * (1 - r_drift)),
    )
