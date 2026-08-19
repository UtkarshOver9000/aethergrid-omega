"""SENSOR_DROPOUT: the forecaster loses fresh readings for a window. We do
not pretend the controller still has good information -- instead we
degrade the path forecast it receives: the point forecast freezes at the
last known-good value and the uncertainty band widens (PART R: "show
controller operating using uncertainty/fallback")."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from aethergrid.schemas.event import EventSpec
from aethergrid.stress._window import active_mask, extra

PathForecastFn = Callable[[int, int], dict]


def dropout_mask(index: pd.DatetimeIndex, event: EventSpec) -> np.ndarray:
    assert event.type == "sensor_dropout"
    return active_mask(index, event)


def wrap_degraded_forecast(base_fn: PathForecastFn, dropout: np.ndarray, event: EventSpec) -> PathForecastFn:
    inflate = extra(event, "uncertainty_inflation", 2.5)

    def wrapped(t: int, H: int) -> dict:
        if t < len(dropout) and dropout[t]:
            last_good = t
            while last_good > 0 and dropout[last_good]:
                last_good -= 1
            base = base_fn(last_good, H)
        else:
            base = base_fn(t, H)
        if not (t < len(dropout) and dropout[t]):
            return base
        out = {}
        for h, qdict in base.items():
            point = qdict.get(0.5, sum(qdict.values()) / len(qdict))
            out[h] = {q: max(0.0, point + (v - point) * inflate) for q, v in qdict.items()}
        return out

    return wrapped
