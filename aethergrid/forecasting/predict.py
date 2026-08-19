"""ForecastEngine: trains + serves quantile forecasts at the four required
horizons (PART G: 1h, 4h, 8h, 24h). Training data is a longer synthetic
history generated independently of the operational world's realization, so
evaluating on the operational world is a genuine (if synthetic)
train/test split -- not the same draw the model memorized (PART X)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from aethergrid.core.building import Building
from aethergrid.core.resources import resources_from_archetype
from aethergrid.core.weather import generate_weather
from aethergrid.forecasting.calibration import CalibrationReport, build_calibration_report
from aethergrid.forecasting.features import make_feature_frame, make_horizon_target
from aethergrid.forecasting.quantile_models import QuantileModelSet, train_quantile_model
from aethergrid.schemas.building import ARCHETYPES

HORIZONS = {"1h": 4, "4h": 16, "8h": 32, "24h": 96}  # steps @ 15-min resolution


def context_frame(building: Building, weather: pd.DataFrame) -> pd.DataFrame:
    """Build the forecaster's input context frame for an operational-world
    building, given the world's weather DataFrame (same index)."""
    p = building.profile
    return pd.DataFrame({
        "base_load_kw": p.base_load_kw,
        "solar_kw": p.solar_potential_kw,
        "temp_c": weather["temp_c"].values,
        "ghi_wm2": weather["ghi_wm2"].values,
        "occupancy_frac": p.occupancy_frac,
    }, index=p.index)


def build_training_building(building_type: str, seed: int, n_days: int, dt_minutes: int,
                             start: str = "2025-10-01") -> tuple[Building, pd.DataFrame]:
    """Independent synthetic training history for one archetype -- a
    different weather draw / longer window than any operational world."""
    from aethergrid.schemas.world import ResourcesSpec
    arch = ARCHETYPES[building_type]
    res = resources_from_archetype(f"train_{building_type}", arch, ResourcesSpec())
    n_steps = int(n_days * 24 * 60 / dt_minutes)
    weather = generate_weather(pd.Timestamp(start), n_steps, dt_minutes, seed=seed)
    b = Building(f"train_{building_type}", arch, res, arch.default_criticality, weather, seed=seed)
    ctx = pd.DataFrame({
        "base_load_kw": b.profile.base_load_kw,
        "solar_kw": b.profile.solar_potential_kw,
        "temp_c": weather["temp_c"].values,
        "ghi_wm2": weather["ghi_wm2"].values,
        "occupancy_frac": b.profile.occupancy_frac,
    }, index=weather.index)
    return b, ctx


@dataclass
class ForecastBundle:
    target: str
    backend: str
    feature_names: list[str]
    models: dict[int, QuantileModelSet] = field(default_factory=dict)
    calibration: dict[int, CalibrationReport] = field(default_factory=dict)


class ForecastEngine:
    def __init__(self, target_col: str = "base_load_kw", steps_per_day: int = 96):
        self.target_col = target_col
        self.steps_per_day = steps_per_day
        self.bundle: ForecastBundle | None = None

    def fit(self, history_df: pd.DataFrame, val_frac: float = 0.2) -> "ForecastEngine":
        feats = make_feature_frame(history_df, self.target_col, self.steps_per_day)
        feature_names = list(feats.columns)
        n = len(feats)
        split = int(n * (1 - val_frac))
        bundle = ForecastBundle(self.target_col, "", feature_names)

        for _, h in HORIZONS.items():
            target = make_horizon_target(history_df[self.target_col], h)
            X_train, y_train = feats.iloc[:split], target.iloc[:split]
            X_val, y_val = feats.iloc[split:], target.iloc[split:]
            qm = train_quantile_model(X_train, y_train, feature_names)
            bundle.models[h] = qm
            bundle.backend = qm.backend

            mask = X_val[feature_names].notna().all(axis=1) & y_val.notna()
            if mask.sum() > 5:
                preds = qm.predict(X_val.loc[mask])
                bundle.calibration[h] = build_calibration_report(y_val.loc[mask], preds, self.target_col, h)

        self.bundle = bundle
        return self

    def predict(self, context_df: pd.DataFrame) -> dict[int, pd.DataFrame]:
        assert self.bundle is not None, "call fit() before predict()"
        feats = make_feature_frame(context_df, self.target_col, self.steps_per_day)
        out = {}
        for h, qm in self.bundle.models.items():
            mask = feats[self.bundle.feature_names].notna().all(axis=1)
            preds = qm.predict(feats.loc[mask, self.bundle.feature_names])
            out[h] = preds.reindex(feats.index)
        return out

    def predict_latest(self, context_df: pd.DataFrame, t_idx: int) -> dict[int, dict[float, float]]:
        """Convenience: quantile forecast dict {horizon_steps: {q: value}}
        anchored at row t_idx of context_df (uses only data up to t_idx)."""
        window = context_df.iloc[: t_idx + 1]
        preds = self.predict(window)
        out = {}
        for h, df in preds.items():
            if len(df) == 0 or df.iloc[-1].isna().any():
                out[h] = None
            else:
                out[h] = df.iloc[-1].to_dict()
        return out

    def calibration_summary(self) -> dict:
        assert self.bundle is not None
        return {
            "target": self.bundle.target, "backend": self.bundle.backend,
            "by_horizon": {str(h): rep.as_dict() for h, rep in self.bundle.calibration.items()},
        }
