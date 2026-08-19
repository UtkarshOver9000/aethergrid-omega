"""FORECAST_BIAS: injects a systematic +X% bias into the forecaster's point
estimate without changing the true simulated physics -- this is exactly
the PART S experiment ("how expensive is being wrong?"): the controller
plans against a biased forecast while the digital twin still realizes the
true demand."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from aethergrid.schemas.event import EventSpec
from aethergrid.stress._window import active_mask, extra

PathForecastFn = Callable[[int, int], dict]


def wrap_biased_forecast(base_fn: PathForecastFn, index: pd.DatetimeIndex, event: EventSpec) -> PathForecastFn:
    mask = active_mask(index, event)
    bias_frac = extra(event, "bias_pct", 10.0) / 100.0

    def wrapped(t: int, H: int) -> dict:
        base = base_fn(t, H)
        if t >= len(mask) or not mask[t]:
            return base
        return {h: {q: v * (1 + bias_frac) for q, v in qdict.items()} for h, qdict in base.items()}

    return wrapped
