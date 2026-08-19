"""Quantile regression models (PART G). LightGBM quantile regression is the
primary model; if LightGBM is unavailable at import time we fall back to
sklearn's GradientBoostingRegressor(loss="quantile") -- the fallback is
recorded so it's never silently mistaken for the primary model (PART AV)."""
from __future__ import annotations

import numpy as np
import pandas as pd

QUANTILES = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]

try:
    import lightgbm as lgb
    _HAS_LGBM = True
except ImportError:  # pragma: no cover
    _HAS_LGBM = False

from sklearn.ensemble import GradientBoostingRegressor


class QuantileModelSet:
    """One trained model per quantile for a single (target, horizon) pair."""

    def __init__(self, feature_names: list[str]):
        self.feature_names = feature_names
        self.models: dict[float, object] = {}
        self.backend: str = "lightgbm" if _HAS_LGBM else "sklearn_gbr_fallback"

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "QuantileModelSet":
        Xv = X[self.feature_names].values
        yv = y.values
        for q in QUANTILES:
            if _HAS_LGBM:
                model = lgb.LGBMRegressor(
                    objective="quantile", alpha=q, n_estimators=80, num_leaves=15,
                    max_depth=4, learning_rate=0.08, min_child_samples=5, verbosity=-1,
                )
            else:
                model = GradientBoostingRegressor(loss="quantile", alpha=q, n_estimators=80, max_depth=3)
            model.fit(Xv, yv)
            self.models[q] = model
        return self

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        Xv = X[self.feature_names].values
        preds = {q: self.models[q].predict(Xv) for q in QUANTILES}
        df = pd.DataFrame(preds, index=X.index)
        # enforce monotonicity across quantiles row-wise (crossing can happen with
        # independently-trained tree quantile models) -- sort, don't hide, but note it.
        arr = np.sort(df.values, axis=1)
        return pd.DataFrame(arr, index=X.index, columns=df.columns)


def train_quantile_model(X: pd.DataFrame, y: pd.Series, feature_names: list[str]) -> QuantileModelSet:
    mask = X[feature_names].notna().all(axis=1) & y.notna()
    qm = QuantileModelSet(feature_names)
    qm.fit(X.loc[mask], y.loc[mask])
    return qm
