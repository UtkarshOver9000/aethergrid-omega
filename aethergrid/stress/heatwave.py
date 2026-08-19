"""HEATWAVE event: raises outdoor temperature for a window (PART AB
example). Must be applied to the weather series BEFORE building exogenous
profiles are generated, since base-load weather-sensitivity and solar are
both derived from weather at Building construction time."""
from __future__ import annotations

import pandas as pd

from aethergrid.core.weather import apply_heatwave
from aethergrid.schemas.event import EventSpec


def apply(weather: pd.DataFrame, event: EventSpec) -> pd.DataFrame:
    delta = (event.model_extra or {}).get("temperature_delta", 6.0)
    return apply_heatwave(weather, event.start, event.duration_hours, float(delta) * event.severity)
