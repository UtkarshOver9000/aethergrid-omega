"""Chance-constrained forecast substitution (PART J). Converts a per-step
quantile path forecast into the single deterministic array the LP actually
sees, according to the requested risk posture:

  MEAN     : use q50 for both base load and solar (mean-forecast control)
  QUANTILE : use the conservative tail -- q(1-risk) for base load (defend
             against higher-than-median demand), q(risk) for solar (defend
             against lower-than-median generation)

This is the one place H1 ("uncertainty-aware forecasting reduces costly
peak-demand violations") is operationalized -- the two arms differ only in
which quantile they hand the identical optimizer, so any performance
difference is attributable to the uncertainty treatment, not the optimizer.
"""
from __future__ import annotations

from typing import Literal

import numpy as np

ForecastMode = Literal["mean", "quantile"]


def _nearest_quantile_key(qdict: dict[float, float], target: float) -> float:
    return min(qdict.keys(), key=lambda q: abs(q - target))


def build_horizon_arrays(
    base_load_path: dict[int, dict[float, float]],
    solar_path: dict[int, dict[float, float]],
    horizon: int,
    mode: ForecastMode,
    risk_level: float = 0.05,
) -> tuple[np.ndarray, np.ndarray]:
    base_q = 0.5 if mode == "mean" else min(0.95, 1 - risk_level)
    solar_q = 0.5 if mode == "mean" else max(0.05, risk_level)

    base_arr, solar_arr = [], []
    for h in range(1, horizon + 1):
        bq = base_load_path.get(h, base_load_path.get(max(base_load_path), {}))
        sq = solar_path.get(h, solar_path.get(max(solar_path), {}))
        base_arr.append(bq[_nearest_quantile_key(bq, base_q)] if bq else 0.0)
        solar_arr.append(sq[_nearest_quantile_key(sq, solar_q)] if sq else 0.0)
    return np.array(base_arr), np.array(solar_arr)
