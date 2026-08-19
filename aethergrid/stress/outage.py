"""GRID_OUTAGE: grid import forced to 0 for the event window (PART Z
resilience mode). Consumed directly as `outage_mask` by
core/timestep.py:simulate_building_series."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aethergrid.schemas.event import EventSpec
from aethergrid.stress._window import active_mask


def outage_mask(index: pd.DatetimeIndex, event: EventSpec) -> np.ndarray:
    assert event.type == "grid_outage"
    return active_mask(index, event)
