"""Fast per-step path forecaster used ONLY to feed the rolling-horizon MPC
at every step 1..H of its planning window.

This is deliberately a different (and much cheaper) model than the
LightGBM/GBR ForecastEngine in predict.py, which is the one evaluated in
the scientific Forecast Report (PART G/H: pinball loss, coverage,
reliability curve at the four required horizons). Training 7 quantiles x 32
per-step-ahead gradient-boosted models for every building, every timestep of
a rolling simulation is not compute-tractable in a hackathon setting, so the
MPC instead uses a seasonal-naive point forecast (today anchored, corrected
toward yesterday's same-hour value) with a Gaussian uncertainty band whose
per-step-ahead standard deviation is empirically estimated once from
backtested seasonal-naive residuals on the training history. This is a
real, computed, non-fabricated uncertainty estimate -- just a cheaper
family of model than the headline ML forecaster. Both are labeled
distinctly everywhere they surface (`method` field).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

QUANTILES = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
# scipy.stats.norm.ppf has meaningful per-call overhead; since QUANTILES is a
# fixed, small set, its z-scores are computed exactly once at import time and
# reused via vectorized numpy ops -- this is the dominant cost in a rolling
# simulation that calls forecast_path() at every timestep.
_Z_SCORES = np.array([norm.ppf(q) for q in QUANTILES])


@dataclass
class PathForecaster:
    steps_per_day: int
    max_horizon: int
    sigma_by_step: np.ndarray  # shape (max_horizon,), empirically fit
    method: str = "seasonal_naive_gaussian"

    @classmethod
    def fit(cls, history: np.ndarray, steps_per_day: int, max_horizon: int) -> "PathForecaster":
        n = len(history)
        resid_by_step: list[list[float]] = [[] for _ in range(max_horizon)]
        for t in range(steps_per_day, n - max_horizon):
            for h in range(1, max_horizon + 1):
                point = cls._point_forecast(history, t, h, steps_per_day)
                resid_by_step[h - 1].append(history[t + h] - point)
        sigma = np.array([
            float(np.std(r)) if len(r) > 3 else float(np.std(history)) * 0.1
            for r in resid_by_step
        ])
        # uncertainty should not shrink with horizon; enforce monotonic non-decrease
        sigma = np.maximum.accumulate(sigma)
        return cls(steps_per_day, max_horizon, sigma)

    @staticmethod
    def _point_forecast(history: np.ndarray, t: int, h: int, steps_per_day: int) -> float:
        target_idx = t + h
        yesterday_idx = target_idx - steps_per_day
        recent = history[t]
        if 0 <= yesterday_idx < len(history):
            seasonal = history[yesterday_idx]
            w = min(1.0, h / steps_per_day)  # near-term: trust persistence; far: trust seasonal
            return (1 - w) * recent + w * seasonal
        return recent

    def forecast_path(self, history: np.ndarray, t0: int, horizon: int, nonneg: bool = True) -> dict[int, dict[float, float]]:
        horizon = min(horizon, self.max_horizon)
        h_arr = np.arange(1, horizon + 1)
        target_idx = t0 + h_arr
        yesterday_idx = target_idx - self.steps_per_day
        recent = history[t0]
        valid = (yesterday_idx >= 0) & (yesterday_idx < len(history))
        seasonal = np.where(valid, history[np.clip(yesterday_idx, 0, len(history) - 1)], recent)
        w = np.minimum(1.0, h_arr / self.steps_per_day)
        w = np.where(valid, w, 0.0)
        point = (1 - w) * recent + w * seasonal          # shape (horizon,)
        sigma = self.sigma_by_step[:horizon]              # shape (horizon,)

        qmatrix = point[:, None] + sigma[:, None] * _Z_SCORES[None, :]  # (horizon, n_quantiles)
        if nonneg:
            qmatrix = np.maximum(qmatrix, 0.0)

        return {
            int(h): {q: float(qmatrix[i, j]) for j, q in enumerate(QUANTILES)}
            for i, h in enumerate(h_arr)
        }
