"""Synthetic weather generator. No real historical weather data is available
in this environment, so outdoor temperature and solar irradiance are
generated from a seeded seasonal + diurnal model with noise. This is
SYNTHETIC data and is labeled as such everywhere it surfaces in the UI.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def generate_weather(
    start: pd.Timestamp,
    n_steps: int,
    dt_minutes: int,
    seed: int = 42,
    base_temp_c: float = 24.0,
    seasonal_amplitude_c: float = 6.0,
    diurnal_amplitude_c: float = 6.0,
    peak_ghi_wm2: float = 950.0,
) -> pd.DataFrame:
    """Return a DataFrame indexed by timestamp with columns
    [temp_c, ghi_wm2] at the requested resolution."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start=start, periods=n_steps, freq=f"{dt_minutes}min")
    hours = idx.hour + idx.minute / 60.0
    day_of_year = idx.dayofyear.values

    seasonal = seasonal_amplitude_c * np.sin(2 * np.pi * (day_of_year - 80) / 365.0)
    diurnal = diurnal_amplitude_c * np.sin(2 * np.pi * (hours - 9) / 24.0)
    noise = rng.normal(0, 0.6, size=n_steps)
    # AR(1) smoothing so noise doesn't look like white-noise jitter
    for i in range(1, n_steps):
        noise[i] = 0.85 * noise[i - 1] + 0.15 * noise[i]
    temp_c = base_temp_c + seasonal + diurnal + noise

    daylight = np.clip(np.sin(np.pi * (hours - 6) / 12.0), 0, None)
    cloud_factor = np.clip(1 - rng.beta(1.5, 5, size=n_steps), 0.15, 1.0)
    ghi = peak_ghi_wm2 * daylight * cloud_factor

    return pd.DataFrame({"temp_c": temp_c, "ghi_wm2": ghi}, index=idx)


def apply_heatwave(weather: pd.DataFrame, start, duration_hours: float, temperature_delta: float) -> pd.DataFrame:
    out = weather.copy()
    end = start + pd.Timedelta(hours=duration_hours)
    mask = (out.index >= start) & (out.index < end)
    out.loc[mask, "temp_c"] = out.loc[mask, "temp_c"] + temperature_delta
    return out
