"""Per-household occupant-activity trace. This is the emergence point:
electrical demand downstream is a CONSEQUENCE of this trace (appliances
only draw when triggered by occupancy), not a fixed curve attached to a
house. Each house gets its own seeded AR(1) noise on top of its
archetype's base hourly presence probability, so households of the same
archetype are never synchronized (realism check: "houses do not all peak
simultaneously")."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from aethergrid.worldsim.schemas.household import HouseholdArchetype


@dataclass
class OccupancyTrace:
    occupancy_frac: np.ndarray   # continuous presence intensity in [0,1] per tick
    occupant_count: np.ndarray   # int occupants present per tick
    cooking: np.ndarray          # bool: cooking-intensity window, gated by presence
    is_night: np.ndarray         # bool: typical sleep hours


def generate_occupancy_trace(archetype: HouseholdArchetype, index: pd.DatetimeIndex, seed: int,
                              occupancy_multiplier: np.ndarray | None = None) -> OccupancyTrace:
    """`occupancy_multiplier`: optional per-tick multiplier (e.g. > 1
    during a festival event, < 1 during a holiday-away pattern) applied
    on top of the archetype's own base curve -- lets events genuinely
    shift occupancy rather than only touching environment fields."""
    rng = np.random.default_rng(seed)
    hours = index.hour.values + index.minute.values / 60.0
    is_weekend = index.dayofweek.values >= 5

    # Per-household phase shift (own arrival/departure timing, up to ~90min
    # earlier/later than the archetype's nominal curve) via smooth cyclic
    # interpolation -- this is what keeps households of the SAME archetype
    # from all peaking at the identical minute (realism check: coincidence
    # factor should land around 0.4-0.6, not ~1.0).
    phase_shift_h = rng.uniform(-2.2, 2.2)
    curve = np.array(archetype.occupancy.home_prob_by_hour + [archetype.occupancy.home_prob_by_hour[0]])
    hour_grid = np.arange(25)
    shifted_hours = np.mod(hours - phase_shift_h, 24.0)
    base_prob = np.interp(shifted_hours, hour_grid, curve)
    weekend_scale = np.where(is_weekend, archetype.occupancy.weekend_multiplier, 1.0)
    base_prob = np.clip(base_prob * weekend_scale, 0, 1)

    n = len(index)
    noise = np.zeros(n)
    noise[0] = rng.normal(0, 0.12)
    for i in range(1, n):
        noise[i] = 0.8 * noise[i - 1] + 0.2 * rng.normal(0, 0.16)
    occupancy_frac = np.clip(base_prob + noise, 0, 1)
    if occupancy_multiplier is not None:
        occupancy_frac = np.clip(occupancy_frac * occupancy_multiplier, 0, 1)

    occupant_draw = rng.normal(archetype.occupancy.mean_occupant_count, archetype.occupancy.occupant_count_std, size=n)
    occupant_count = np.clip(np.round(occupant_draw * occupancy_frac), 0, None).astype(int)

    cooking = (((shifted_hours >= 7) & (shifted_hours < 9)) | ((shifted_hours >= 19) & (shifted_hours < 21))) & (occupancy_frac > 0.3)
    is_night = (shifted_hours >= 23) | (shifted_hours < 6)

    return OccupancyTrace(occupancy_frac, occupant_count, cooking, is_night)
