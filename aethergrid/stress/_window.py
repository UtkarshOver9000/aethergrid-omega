"""Shared helper: boolean activation mask for an event's [start, start+duration) window."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aethergrid.schemas.event import EventSpec


def active_mask(index: pd.DatetimeIndex, event: EventSpec) -> np.ndarray:
    end = event.start + pd.Timedelta(hours=event.duration_hours)
    return np.asarray((index >= event.start) & (index < end))


def extra(event: EventSpec, key: str, default):
    return (event.model_extra or {}).get(key, default)
