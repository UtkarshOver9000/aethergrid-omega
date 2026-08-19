"""SOLAR_FAILURE: PV generation drops to zero (inverter fault, panel
soiling event, etc.) for the event window. Consumed as
`solar_failure_mask` by simulate_building_series."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aethergrid.schemas.event import EventSpec
from aethergrid.stress._window import active_mask


def solar_failure_mask(index: pd.DatetimeIndex, event: EventSpec) -> np.ndarray:
    assert event.type == "solar_failure"
    return active_mask(index, event)
