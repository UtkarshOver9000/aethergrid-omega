"""Feature engineering shared by all forecast targets (base load, solar,
thermal/weather). Compact by design (PART G): one feature builder reused
across targets and horizons instead of bespoke pipelines per model."""
from __future__ import annotations

import numpy as np
import pandas as pd

STEPS_PER_DAY_DEFAULT = 96  # 15-minute steps


def make_feature_frame(
    df: pd.DataFrame, target_col: str, steps_per_day: int = STEPS_PER_DAY_DEFAULT,
) -> pd.DataFrame:
    """df must be indexed by a DatetimeIndex and contain `target_col` plus
    any of [temp_c, ghi_wm2/solar_kw, occupancy_frac] as available context
    columns. Returns a feature frame aligned to df.index (NaN rows from
    lags are left in -- caller drops them after adding the horizon target)."""
    out = pd.DataFrame(index=df.index)
    y = df[target_col]

    for lag in (1, 2, 4, steps_per_day):
        out[f"lag_{lag}"] = y.shift(lag)
    out["roll_mean_4"] = y.shift(1).rolling(4).mean()
    out["roll_std_4"] = y.shift(1).rolling(4).std()
    out["roll_mean_24"] = y.shift(1).rolling(24).mean()
    out["roll_max_24"] = y.shift(1).rolling(24).max()
    out["recent_ramp"] = y.shift(1) - y.shift(2)
    out["recent_peak"] = y.shift(1).rolling(steps_per_day).max()

    hours = out.index.hour + out.index.minute / 60.0
    out["hour_sin"] = np.sin(2 * np.pi * hours / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hours / 24)
    out["dow_sin"] = np.sin(2 * np.pi * out.index.dayofweek / 7)
    out["dow_cos"] = np.cos(2 * np.pi * out.index.dayofweek / 7)
    out["month_sin"] = np.sin(2 * np.pi * out.index.month / 12)
    out["month_cos"] = np.cos(2 * np.pi * out.index.month / 12)
    doy = out.index.dayofyear
    out["season_sin"] = np.sin(2 * np.pi * doy / 365)
    out["season_cos"] = np.cos(2 * np.pi * doy / 365)
    out["is_weekend"] = (out.index.dayofweek >= 5).astype(float)

    if "temp_c" in df.columns:
        out["temp_c"] = df["temp_c"]
        out["temp_forecast_proxy"] = df["temp_c"].shift(-1).fillna(df["temp_c"])  # crude NWP-forecast stand-in
    if "ghi_wm2" in df.columns:
        out["ghi_wm2"] = df["ghi_wm2"]
    if "occupancy_frac" in df.columns:
        out["occupancy_frac"] = df["occupancy_frac"]

    return out


def make_horizon_target(y: pd.Series, horizon_steps: int) -> pd.Series:
    return y.shift(-horizon_steps)
