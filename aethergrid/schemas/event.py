"""Pydantic schema for stress/adversarial events (PART AB). Events are JSON
objects that the stress engine (aethergrid/stress/*) applies to a running
simulation. `extra='allow'` lets each event type carry its own parameters
(temperature_delta, bias_pct, building_id, ...) without a combinatorial
explosion of subclasses."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

EventType = Literal[
    "heatwave",
    "sensor_dropout",
    "demand_spike",
    "solar_failure",
    "grid_outage",
    "tariff_change",
    "building_failure",
    "connection_failure",
    "forecast_bias",
    "parameter_drift",
]


class EventSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: EventType
    start: datetime
    duration_hours: float = 1.0
    target_building_id: str | None = None
    severity: float = 1.0
