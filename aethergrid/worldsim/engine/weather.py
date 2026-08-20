"""Environment for one simulation run: wraps (never duplicates)
aethergrid.core.weather.generate_weather for temp_c/ghi_wm2, and adds
what that module doesn't compute -- humidity, cloud_factor, and real
sun altitude/azimuth from standard solar-position astronomy (no external
dependency, pure numpy)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from aethergrid.core.weather import apply_heatwave, generate_weather


@dataclass
class Environment:
    index: pd.DatetimeIndex
    temp_c: np.ndarray
    humidity_pct: np.ndarray
    ghi_wm2: np.ndarray
    cloud_factor: np.ndarray
    sun_altitude: np.ndarray     # radians; <=0 means below horizon (night)
    sun_azimuth: np.ndarray      # radians from north, clockwise


def _sun_position(index: pd.DatetimeIndex, lat_deg: float, lon_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """Standard simplified solar-position formula (declination + hour
    angle). Accurate enough for a visual day/night cycle and irradiance
    shaping; not survey-grade astronomy."""
    lat = np.radians(lat_deg)
    day_of_year = index.dayofyear.values
    decl = np.radians(23.45 * np.sin(np.radians(360.0 / 365.0 * (284 + day_of_year))))

    # local solar time approximated as local clock time (timezone/lon correction
    # folded into a fixed offset so noon lands near local midday -- fine for a
    # synthetic demo world, not a real-site solar-yield calculation)
    hours = index.hour.values + index.minute.values / 60.0
    hour_angle = np.radians(15.0 * (hours - 12.0))

    sin_alt = np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(hour_angle)
    altitude = np.arcsin(np.clip(sin_alt, -1.0, 1.0))

    cos_az = (np.sin(decl) - np.sin(lat) * np.sin(altitude)) / np.clip(np.cos(lat) * np.cos(altitude), 1e-6, None)
    azimuth = np.arccos(np.clip(cos_az, -1.0, 1.0))
    azimuth = np.where(hour_angle > 0, 2 * np.pi - azimuth, azimuth)
    return altitude, azimuth


def build_environment(
    start: pd.Timestamp, n_steps: int, dt_minutes: int, seed: int,
    lat_deg: float, lon_deg: float,
    base_temp_c: float = 30.0, seasonal_amplitude_c: float = 5.0, diurnal_amplitude_c: float = 6.0,
) -> Environment:
    weather = generate_weather(start, n_steps, dt_minutes, seed=seed, base_temp_c=base_temp_c,
                                seasonal_amplitude_c=seasonal_amplitude_c, diurnal_amplitude_c=diurnal_amplitude_c)
    rng = np.random.default_rng(seed + 777)

    altitude, azimuth = _sun_position(weather.index, lat_deg, lon_deg)

    # cloud_factor: a slowly-varying AR(1) series in [0,1] (0 = clear, 1 = fully overcast)
    n = len(weather)
    cloud = np.zeros(n)
    cloud[0] = rng.uniform(0.05, 0.3)
    for i in range(1, n):
        cloud[i] = np.clip(0.9 * cloud[i - 1] + 0.1 * rng.uniform(0, 0.6), 0, 1)

    humidity = np.clip(45 + 25 * cloud + rng.normal(0, 3, size=n), 20, 95)

    return Environment(
        index=weather.index, temp_c=weather["temp_c"].values, humidity_pct=humidity,
        ghi_wm2=weather["ghi_wm2"].values, cloud_factor=cloud,
        sun_altitude=altitude, sun_azimuth=azimuth,
    )


def apply_heatwave_to_environment(env: Environment, start: pd.Timestamp, duration_hours: float, temperature_delta: float) -> Environment:
    df = pd.DataFrame({"temp_c": env.temp_c, "ghi_wm2": env.ghi_wm2}, index=env.index)
    df = apply_heatwave(df, start, duration_hours, temperature_delta)
    env.temp_c = df["temp_c"].values
    return env


def apply_cloud_cover(env: Environment, start: pd.Timestamp, duration_hours: float, severity: float) -> Environment:
    end = start + pd.Timedelta(hours=duration_hours)
    mask = (env.index >= start) & (env.index < end)
    env.cloud_factor = np.where(mask, np.clip(env.cloud_factor + severity, 0, 1), env.cloud_factor)
    return env
