"""BUILDING_FAILURE: an equipment failure (HVAC/battery/DHW inverter trips
offline) for one targeted building over the event window. Consumed as
`building_failure_mask` by simulate_building_series, which forces the
relevant flexible-load actions to zero for the affected steps regardless
of what the controller proposed."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aethergrid.schemas.event import EventSpec
from aethergrid.stress._window import active_mask


def building_failure_mask(index: pd.DatetimeIndex, event: EventSpec, building_id: str) -> np.ndarray:
    assert event.type == "building_failure"
    if event.target_building_id is not None and event.target_building_id != building_id:
        return np.zeros(len(index), dtype=bool)
    return active_mask(index, event)
