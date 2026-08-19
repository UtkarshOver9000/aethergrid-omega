"""DEMAND_SPIKE: an unplanned extra load added on top of the building's
normal exogenous base load (e.g. equipment surge, unexpected occupancy).
Consumed as `demand_spike_addon_kw` by simulate_building_series."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aethergrid.schemas.event import EventSpec
from aethergrid.stress._window import active_mask, extra


def addon_kw(index: pd.DatetimeIndex, event: EventSpec, building_peak_kw: float) -> np.ndarray:
    assert event.type == "demand_spike"
    mask = active_mask(index, event)
    magnitude_kw = extra(event, "magnitude_kw", None)
    if magnitude_kw is None:
        magnitude_kw = building_peak_kw * extra(event, "magnitude_frac_of_peak", 0.4) * event.severity
    return mask.astype(float) * float(magnitude_kw)
