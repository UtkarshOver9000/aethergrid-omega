"""CONNECTION_FAILURE: a previously RECOMMENDED/active building-to-building
coordination link goes down for the event window (comms/metering fault).
Consumed by the connection-world orchestration to zero out the
coordination price signal during the window, forcing each building back to
independent (RUN-A-equivalent) operation -- this is the "graceful
degradation" story for Level-3 coordination."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aethergrid.schemas.event import EventSpec
from aethergrid.stress._window import active_mask


def failure_mask(index: pd.DatetimeIndex, event: EventSpec) -> np.ndarray:
    assert event.type == "connection_failure"
    return active_mask(index, event)


def apply_to_coordination_price(price: np.ndarray, index: pd.DatetimeIndex, event: EventSpec) -> np.ndarray:
    mask = failure_mask(index, event)
    out = price.copy()
    out[mask] = 0.0
    return out
